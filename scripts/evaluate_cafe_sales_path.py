"""Backtest a shared one-quarter cafe sales model by applying it twice per origin."""

import argparse
from dataclasses import dataclass, replace
from pathlib import Path
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits


ROOT = Path(__file__).resolve().parents[1]
MODELING = ROOT / "jsw" / "모델링 방법"
PREVIOUS = MODELING / "카페매출_큰오차_개선_20261116"
PANEL = ROOT / "jsw/11.03 주간보고서_제안서/미래예측_카페기본_20261103/data/panel.parquet"
OUTPUT = MODELING / "카페매출_연속예측_20261124"
KEY = ["area", "origin", "target", "h"]
ORIGIN = 2026 * 4 + 1
LAGS = 15
MILLION = 1_000_000
EOK = 100_000_000
EXAMPLE_AREAS = ["3120052", "3120189", "3120103", "3120107", "3120003", "3110003"]


@dataclass(frozen=True)
class Spec:
    name: str
    loss: str
    shock_weight: float
    size_power: float
    leaves: int
    history: int = 20
    trees: int = 90
    context: bool = False
    recent_anchor: bool = False
    relative_power: float = 0.
    simulated_weight: float = 0.
    relative_floor: float = -1.
    replay: bool = False


SALES_SPECS = (
    Spec("absolute", "absolute_error", 1, 0, 15),
    Spec("absolute_robust", "absolute_error", .15, 0, 15),
    Spec("absolute_robust_size", "absolute_error", .15, .40, 15),
    Spec("absolute_robust_recent", "absolute_error", .15, .40, 15, 12),
    Spec("squared", "squared_error", 1, 0, 15),
    Spec("squared_robust", "squared_error", .15, 0, 15),
    Spec("squared_robust_size", "squared_error", .15, .40, 15),
    Spec("squared_robust_recent", "squared_error", .15, .40, 15, 12),
    Spec("squared_robust_deep", "squared_error", .15, .40, 31, 20, 120),
)
CONTEXT_BASE = Spec("context_absolute", "absolute_error", .15, .65, 15, history=12, trees=85,
                    context=True, recent_anchor=True)
CONTEXT_SIMULATED = replace(CONTEXT_BASE, name="context_simulated", trees=95,
                            relative_power=.55, simulated_weight=.5)
CONTEXT_SPECS = SALES_SPECS + (
    CONTEXT_BASE,
    replace(CONTEXT_BASE, name="context_squared", loss="squared_error"),
    replace(CONTEXT_BASE, name="context_relative", size_power=.45, history=16, trees=95, relative_power=.75),
    replace(CONTEXT_BASE, name="context_relative_squared", loss="squared_error", history=16,
            trees=95, relative_power=.75),
    replace(CONTEXT_BASE, name="context_recent_relative", relative_power=.65),
    CONTEXT_SIMULATED,
    replace(CONTEXT_SIMULATED, name="context_simulated_squared", loss="squared_error"),
)
POOLED_BASE = replace(CONTEXT_SIMULATED, name="path_pooled", loss="squared_error", size_power=.80,
                      history=16, trees=100, relative_power=.50, simulated_weight=1.4)
POOLED_RELATIVE = replace(POOLED_BASE, name="path_pooled_relative", size_power=.75, relative_power=.65,
                          simulated_weight=1.1, relative_floor=-2.5)
