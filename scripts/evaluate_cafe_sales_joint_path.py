"""Fit a single recurrent sales step against the errors along both forecast quarters."""

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn

import evaluate_cafe_sales_path as common


@dataclass(frozen=True)
class Spec:
    name: str
    level_weight: float
    direction_weight: float
    shock_weight: float
    history: int = 16
    epochs: int = 24
    width: int = 48


SPECS = (
    Spec("joint_relative", .25, .06, .15),
    Spec("joint_balanced", .50, .06, .15),
    Spec("joint_level", .75, .06, .15),
    Spec("joint_direction", .50, .16, .15),
    Spec("joint_without_reversals", .50, .06, 0.),
    Spec("joint_larger", .55, .08, .15, 20, 33, 80),
)


class SalesStep(nn.Module):
    def __init__(self, feature_count, width):
        super().__init__()
        self.increment = nn.Sequential(
            nn.Linear(feature_count + 5, width),
            nn.SiLU(),
            nn.Linear(width, width // 2),
            nn.SiLU(),
            nn.Linear(width // 2, 1),
        )

    def forward(self, fixed, initial, previous, calendar):
        level = initial
        path = []
        for season in calendar.unbind(dim=1):
            state = torch.column_stack((fixed, level - initial, previous.clamp(-1, 1), season))
            change = .50 * season[:, 0] + .55 * self.increment(state).squeeze(-1).tanh()
            level = level + change
            path.append(level)
            previous = change
        return torch.stack(path, dim=1)


def prepare_inputs(panel, rows, fallback):
    history = common.history_at(panel.sales, rows)
    context = common.add_observed_trend(common.context_at(panel, rows), history)
    matrix, anchor = common.features(history, rows.origin + 1, fallback, True, context)
    initial = matrix.log_current.to_numpy(dtype=float)
    previous = np.nan_to_num(history[:, 0] - history[:, 1])
    calendar = np.stack([
        np.column_stack((common.seasonal_change(history, -h),
                         np.sin((rows.origin + h) % 4 * np.pi / 2),
                         np.cos((rows.origin + h) % 4 * np.pi / 2)))
        for h in (1, 2)
    ], axis=1)
    fixed = matrix.drop(columns=["target_sin", "target_cos", "log_anchor", "season_next"]).to_numpy(dtype=float)
    return fixed, initial, previous, calendar, anchor


def prepare_training(panel):
    rows = panel.sales.loc[panel.sales.gt(0)].reset_index()[["area", "t"]].rename(columns={"t": "origin"})
    inputs = prepare_inputs(panel, rows, np.log(common.MILLION))
    actual = np.column_stack([common.lookup(panel.sales, rows.area, rows.origin + h) for h in (0, 1, 2, 3)])
    logged = np.log(np.where(actual > 0, actual, np.nan))
    season = inputs[3][:, :, 0]
    anchor = inputs[-1]
    expected = np.column_stack((anchor, anchor + .50 * season[:, 1], anchor + .50 * season[:, 1]))
    deviation = logged[:, 1:4] - expected
    confirmed = ((np.abs(deviation[:, :2]) > .35)
                 & (np.abs(deviation[:, 1:3]) < .55 * np.abs(deviation[:, :2])))
    return rows, inputs, logged[:, :3], confirmed


def to_tensor(values):
    return torch.tensor(np.ascontiguousarray(values), dtype=torch.float32)


def inference_inputs(inputs, center, spread):
    fixed, initial, previous, calendar, _ = inputs
    scaled = np.nan_to_num((fixed - center) / spread).clip(-6., 6.)
    return to_tensor(scaled), to_tensor(initial), to_tensor(previous), to_tensor(calendar)


def fit(training, origin, spec):
    rows, inputs, log_sales, confirmed = training
    in_window = rows.origin.between(origin - spec.history, origin - 1).to_numpy()
    cut = rows.origin.to_numpy()[:, None] + np.array([1, 2]) <= origin
    eligible = in_window & (np.isfinite(log_sales[:, 1:]) & cut).any(axis=1)
    sliced = tuple(values[eligible] for values in inputs)
    fixed = sliced[0]
    center = common.row_median(fixed.T, 0)
    spread = common.row_median(np.abs(fixed - center).T, 0).clip(.12)
    tensors = inference_inputs(sliced, center, spread)
    labels = log_sales[eligible]
    target = labels[:, 1:]
    valid = np.isfinite(target) & cut[eligible]
    training_targets = rows.origin.to_numpy()[eligible, None] + np.array([1, 2])
    latest_target = int(training_targets[valid].max())
    common.require(latest_target <= origin, "Recurrent training target beyond the origin")
    reversal_known = rows.origin.to_numpy()[eligible, None] + np.array([2, 3]) <= origin
    weights = valid * np.where(confirmed[eligible] & reversal_known, spec.shock_weight, 1.)
    actual_changes = np.diff(labels, axis=1)
    signs = to_tensor(np.sign(np.nan_to_num(actual_changes)))
    sign_weight = to_tensor(weights * np.isfinite(actual_changes) * (np.abs(actual_changes) > .005))
    target = to_tensor(np.where(valid, target, sliced[1][:, None]))
    weights = to_tensor(weights)
    size = np.exp(sliced[1])
    value_weights = to_tensor((size / np.median(size)) ** .8).clamp(.1, 14.)
    value_weights /= value_weights.mean()

    torch.manual_seed(368)
    model = SalesStep(fixed.shape[1], spec.width)
    optimizer = torch.optim.AdamW(model.parameters(), lr=.002, weight_decay=.018)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=spec.epochs, eta_min=.00035)
    for _ in range(spec.epochs):
        for indices in torch.randperm(len(fixed)).split(768):
            current = tensors[1][indices]
            path = model(*(values[indices] for values in tensors))
            error = path - target[indices]
            log_loss = torch.nn.functional.smooth_l1_loss(path, target[indices], beta=.12, reduction="none")
            relative_loss = torch.expm1(error.clamp(-2., 1.25)).abs()
            level_loss = error.square() * value_weights[indices, None]
            loss = ((.44 * log_loss + .14 * relative_loss + spec.level_weight * level_loss)
                    * weights[indices]).mean()
            changes = torch.diff(torch.column_stack((current, path)), dim=1)
            direction_loss = torch.nn.functional.softplus(-9 * changes * signs[indices])
            loss += spec.direction_weight * (direction_loss * sign_weight[indices]).mean()
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.)
            optimizer.step()
        scheduler.step()
    audit = {"training_n": int(eligible.sum()), "latest_training_target": latest_target}
    return model.eval(), center, spread, float(np.median(labels[:, 0])), audit


