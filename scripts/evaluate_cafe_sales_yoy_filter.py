"""Backtest a shared cafe sales model that attenuates isolated YoY spikes."""

import argparse
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

import evaluate_cafe_sales_path as common


@dataclass(frozen=True)
class Spec:
    name: str
    excess_share: float
    threshold: float
    size_power: float = .65
    relative_power: float = .55
    replay_weight: float = .50
    history: int = 12


BASE = Spec("yoy_selective", .20, .23)
SPECS = (
    BASE,
    replace(BASE, name="yoy_selective_strong", excess_share=0.),
    replace(BASE, name="yoy_selective_sensitive", threshold=.17),
    replace(BASE, name="yoy_selective_conservative", threshold=.32),
    replace(BASE, name="yoy_selective_replay", size_power=.75, replay_weight=1.10, history=16),
    replace(BASE, name="yoy_selective_relative", relative_power=.70, replay_weight=1.10, history=16),
    replace(BASE, name="yoy_selective_value", size_power=.95, relative_power=.35, replay_weight=.85, history=16),
)


def filter_history(history, spec):
    """Reduce isolated positive growth in the latest three available quarters."""
    yoy = history[:, :11] - history[:, 4:15]
    result = history.copy()
    current_excess = np.zeros(len(history))
    for lag in (2, 1, 0):
        past = yoy[:, lag + 1:lag + 5]
        prior = common.row_median(past, 0.)
        spread = common.row_median(np.abs(past - prior[:, None]), .04)
        threshold = np.clip(2.75 * spread, spec.threshold, .6)
        continuing = (np.isfinite(past) & (past > prior[:, None] + .5 * threshold[:, None])).sum(axis=1) >= 2
        enough_history = np.isfinite(past).sum(axis=1) >= 3
        # Check the same-quarter jump against the recent sales level as well.
        # A low prior-year comparison alone must not make normal current sales a spike.
        seasonal = common.seasonal_change(history, lag)
        previous = np.where(np.isfinite(result[:, lag + 1]), result[:, lag + 1], history[:, lag + 2])
        level_gap = history[:, lag] - (previous + seasonal)
        yoy_excess = np.maximum(yoy[:, lag] - prior - threshold, 0)
        supported_excess = np.minimum(yoy_excess, np.maximum(level_gap - .10, 0))
        spike = np.where(enough_history & ~continuing & np.isfinite(supported_excess), supported_excess, 0.)
        result[:, lag] -= (1 - spec.excess_share) * spike
        if lag == 0:
            current_excess = spike
    return result, current_excess


def model_design(history, rows, context, spec, fallback):
    filtered, _ = filter_history(history, spec)
    return common.features(filtered, rows.target, fallback, True, context)


def prepared_design(panel, source, spec):
    rows, actual_log, atypical, reversed_jump, _ = source
    actual_history = common.history_at(panel.sales, rows)
    actual_context = common.context_at(panel, rows)
    matrix, anchor = model_design(actual_history, rows, actual_context, spec, np.log(common.MILLION))

    prior = rows.assign(origin=rows.origin - 1, target=rows.origin)
    prior_history = common.history_at(panel.sales, prior)
    prior_context = common.context_at(panel, prior)
    _, first_proxy = model_design(prior_history, prior, prior_context, spec, np.log(common.MILLION))
    simulated_history = np.column_stack([first_proxy, prior_history[:, :-1]])
    sim_x, sim_anchor = model_design(simulated_history, rows, prior_context, spec, np.log(common.MILLION))
    return rows, actual_log, atypical, reversed_jump, {
        "context": (matrix, anchor),
        "simulated": (sim_x, sim_anchor, np.isfinite(prior_history[:, 0])),
    }


def fitted_spec(spec):
    return replace(common.CONTEXT_SIMULATED, name=spec.name, loss="squared_error",
                   history=spec.history, size_power=spec.size_power,
                   relative_power=spec.relative_power, simulated_weight=spec.replay_weight)


def path(model, history, rows, context, spec, fallback):
    estimates = []
    state = history
    for target in (1, 2):
        model_rows = rows.assign(target=rows.origin + target)
        features, anchor = model_design(state, model_rows, context, spec, fallback)
        predicted = anchor + model.predict(features).clip(-.75, .75)
        estimates.append(np.exp(predicted))
        state = np.column_stack([predicted, state[:, :-1]])
    return np.column_stack(estimates)