REPLAY_BASE = replace(POOLED_BASE, name="replay", simulated_weight=1., relative_floor=-2., replay=True)
SPECS = CONTEXT_SPECS + (
    POOLED_BASE,
    replace(POOLED_BASE, name="path_pooled_long", history=24),
    replace(POOLED_BASE, name="path_pooled_level", size_power=1.10, relative_power=.40),
    replace(POOLED_BASE, name="path_pooled_deep", size_power=.85, leaves=23, history=20,
            trees=115, simulated_weight=1.1),
    POOLED_RELATIVE,
    replace(POOLED_RELATIVE, name="path_pooled_relative_deep", leaves=23, history=20, trees=115),
    replace(POOLED_RELATIVE, name="path_pooled_exclude", shock_weight=0., relative_power=.55),
    replace(POOLED_RELATIVE, name="path_pooled_median", loss="absolute_error", size_power=.85, relative_power=.75),
    REPLAY_BASE,
    replace(REPLAY_BASE, name="replay_recent", history=12, size_power=.85),
    replace(REPLAY_BASE, name="replay_heavy", size_power=1.25, relative_power=.25),
    replace(REPLAY_BASE, name="replay_low_mape", relative_power=.80, size_power=.55),
    replace(REPLAY_BASE, name="replay_deep", leaves=25, history=20, simulated_weight=1.5),
    replace(REPLAY_BASE, name="replay_exclude", shock_weight=0., size_power=.65),
    replace(REPLAY_BASE, name="replay_median", loss="absolute_error", size_power=.70, relative_power=.65),
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def quarter_label(quarter):
    return f"{quarter // 4}Q{quarter % 4 + 1}"


def row_median(values, fallback=np.nan):
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="All-NaN slice encountered", category=RuntimeWarning)
        median = np.nanmedian(values, axis=1)
    return np.where(np.isfinite(median), median, fallback)


def lookup(sales, areas, quarters):
    keys = pd.MultiIndex.from_arrays([areas, quarters], names=["area", "t"])
    return sales.reindex(keys).to_numpy(dtype=float)


def read_panel(path):
    panel = pd.read_parquet(path, columns=["area", "t", "industry", "sales", "transactions",
                                          "stores", "population", "opened", "closed"])
    require(panel.industry.eq("CS100010").all(), "The input must contain only cafe sales")
    panel["area"] = panel.area.astype(str)
    panel = panel.set_index(["area", "t"]).drop(columns="industry").sort_index()
    require(panel.index.is_unique and panel.sales.dropna().ge(0).all(), "Invalid panel observations")
    return panel


def history_at(sales, rows):
    history = np.column_stack([
        lookup(sales, rows.area, rows.origin - lag) for lag in range(LAGS)
    ])
    # Zero or missing sales supplies no multiplicative growth information.
    return np.log(np.where(history > 0, history, np.nan))


def seasonal_change(history, end_lag):
    previous_years = [
        history[:, end_lag + distance] - history[:, end_lag + distance + 1]
        for distance in (4, 8, 12)
        if 0 <= end_lag + distance < LAGS - 1
    ]
    return row_median(np.column_stack(previous_years), 0).clip(-.35, .35)


def context_at(panel, rows):
    latest = {}
    for lag in (0, 1, 4):
        keys = pd.MultiIndex.from_arrays([rows.area, rows.origin - lag], names=panel.index.names)
        latest[lag] = panel.reindex(keys).set_axis(rows.index)
    result = {}
    for field in ("transactions", "stores", "population"):
        logged = {lag: np.log1p(frame[field].clip(lower=0)) for lag, frame in latest.items()}
        result[field] = logged[0]
        for lag in (1, 4):
            result[f"{field}_change_{lag}"] = (logged[0] - logged[lag]).clip(-2, 2)
    for field in ("opened", "closed"):
        result[f"{field}_rate"] = latest[0][field] / latest[0].stores.where(latest[0].stores.gt(0))
    return pd.DataFrame(result, index=rows.index)


