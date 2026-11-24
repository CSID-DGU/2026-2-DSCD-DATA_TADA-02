"""Evaluate an inference-time guard for isolated positive YoY sales shocks."""

import argparse
from dataclasses import dataclass, replace
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

import evaluate_cafe_sales_path as common
import evaluate_cafe_sales_yoy_filter as detection


@dataclass(frozen=True)
class Guard:
    name: str
    threshold: float
    strength: float
    maximum_log_cut: float


UNFILTERED = Guard("same_model_unfiltered", .30, 0., 0.)
GUARDS = (
    Guard("narrow_guard", .30, .30, .08),
    Guard("strong_narrow_guard", .30, .60, .12),
    Guard("severe_only_guard", .40, .45, .10),
    Guard("extreme_only_guard", .55, .50, .10),
    Guard("broad_soft_guard", .23, .20, .06),
)


def guarded_step(model, state, target, context, fallback, guard):
    x, anchor = common.features(state, target, fallback, True, context)
    raw = anchor + model.predict(x).clip(-.75, .75)
    if not guard.strength:
        return raw, np.zeros(len(state), dtype=bool)
    spec = replace(detection.BASE, threshold=guard.threshold, excess_share=.20)
    filtered, excess = detection.filter_history(state, spec)
    active = excess > 0
    if active.any():
        alternate, alternate_anchor = common.features(
            filtered[active], np.asarray(target)[active], fallback, True, context.loc[active],
        )
        alternate_log = alternate_anchor + model.predict(alternate).clip(-.75, .75)
        # The correction uses the same estimator and activates only if the spike raised its forecast.
        cut = guard.strength * np.maximum(raw[active] - alternate_log, 0.)
        raw[active] -= cut.clip(0., guard.maximum_log_cut)
    return raw, active


def forecast(model, history, rows, context, fallback, guard):
    state = history.copy()
    path, active = [], []
    for distance in (1, 2):
        estimate, mask = guarded_step(model, state, rows.origin + distance, context, fallback, guard)
        path.append(np.exp(estimate))
        active.append(mask)
        state = np.column_stack([estimate, state[:, :-1]])
    return np.column_stack(path), np.column_stack(active)


def backtest(panel, cases, designs, training_spec, guards):
    output, audits, saved = [], [], {}
    for origin, frame in cases.groupby("origin", sort=True):
        locations = frame[["area", "origin"]].drop_duplicates(ignore_index=True)
        history = common.history_at(panel.sales, locations)
        context = common.context_at(panel, locations)
        result = frame.merge(locations.reset_index(), on=["area", "origin"], validate="many_to_one")
        model, audit = common.fit(designs, origin, training_spec)
        audit = {"origin": origin, **audit}
        audits.append(audit)
        saved[origin] = (model, audit)
        baseline = common.forecast_path(None, history, origin, np.log(common.MILLION))
        result["seasonal_path"] = baseline[result["index"], result.h - 1]
        result["seasonal_path_first"] = baseline[result["index"], 0]
        for guard in guards:
            path, active = forecast(model, history, locations, context, audit["fallback_log"], guard)
            result[guard.name] = path[result["index"], result.h - 1]
            result[f"{guard.name}_first"] = path[result["index"], 0]
            result[f"{guard.name}_active"] = active[result["index"], 0]
        output.append(result.drop(columns="index"))
        print(f"{common.quarter_label(origin)}: {len(locations)} areas, one shared fit", flush=True)
    return pd.concat(output, ignore_index=True), pd.DataFrame(audits), saved


def reversal_diagnostic(sales, evaluated):
    flagged = evaluated.loc[evaluated.h.eq(1) & evaluated.yoy_spike_at_origin]
    history = common.history_at(sales, flagged)
    yoy = history[:, :5] - history[:, 4:9]
    historical = common.row_median(yoy[:, 1:], 0.)
    next_yoy = np.log(flagged.true_sales.to_numpy()) - history[:, 3]
    comparable = np.isfinite(next_yoy)
    lowered = evaluated.same_model_unfiltered - evaluated.new_model > .01
    already_low = evaluated.same_model_unfiltered.lt(evaluated.true_sales)
    return pd.DataFrame([{
        "comparable_spikes_h1": int(comparable.sum()),
        "next_yoy_was_lower": int((comparable & (next_yoy < yoy[:, 0])).sum()),
        "moved_toward_prior_trend": int((comparable & (np.abs(next_yoy - historical) <
                                                     np.abs(yoy[:, 0] - historical))).sum()),
        "forecasts_lowered": int(lowered.sum()),
        "lowered_forecasts_already_below_actual": int((lowered & already_low).sum()),
    }])


