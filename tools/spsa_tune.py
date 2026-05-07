from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.eval_elo import EngineConfig, default_configs, render_progress, run_evaluation


@dataclass(frozen=True)
class Tunable:
    name: str
    baseline: float
    low: float
    high: float
    is_int: bool = False


TUNABLES: Tuple[Tunable, ...] = (
    Tunable("score_open_four", 240_000, 80_000, 500_000, True),
    Tunable("score_half_four", 62_000, 20_000, 150_000, True),
    Tunable("score_open_three", 28_000, 8_000, 80_000, True),
    Tunable("score_half_three", 6_200, 1_500, 20_000, True),
    Tunable("score_open_two", 1_500, 300, 5_000, True),
    Tunable("score_half_two", 360, 80, 1_500, True),
    Tunable("enemy_pattern_scale", 1.0, 0.8, 2.0),
)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def baseline_theta() -> Dict[str, float]:
    return {item.name: item.baseline for item in TUNABLES}


def candidate(theta: Dict[str, float], deltas: Dict[str, int], c: float, sign: int) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for item in TUNABLES:
        span = item.high - item.low
        raw = theta[item.name] + sign * c * span * deltas[item.name]
        raw = clamp(raw, item.low, item.high)
        out[item.name] = round(raw) if item.is_int else raw
    return out


def make_config(name: str, weights: Dict[str, float], depth: int, time_ms: int) -> EngineConfig:
    _base, config = default_configs(depth, depth, time_ms, time_ms)
    config.name = name
    config.score_open_four = int(weights["score_open_four"])
    config.score_half_four = int(weights["score_half_four"])
    config.score_open_three = int(weights["score_open_three"])
    config.score_half_three = int(weights["score_half_three"])
    config.score_open_two = int(weights["score_open_two"])
    config.score_half_two = int(weights["score_half_two"])
    config.enemy_pattern_scale = float(weights["enemy_pattern_scale"])
    return config


def fitness(
    *,
    weights: Dict[str, float],
    depth: int,
    time_ms: int,
    games: int,
    seed: int,
    competitive: bool,
    show_progress: bool,
    label: str,
) -> float:
    baseline, _enhanced = default_configs(depth, depth, time_ms, time_ms)
    baseline.name = "baseline"
    challenger = make_config(label, weights, depth, time_ms)
    result = run_evaluation(
        board_size=15,
        opening_plies=4,
        seed=seed,
        competitive=competitive,
        games=games,
        config_a=baseline,
        config_b=challenger,
        show_progress=show_progress,
        progress_title=label,
    )
    # run_evaluation reports Elo(A-B), while SPSA optimizes challenger B.
    return -result.elo_a_minus_b


def write_report(path: Path, rows: List[Dict[str, object]], best: Dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SPSA Tuning Report",
        "",
        "## Best Weights",
        "",
        "| Weight | Value |",
        "|---|---:|",
    ]
    for item in TUNABLES:
        value = best[item.name]
        lines.append(f"| {item.name} | {value:.4f} |" if not item.is_int else f"| {item.name} | {int(value)} |")
    lines.extend(
        [
            "",
            "## Iterations",
            "",
            "| Iter | Elo(+ vs base) | Elo(- vs base) | Step Elo Diff |",
            "|---:|---:|---:|---:|",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row['iteration']} | {float(row['elo_plus']):.2f} | "
            f"{float(row['elo_minus']):.2f} | {float(row['diff']):.2f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_checkpoint(path: Path, rows: List[Dict[str, object]], theta: Dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "iterations_completed": len(rows),
        "theta": theta,
        "rows": rows,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SPSA tuner for Gomoku evaluation weights.")
    parser.add_argument("--iterations", type=int, default=6)
    parser.add_argument("--games-per-eval", type=int, default=80)
    parser.add_argument("--depth", type=int, default=2)
    parser.add_argument("--time-ms", type=int, default=800)
    parser.add_argument("--seed", type=int, default=20260505)
    parser.add_argument("--a", type=float, default=0.02, help="SPSA learning-rate factor.")
    parser.add_argument("--c", type=float, default=0.10, help="SPSA perturbation factor.")
    parser.add_argument("--alpha", type=float, default=0.602)
    parser.add_argument("--gamma", type=float, default=0.101)
    parser.add_argument("--competitive", action="store_true")
    parser.add_argument("--output", type=str, default="reports/spsa_report.md")
    parser.add_argument("--checkpoint", type=str, default="", help="Optional JSON checkpoint path. Defaults to output with .json suffix.")
    parser.add_argument("--no-progress", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rng = random.Random(args.seed)
    theta = baseline_theta()
    rows: List[Dict[str, object]] = []
    start_ts = time.perf_counter()
    output = Path(args.output)
    checkpoint = Path(args.checkpoint) if args.checkpoint else output.with_suffix(".json")

    for index in range(max(1, args.iterations)):
        ak = args.a / ((index + 1) ** args.alpha)
        ck = args.c / ((index + 1) ** args.gamma)
        deltas = {item.name: rng.choice((-1, 1)) for item in TUNABLES}
        plus = candidate(theta, deltas, ck, sign=1)
        minus = candidate(theta, deltas, ck, sign=-1)
        iter_seed = args.seed + index * 997

        print(f"[{index + 1}/{args.iterations}] evaluating + perturbation")
        elo_plus = fitness(
            weights=plus,
            depth=args.depth,
            time_ms=args.time_ms,
            games=args.games_per_eval,
            seed=iter_seed,
            competitive=bool(args.competitive),
            show_progress=not args.no_progress,
            label=f"iter {index + 1} plus",
        )
        print(f"[{index + 1}/{args.iterations}] evaluating - perturbation")
        elo_minus = fitness(
            weights=minus,
            depth=args.depth,
            time_ms=args.time_ms,
            games=args.games_per_eval,
            seed=iter_seed,
            competitive=bool(args.competitive),
            show_progress=not args.no_progress,
            label=f"iter {index + 1} minus",
        )

        diff = elo_plus - elo_minus
        for item in TUNABLES:
            span = item.high - item.low
            # SPSA estimate in normalized parameter space.
            gradient = diff / (2.0 * ck * deltas[item.name])
            theta[item.name] = clamp(theta[item.name] + ak * span * gradient / 1000.0, item.low, item.high)
            if item.is_int:
                theta[item.name] = round(theta[item.name])

        rows.append(
            {
                "iteration": index + 1,
                "elo_plus": elo_plus,
                "elo_minus": elo_minus,
                "diff": diff,
            }
        )
        write_report(output, rows, theta)
        write_checkpoint(checkpoint, rows, theta)
        render_progress(index + 1, max(1, args.iterations), start_ts)
        print()

    write_report(output, rows, theta)
    write_checkpoint(checkpoint, rows, theta)
    print("Best weights:")
    for item in TUNABLES:
        value = theta[item.name]
        print(f"  {item.name}: {int(value) if item.is_int else round(value, 4)}")
    print(f"Report: {output.resolve()}")


if __name__ == "__main__":
    main()