def features(history, target, fallback, recent_anchor=False, context=None):
    target = np.asarray(target)
    season = {lag: seasonal_change(history, lag) for lag in range(-1, 3)}
    past_levels = np.column_stack([
        history[:, 1] + season[0],
        history[:, 2] + season[0] + season[1],
        history[:, 3] + season[0] + season[1] + season[2],
    ])
    # Translate recent seasons to the current quarter before deciding whether a jump is unusual.
    normal = row_median(past_levels, history[:, 0])
    supported = np.isfinite(history[:, 0]) & np.isfinite(past_levels).any(axis=1)
    shock = np.where(supported, history[:, 0] - normal, 0)
    cleaned = np.where(np.isfinite(history[:, 0]), normal + shock.clip(-.30, .30), normal)
    cleaned = np.where(np.isfinite(cleaned), cleaned, row_median(history, fallback))
    yoy = history[:, :4] - history[:, 4:8]
    qq_excess = history[:, :3] - history[:, 1:4] - np.column_stack([season[i] for i in range(3)])
    trend = row_median(qq_excess, 0).clip(-.15, .15)
    recent_yoy = row_median(yoy[:, 1:], 0).clip(-.70, .70)
    projected = cleaned + season[-1] + .35 * trend
    historical_target = history[:, 3] + recent_yoy
    anchor = np.where(np.isfinite(historical_target), .80 * projected + .20 * historical_target, projected)

    if recent_anchor:
        # Shrink year-to-year seasonal estimates and retain more of the current sales level.
        projected = cleaned + .50 * season[-1] + .12 * trend
        anchor = np.where(np.isfinite(historical_target), .95 * projected + .05 * historical_target, projected)

    matrix = pd.DataFrame({
        "log_anchor": anchor,
        "log_current": cleaned,
        "current_excess": shock.clip(-.55, .55),
        "atypical_current": np.abs(shock) > .35,
        "season_next": season[-1],
        "season_current": season[0],
        "season_previous": season[1],
        "yoy_robust": recent_yoy,
        "trend_robust": trend,
        "trend_3q": (cleaned - history[:, 3]).clip(-1, 1),
        "trend_annualized": (cleaned - history[:, 4]).clip(-1, 1),
        "recent_yoy": (cleaned - history[:, 4]).clip(-1, 1) - recent_yoy,
        "historical_target_gap": (historical_target - projected).clip(-1, 1),
        "excess_1q": qq_excess[:, 0].clip(-.55, .55),
        "excess_2q": qq_excess[:, 1].clip(-.55, .55),
        "excess_3q": qq_excess[:, 2].clip(-.55, .55),
        "spread": row_median(np.abs(qq_excess - trend[:, None]), 0).clip(0, 1),
        "past_sales_count": np.isfinite(history[:, :8]).sum(axis=1),
        "target_sin": np.sin(target % 4 * np.pi / 2),
        "target_cos": np.cos(target % 4 * np.pi / 2),
    })
    if context is not None:
        matrix = pd.concat([matrix, context.reset_index(drop=True)], axis=1)
    return matrix, anchor


def train_examples(panel, with_replay):
    sales = panel.sales
    rows = sales.dropna().loc[lambda values: values.gt(0)].reset_index()
    rows = rows[["area", "t"]].rename(columns={"t": "origin"})
    rows["target"] = rows.origin + 1
    rows["actual"] = lookup(sales, rows.area, rows.target)
    rows = rows.loc[rows.actual.gt(0)].reset_index(drop=True)
    history = history_at(sales, rows)
    matrix, anchor = features(history, rows.target, np.log(MILLION))
    actual_log = np.log(rows.actual.to_numpy())
    residual = actual_log - anchor
    # A subsequent observed return toward the predicted trend distinguishes temporary shocks
    # from persistent level changes. The training cut controls when this evidence is usable.
    following_target = rows.target + 1
    following = lookup(sales, rows.area, following_target)
    following_expected = anchor + seasonal_change(history, -2)
    following_error = np.log(np.where(following > 0, following, np.nan)) - following_expected
    shock_limit = np.maximum(.35, 3 * matrix.spread.to_numpy())
    atypical = np.abs(residual) > shock_limit
    reversed_jump = atypical & (np.abs(following_error) < .55 * np.abs(residual))
    actual_matrix, actual_anchor = features(history, rows.target, np.log(MILLION), True, context_at(panel, rows))
    prior_rows = rows.assign(origin=rows.origin - 1)
    prior_history = history_at(sales, prior_rows)
    _, simulated_log = features(prior_history, rows.origin, np.log(MILLION), True)
    simulated_history = np.column_stack([simulated_log, prior_history[:, :-1]])
    sim_matrix, sim_anchor = features(simulated_history, rows.target, np.log(MILLION), True,
                                      context_at(panel, prior_rows))
    designs = {
        "sales": (matrix, anchor),
        "context": (actual_matrix, actual_anchor),
        "simulated": (sim_matrix, sim_anchor, np.isfinite(prior_history[:, 0])),
    }
    examples = rows, actual_log, atypical, reversed_jump, designs
    if not with_replay:
        return examples
    replay_context = add_observed_trend(context_at(panel, rows), history)
    replay_prior_context = add_observed_trend(context_at(panel, prior_rows), prior_history)
    design = features(history, rows.target, np.log(MILLION), True, replay_context)
    designs["replay"] = design
    designs["replayed"] = replay_training(examples, prior_rows, prior_history, replay_prior_context)
    return examples