def backtest(panel, cases, designs, specs):
    output, audits, models = [], [], {}
    for origin, frame in cases.groupby("origin", sort=True):
        locations = frame[["area", "origin"]].drop_duplicates(ignore_index=True)
        history = common.history_at(panel.sales, locations)
        context = common.context_at(panel, locations)
        result = frame.merge(locations.reset_index(), on=["area", "origin"], validate="many_to_one")
        forecasts = {"seasonal_path": common.forecast_path(None, history, origin, np.log(common.MILLION))}
        for spec in specs:
            model, audit = common.fit(designs[spec.name], origin, fitted_spec(spec))
            forecasts[spec.name] = path(model, history, locations, context, spec, audit["fallback_log"])
            audits.append({"origin": origin, "model": spec.name, **audit})
            models[(origin, spec.name)] = (model, audit)
        for name, predicted in forecasts.items():
            result[name] = predicted[result["index"], result.h - 1]
            result[f"{name}_first"] = predicted[result["index"], 0]
        output.append(result.drop(columns="index"))
        print(f"{common.quarter_label(origin)}: {len(locations)} areas, {len(specs)} fits", flush=True)
    return pd.concat(output, ignore_index=True), pd.DataFrame(audits), models


def comparison_scores(evaluated):
    samples = {
        "all": evaluated,
        "H1": evaluated.loc[evaluated.h.eq(1)],
        "H2": evaluated.loc[evaluated.h.eq(2)],
        "spike_at_origin": evaluated.loc[evaluated.yoy_spike_at_origin],
        "spike_at_origin_H1": evaluated.loc[evaluated.yoy_spike_at_origin & evaluated.h.eq(1)],
        "spike_at_origin_H2": evaluated.loc[evaluated.yoy_spike_at_origin & evaluated.h.eq(2)],
    }
    return pd.DataFrame([
        {"group": name, "model": method, **common.score(rows, method)}
        for name, rows in samples.items()
        for method in ("ref_1118", "same_model_unfiltered", "new_model")
    ])


def run(panel_path, previous, output):
    panel = common.read_panel(panel_path)
    source = common.train_examples(panel, with_replay=False)
    designs = {spec.name: prepared_design(panel, source, spec) for spec in SPECS}
    dev, dev_audit, _ = backtest(panel, common.development_rows(panel.sales), designs, SPECS)
    selected, dev_scores = common.select_model(common.attach_actual_first(dev, panel.sales), SPECS)
    print(f"2024 selection: {selected.name}", flush=True)
    unfiltered = replace(selected, name="same_model_unfiltered", excess_share=1.)
    designs[unfiltered.name] = prepared_design(panel, source, unfiltered)
    evaluation = common.evaluation_rows(previous, "eval")
    common.require(len(evaluation) == 11_513, "Unexpected historical sample")
    np.testing.assert_array_equal(common.lookup(panel.sales, evaluation.area, evaluation.target), evaluation.true_sales)
    evaluated, eval_audit, _ = backtest(panel, evaluation, designs, (selected, unfiltered))
    history = common.history_at(panel.sales, evaluated)
    _, excess = filter_history(history, selected)
    evaluated["yoy_spike_at_origin"] = excess > 0
    renamed = {selected.name: "new_model", f"{selected.name}_first": "new_model_first"}
    evaluated = common.add_baseline_first(common.attach_actual_first(evaluated.rename(columns=renamed), panel.sales))
    evaluated["same_model_unfiltered_first"] = evaluated.same_model_unfiltered_first.where(evaluated.ref_1118_first.notna())
    full = common.evaluation_scores(evaluated)
    matched_scores = comparison_scores(evaluated)

    future = common.evaluation_rows(previous, "future")
    common.require(len(future) == 3016 and future.origin.eq(common.ORIGIN).all(), "Unexpected future sample")
    outlook, future_audit, models = backtest(panel, future, designs, (selected,))
    model, audit = models[(common.ORIGIN, selected.name)]
    output.mkdir(parents=True, exist_ok=True)
    stored = output / "sales_yoy_filter_path.joblib"
    joblib.dump({"model": model, "spec": asdict(selected), **audit}, stored, compress=3)
    reloaded = joblib.load(stored)
    cut = panel.loc[panel.index.get_level_values("t") <= common.ORIGIN]
    history = common.history_at(cut.sales, outlook)
    restored = path(reloaded["model"], history, outlook, common.context_at(cut, outlook),
                    Spec(**reloaded["spec"]), reloaded["fallback_log"])
    np.testing.assert_allclose(restored[np.arange(len(outlook)), outlook.h - 1], outlook[selected.name], rtol=1e-12)
    for name, frame in (
        ("development_scores", dev_scores), ("evaluation_scores", full), ("comparison_scores", matched_scores),
        ("evaluation_predictions", evaluated), ("future_predictions", outlook.rename(columns=renamed)),
        ("fit_audit", pd.concat([dev_audit.assign(stage="dev"), eval_audit.assign(stage="eval"),
                                 future_audit.assign(stage="future")], ignore_index=True)),
    ):
        common.write_csv(frame, output / f"{name}.csv")
    print(matched_scores.to_string(index=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, default=common.PANEL)
    parser.add_argument("--previous", type=Path, default=common.PREVIOUS)
    parser.add_argument("--output", type=Path, default=common.OUTPUT / "yoy_filter_training")
    args = parser.parse_args()
    with threadpool_limits(limits=4):
        run(args.panel, args.previous, args.output)