def paths(panel, cases, training, specs):
    outputs, audits = [], []
    saved = {}
    for origin, group in cases.groupby("origin", sort=True):
        areas = group[["area", "origin"]].drop_duplicates(ignore_index=True)
        history = common.history_at(panel.sales, areas)
        frame = group.merge(areas.reset_index(), on=["area", "origin"], validate="many_to_one")
        baseline = common.forecast_path(None, history, origin, np.log(common.MILLION))
        frame["seasonal_path"] = baseline[frame["index"], frame.h - 1]
        frame["seasonal_path_first"] = baseline[frame["index"], 0]
        for spec in specs:
            model, center, spread, fallback, audit = fit(training, origin, spec)
            with torch.inference_mode():
                inputs = inference_inputs(prepare_inputs(panel, areas, fallback), center, spread)
                path = model(*inputs).exp().numpy().astype(np.float64)
            frame[spec.name] = path[frame["index"], frame.h - 1]
            frame[f"{spec.name}_first"] = path[frame["index"], 0]
            audits.append({"origin": origin, "model": spec.name, **audit})
            saved[(origin, spec.name)] = (model, center, spread, fallback)
        outputs.append(frame.drop(columns="index"))
        print(f"{common.quarter_label(origin)}: {len(areas)} areas, {len(specs)} recurrent fits", flush=True)
    return pd.concat(outputs, ignore_index=True), pd.DataFrame(audits), saved


def run(panel_path, previous, output):
    panel = common.read_panel(panel_path)
    training = prepare_training(panel)
    dev, dev_audit, _ = paths(panel, common.development_rows(panel.sales), training, SPECS)
    selected, scores = common.select_model(common.attach_actual_first(dev, panel.sales), SPECS)
    print(f"2024 selection: {selected.name}", flush=True)
    evaluations = common.evaluation_rows(previous, "eval")
    actual = common.lookup(panel.sales, evaluations.area, evaluations.target)
    common.require(len(evaluations) == 11_513 and np.array_equal(actual, evaluations.true_sales),
                   "Unexpected historical evaluation rows")
    evaluated, ev_audit, _ = paths(panel, evaluations, training, (selected,))
    renamed = {selected.name: "new_model", f"{selected.name}_first": "new_model_first"}
    evaluated = common.add_baseline_first(common.attach_actual_first(evaluated.rename(columns=renamed), panel.sales))
    metrics = common.evaluation_scores(evaluated)
    future_cases = common.evaluation_rows(previous, "future")
    common.require(len(future_cases) == 3016 and future_cases.origin.eq(common.ORIGIN).all(),
                   "Unexpected future forecast rows")
    future, future_audit, saved = paths(panel, future_cases, training, (selected,))
    output.mkdir(parents=True, exist_ok=True)
    model, center, spread, fallback = saved[(common.ORIGIN, selected.name)]
    weights = output / "sales_joint_path.pt"
    torch.save({"parameters": model.state_dict(), "center": to_tensor(center), "spread": to_tensor(spread),
                "fallback": fallback, "width": selected.width, "spec": vars(selected)}, weights)
    restored = torch.load(weights, map_location="cpu", weights_only=True)
    replay_model = SalesStep(len(restored["center"]), restored["width"])
    replay_model.load_state_dict(restored["parameters"])
    cut = panel.loc[panel.index.get_level_values("t") <= common.ORIGIN]
    replay_inputs = prepare_inputs(cut, future, restored["fallback"])
    with torch.inference_mode():
        replay = replay_model(*inference_inputs(replay_inputs, restored["center"].numpy(),
                                                restored["spread"].numpy())).exp().numpy()
    np.testing.assert_allclose(replay[np.arange(len(future)), future.h - 1], future[selected.name], rtol=5e-6)
    common.require(np.isfinite(future[selected.name]).all() and future[selected.name].gt(0).all(),
                   "Invalid future forecasts")
    common.write_csv(scores, output / "development_scores.csv")
    common.write_csv(metrics, output / "evaluation_scores.csv")
    common.write_csv(evaluated, output / "evaluation_predictions.csv")
    common.write_csv(future.rename(columns=renamed), output / "future_predictions.csv")
    common.write_csv(pd.concat([dev_audit.assign(stage="dev"), ev_audit.assign(stage="eval"),
                                future_audit.assign(stage="future")]), output / "fit_audit.csv")
    print(metrics.loc[metrics.group.isin(["all", "H1", "H2"])].to_string(index=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, default=common.PANEL)
    parser.add_argument("--previous", type=Path, default=common.PREVIOUS)
    parser.add_argument("--output", type=Path, default=common.OUTPUT / "joint_training")
    args = parser.parse_args()
    torch.set_num_threads(4)
    run(args.panel, args.previous, args.output)