def add_observed_trend(context, history):
    context["origin_sales_log"] = history[:, 0]
    context["origin_yoy_log"] = row_median(history[:, :3] - history[:, 4:7], 0).clip(-1, 1)
    context["origin_excess_qq"] = row_median(np.column_stack([
        history[:, lag] - history[:, lag + 1] - seasonal_change(history, lag) for lag in range(3)
    ]), 0).clip(-.5, .5)
    return context


def replay_training(examples, prior_rows, prior_history, prior_context):
    """Generate each synthetic input with a model fit before its real value was observed."""
    rows = examples[0]
    teacher = replace(CONTEXT_BASE, name="training_replay", loss="squared_error", relative_power=.35, replay=True)
    estimated = np.full(len(rows), np.nan)
    for origin, index in prior_rows.groupby("origin", sort=True).groups.items():
        if origin < rows.target.min() + 7:
            continue
        model, audit = fit(examples, origin, teacher)
        matrix, anchor = features(prior_history[index], rows.origin.loc[index], audit["fallback_log"],
                                  True, prior_context.loc[index])
        estimated[index] = anchor + model.predict(matrix).clip(-.75, .75)
    replay_history = np.column_stack([estimated, prior_history[:, :-1]])
    matrix, anchor = features(replay_history, rows.target, np.log(MILLION), True, prior_context)
    return matrix, anchor, np.isfinite(estimated) & np.isfinite(prior_history[:, 0])


def fit(examples, cutoff, spec):
    rows, actual_log, atypical, reversed_jump, designs = examples
    eligible = rows.target.between(cutoff - spec.history + 1, cutoff).to_numpy()
    known_reversal = reversed_jump & rows.target.lt(cutoff).to_numpy()
    # The last training target has no observed subsequent quarter at this cutoff.
    unconfirmed = atypical & rows.target.eq(cutoff).to_numpy()
    weights = np.where(known_reversal, spec.shock_weight, 1.)
    weights = np.where(unconfirmed, np.sqrt(spec.shock_weight), weights)
    design_name = "replay" if spec.replay else "context" if spec.context else "sales"
    matrix, anchor = designs[design_name]
    size = np.exp(anchor[eligible])
    relative = np.exp(-spec.relative_power * (actual_log[eligible] - anchor[eligible]).clip(spec.relative_floor, .6))
    weights = weights[eligible] * (size / np.median(size)) ** spec.size_power * relative
    design = matrix.loc[eligible]
    residual = actual_log[eligible] - anchor[eligible]
    if spec.simulated_weight:
        simulated, sim_anchor, sim_supported = designs["replayed" if spec.replay else "simulated"]
        sim_eligible = eligible & sim_supported
        design = pd.concat([design, simulated.loc[sim_eligible]], ignore_index=True)
        residual = np.r_[residual, actual_log[sim_eligible] - sim_anchor[sim_eligible]]
        weights = np.r_[weights, spec.simulated_weight * weights[sim_supported[eligible]]]
    model = HistGradientBoostingRegressor(
        loss=spec.loss, max_leaf_nodes=spec.leaves, max_iter=spec.trees, min_samples_leaf=80,
        learning_rate=.055, l2_regularization=3, early_stopping=False, random_state=13,
    )
    included = weights > 0
    model.fit(design.loc[included], residual[included].clip(-2., 2.),
              sample_weight=weights[included].clip(.025, 8.))
    return model, {
        "training_n": int(eligible.sum()),
        "latest_training_target": int(rows.loc[eligible, "target"].max()),
        "reversed_jumps_n": int((eligible & known_reversal).sum()),
        "unconfirmed_jumps_n": int((eligible & unconfirmed).sum()),
        "excluded_design_rows": int((~included).sum()),
        "fallback_log": float(np.median(anchor[eligible])),
    }