def run(panel_path, previous, output):
    panel = common.read_panel(panel_path)
    training_spec = replace(common.CONTEXT_SIMULATED, loss="squared_error")
    designs = common.train_examples(panel, with_replay=False)
    development, dev_audit, _ = backtest(
        panel, common.development_rows(panel.sales), designs, training_spec, (UNFILTERED, *GUARDS),
    )
    _, dev_scores = common.select_model(common.attach_actual_first(development, panel.sales), (UNFILTERED, *GUARDS))
    ranked = dev_scores.set_index("model").selection_score
    selected = min(GUARDS, key=lambda guard: ranked.loc[guard.name])
    print(f"2024 filter selection: {selected.name}; score {ranked.loc[selected.name]:.6f}; "
          f"unfiltered {ranked.loc[UNFILTERED.name]:.6f}", flush=True)
    evaluation = common.evaluation_rows(previous, "eval")
    common.require(len(evaluation) == 11_513, "Unexpected historical sample")
    np.testing.assert_array_equal(common.lookup(panel.sales, evaluation.area, evaluation.target), evaluation.true_sales)
    rename = {selected.name: "new_model", f"{selected.name}_first": "new_model_first",
              f"{selected.name}_active": "yoy_spike_at_origin"}
    evaluated, eval_audit, _ = backtest(panel, evaluation, designs, training_spec, (UNFILTERED, selected))
    evaluated = common.add_baseline_first(common.attach_actual_first(evaluated.rename(columns=rename), panel.sales))
    evaluated["same_model_unfiltered_first"] = evaluated.same_model_unfiltered_first.where(evaluated.ref_1118_first.notna())
    comparison = detection.comparison_scores(evaluated)
    score = common.evaluation_scores(evaluated)
    future = common.evaluation_rows(previous, "future")
    common.require(len(future) == 3_016 and future.origin.eq(common.ORIGIN).all(), "Unexpected future sample")
    outlook, future_audit, models = backtest(panel, future, designs, training_spec, (selected,))
    model, audit = models[common.ORIGIN]
    output.mkdir(parents=True, exist_ok=True)
    path = output / "sales_yoy_guard.joblib"
    joblib.dump({"model": model, "guard": vars(selected), **audit}, path, compress=3)
    restored = joblib.load(path)
    cut = panel.loc[panel.index.get_level_values("t") <= common.ORIGIN]
    history = common.history_at(cut.sales, outlook)
    replay, _ = forecast(restored["model"], history, outlook, common.context_at(cut, outlook),
                         restored["fallback_log"], Guard(**restored["guard"]))
    np.testing.assert_allclose(replay[np.arange(len(outlook)), outlook.h - 1], outlook[selected.name], rtol=1e-12)
    common.require(np.isfinite(replay).all() and (replay > 0).all(), "Invalid future predictions")
    for name, frame in (
        ("development_scores", dev_scores), ("evaluation_scores", score), ("comparison_scores", comparison),
        ("evaluation_predictions", evaluated), ("future_predictions", outlook.rename(columns=rename)),
        ("reversal_diagnostic", reversal_diagnostic(panel.sales, evaluated)),
        ("fit_audit", pd.concat([dev_audit.assign(stage="dev"), eval_audit.assign(stage="eval"),
                                 future_audit.assign(stage="future")], ignore_index=True)),
    ):
        common.write_csv(frame, output / f"{name}.csv")
    print(comparison.to_string(index=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, default=common.PANEL)
    parser.add_argument("--previous", type=Path, default=common.PREVIOUS)
    parser.add_argument("--output", type=Path, default=common.OUTPUT / "yoy_guard_training")
    args = parser.parse_args()
    with threadpool_limits(limits=4):
        run(args.panel, args.previous, args.output)