def forecast_path(model, history, origin, fallback, recent_anchor=False, context=None):
    path = []
    state = history.copy()
    for target in (origin + 1, origin + 2):
        matrix, anchor = features(state, np.full(len(state), target), fallback, recent_anchor, context)
        residual = model.predict(matrix).clip(-.75, .75) if model is not None else 0
        predicted_log = anchor + residual
        path.append(np.exp(predicted_log))
        state = np.column_stack([predicted_log, state[:, :-1]])
    return np.column_stack(path)


def evaluation_rows(previous, stage):
    filename = "evaluation_predictions.csv" if stage == "eval" else "future_sales_predictions.csv"
    sources = [(1, "rolling_results", "trained_sales"), (2, "two_step_h2_results", "selected_two_step")]
    frames = []
    for horizon, folder, prediction in sources:
        frame = pd.read_csv(previous / folder / filename, dtype={"area": str})
        fields = KEY + ["area_name", "observed_origin_sales", prediction]
        if stage == "eval":
            fields += ["true_sales", "selected_prediction"]
        frame = frame.loc[frame.h.eq(horizon), fields].rename(columns={prediction: "ref_1118"})
        frames.append(frame)
    cases = pd.concat(frames, ignore_index=True)
    require(not cases.duplicated(KEY).any() and cases.target.eq(cases.origin + cases.h).all(),
            f"Invalid {stage} comparison keys")
    return cases


def development_rows(sales):
    positive = sales.loc[sales.gt(0)].reset_index()
    base = positive.loc[positive.t.between(2023 * 4 + 2, 2024 * 4 + 2), ["area", "t", "sales"]]
    base = base.rename(columns={"t": "origin", "sales": "observed_origin_sales"})
    frames = []
    for h in (1, 2):
        frame = base.assign(h=h, target=base.origin + h)
        frame["true_sales"] = lookup(sales, frame.area, frame.target)
        frames.append(frame.loc[frame.target.between(2024 * 4, 2024 * 4 + 3) & frame.true_sales.gt(0)])
    return pd.concat(frames, ignore_index=True)


def backtest(panel, cases, examples, specs):
    results, audits, fitted = [], [], {}
    for origin, frame in cases.groupby("origin", sort=True):
        areas = frame[["area", "origin"]].drop_duplicates(ignore_index=True)
        history = history_at(panel.sales, areas)
        context = context_at(panel, areas)
        replay_context = add_observed_trend(context.copy(), history)
        versions = {"seasonal_path": forecast_path(None, history, origin, np.log(MILLION))}
        for spec in specs:
            model, audit = fit(examples, origin, spec)
            require(audit["latest_training_target"] <= origin, "Training target beyond the origin")
            versions[spec.name] = forecast_path(
                model, history, origin, audit["fallback_log"], spec.recent_anchor,
                replay_context if spec.replay else context if spec.context else None,
            )
            audits.append({"origin": origin, "model": spec.name, **audit})
            fitted[(origin, spec.name)] = (model, audit)
        base = frame.merge(areas.reset_index(), on=["area", "origin"], validate="many_to_one")
        for name, path in versions.items():
            base[name] = path[base["index"], base.h - 1]
            base[f"{name}_first"] = path[base["index"], 0]
        results.append(base.drop(columns="index"))
        print(f"{quarter_label(origin)}: {len(areas)} areas, {len(specs)} shared-model fits", flush=True)
    return pd.concat(results, ignore_index=True), pd.DataFrame(audits), fitted


def direction_summary(actual_change, prediction_change):
    valid = np.isfinite(actual_change) & np.isfinite(prediction_change) & (actual_change != 0)
    actual = np.sign(actual_change[valid])
    predicted = np.sign(prediction_change[valid])
    recall = [np.mean(predicted[actual == sign] == sign) for sign in (-1, 1) if (actual == sign).any()]
    return {
        "direction_n": len(actual),
        "direction_pct": 100 * np.mean(actual == predicted) if len(actual) else np.nan,
        "balanced_direction_pct": 100 * np.mean(recall) if recall else np.nan,
    }


def score(cases, name):
    prediction = cases[name]
    actual = cases.true_sales
    errors = prediction - actual
    # Use both steps from each origin. The real first target supplies the truth for the second step.
    second = cases.loc[cases.h.eq(2)]
    actual_h2_change = second.true_sales - second.actual_first
    forecast_h2_change = second[name] - second[f"{name}_first"]
    actual_h1_change = second.actual_first - second.observed_origin_sales
    forecast_h1_change = second[f"{name}_first"] - second.observed_origin_sales
    valid_path = (
        np.isfinite(actual_h1_change) & np.isfinite(forecast_h1_change)
        & np.isfinite(actual_h2_change) & np.isfinite(forecast_h2_change)
        & actual_h1_change.ne(0) & actual_h2_change.ne(0)
    )
    both = (
        np.sign(actual_h1_change.loc[valid_path]) == np.sign(forecast_h1_change.loc[valid_path])
    ) & (
        np.sign(actual_h2_change.loc[valid_path]) == np.sign(forecast_h2_change.loc[valid_path])
    )
    first = cases.loc[cases.h.eq(1)]
    leg_actual = np.r_[first.true_sales - first.observed_origin_sales, actual_h2_change]
    leg_forecast = np.r_[first[name] - first.observed_origin_sales, forecast_h2_change]
    record = {
        "n": len(cases),
        "mape_pct": 100 * np.mean(np.abs(errors) / actual),
        "mse_eok2": np.mean((errors / EOK) ** 2),
        **direction_summary(leg_actual, leg_forecast),
        "complete_paths_n": len(both),
        "both_directions_pct": 100 * both.mean() if len(both) else np.nan,
    }
    return record


def attach_actual_first(cases, sales):
    cases["actual_first"] = lookup(sales, cases.area, cases.origin + 1)
    cases["actual_first"] = cases.actual_first.where(cases.actual_first.gt(0))
    # Zero marks incomplete origin history for direction. Positive sales still retain full error scoring.
    cases["observed_origin_sales"] = cases.observed_origin_sales.where(cases.observed_origin_sales.gt(0))
    return cases


def select_model(dev, specs):
    names = ["seasonal_path", *(spec.name for spec in specs)]
    all_scores = pd.DataFrame({name: score(dev, name) for name in names}).T
    by_quarter = pd.DataFrame([
        {"model": name, "target": quarter, "h": h, **score(frame, name)}
        for (quarter, h), frame in dev.groupby(["target", "h"])
        for name in names
    ])
    base = by_quarter.loc[by_quarter.model.eq("seasonal_path")].set_index(["target", "h"])
    for name, frame in by_quarter.groupby("model"):
        frame = frame.set_index(["target", "h"])
        all_scores.loc[name, "relative_mape"] = (frame.mape_pct / base.mape_pct).mean()
        all_scores.loc[name, "relative_mse"] = (frame.mse_eok2 / base.mse_eok2).mean()
        all_scores.loc[name, "worst_cell_mape_ratio"] = (frame.mape_pct / base.mape_pct).max()
    # Average by target quarter and lead so one year-end spike or one easy quarter cannot decide the fit.
    all_scores["selection_score"] = (
        .35 * all_scores.relative_mape + .20 * all_scores.relative_mse
        + .15 * all_scores.worst_cell_mape_ratio
        + .30 * all_scores.loc["seasonal_path", "balanced_direction_pct"] / all_scores.balanced_direction_pct
    )
    selected = min(specs, key=lambda spec: all_scores.loc[spec.name, "selection_score"])
    return selected, all_scores.rename_axis("model").reset_index()


def add_baseline_first(frame):
    first = frame.loc[frame.h.eq(1)].set_index(["area", "origin"])
    area_origins = pd.MultiIndex.from_frame(frame[["area", "origin"]])
    for name in ("ref_1118", "selected_prediction"):
        frame[f"{name}_first"] = first[name].reindex(area_origins).to_numpy()
    # Pair evaluation uses the same set of reference and candidate rows.
    paired = frame.ref_1118_first.notna()
    for name in ("ref_1118", "selected_prediction", "seasonal_path", "new_model"):
        frame[f"{name}_first"] = frame[f"{name}_first"].where(paired)
    return frame


def evaluation_scores(frame):
    groups = [("all", frame)]
    groups.extend((f"H{h}", rows) for h, rows in frame.groupby("h"))
    groups.extend((f"{quarter_label(q)}_H{h}", rows) for (q, h), rows in frame.groupby(["target", "h"]))
    groups.extend((f"area_{area}", rows) for area, rows in frame.loc[frame.area.isin(EXAMPLE_AREAS)].groupby("area"))
    return pd.DataFrame([
        {"group": group, "model": name, **score(rows, name)}
        for group, rows in groups
        for name in ("selected_prediction", "ref_1118", "seasonal_path", "new_model")
    ])


def write_csv(frame, path):
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def run(panel, previous, output, specs):
    panel = read_panel(panel)
    sales = panel.sales
    examples = train_examples(panel, with_replay=any(spec.replay for spec in specs))
    dev, dev_audit, _ = backtest(panel, development_rows(sales), examples, specs)
    selected, dev_scores = select_model(attach_actual_first(dev, sales), specs)
    print(f"2024 selection: {selected.name}", flush=True)

    evaluations = evaluation_rows(previous, "eval")
    observed = lookup(sales, evaluations.area, evaluations.target)
    require(len(evaluations) == 11_513 and np.array_equal(observed, evaluations.true_sales),
            "The 11.18 evaluation rows must match the original cafe panel")
    evaluated, ev_audit, _ = backtest(panel, evaluations, examples, (selected,))
    evaluated = evaluated.rename(columns={selected.name: "new_model", f"{selected.name}_first": "new_model_first"})
    evaluated = add_baseline_first(attach_actual_first(evaluated, sales))
    scores = evaluation_scores(evaluated)

    future = evaluation_rows(previous, "future")
    require(len(future) == 3016 and future.origin.eq(ORIGIN).all(), "Unexpected future cases")
    forecast, future_audit, fitted = backtest(panel, future, examples, (selected,))
    model, audit = fitted[(ORIGIN, selected.name)]
    output.mkdir(parents=True, exist_ok=True)
    model_path = output / "sales_path.joblib"
    joblib.dump({"model": model, "spec": vars(selected), "origin": ORIGIN, **audit}, model_path, compress=3)
    reloaded = joblib.load(model_path)
    cut = panel.loc[panel.index.get_level_values("t") <= ORIGIN]
    history = history_at(cut.sales, forecast)
    context = context_at(cut, forecast) if reloaded["spec"]["context"] else None
    if reloaded["spec"]["replay"]:
        context = add_observed_trend(context, history)
    replay = forecast_path(reloaded["model"], history, ORIGIN, reloaded["fallback_log"],
                           reloaded["spec"]["recent_anchor"], context)
    np.testing.assert_allclose(replay[np.arange(len(forecast)), forecast.h - 1], forecast[selected.name])
    require(np.isfinite(forecast[selected.name]).all() and forecast[selected.name].gt(0).all(),
            "Invalid future forecasts")

    write_csv(dev_scores, output / "development_scores.csv")
    write_csv(scores, output / "evaluation_scores.csv")
    write_csv(evaluated, output / "evaluation_predictions.csv")
    write_csv(forecast.rename(columns={selected.name: "new_model", f"{selected.name}_first": "new_model_first"}),
              output / "future_predictions.csv")
    write_csv(pd.concat([dev_audit.assign(stage="dev"), ev_audit.assign(stage="eval"),
                         future_audit.assign(stage="future")], ignore_index=True), output / "fit_audit.csv")
    print(scores.loc[scores.group.isin(["all", "H1", "H2"])].to_string(index=False), flush=True)


if __name__ == "__main__":
    suites = {
        "all": SPECS,
        "context": CONTEXT_SPECS,
        "exclude": tuple(spec for spec in SPECS if spec.name == "path_pooled_exclude"),
    }
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, default=PANEL)
    parser.add_argument("--previous", type=Path, default=PREVIOUS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--suite", choices=suites, default="all")
    args = parser.parse_args()
    output = args.output or (OUTPUT if args.suite == "all" else OUTPUT / f"{args.suite}_training")
    with threadpool_limits(limits=4):
        run(args.panel, args.previous, output, suites[args.suite])
