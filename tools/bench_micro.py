from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gomoku_core import BLACK, GameBoard, GomokuAI, is_forbidden_move


@dataclass
class PositionCase:
    case_id: str
    size: int
    moves: List[Tuple[int, int, int]]
    side_to_move: int


def load_positions(path: Path) -> List[PositionCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    positions = payload.get("positions", [])
    cases: List[PositionCase] = []
    for index, item in enumerate(positions):
        cases.append(
            PositionCase(
                case_id=str(item.get("id", f"case_{index+1}")),
                size=int(item.get("size", 15)),
                moves=[(int(x), int(y), int(s)) for x, y, s in item.get("moves", [])],
                side_to_move=int(item.get("side_to_move", BLACK)),
            )
        )
    return cases


def build_board(case: PositionCase) -> GameBoard:
    board = GameBoard(size=case.size)
    for x, y, stone in case.moves:
        board.place(x, y, stone)
    return board


def quantile(sorted_values: Sequence[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = max(0, min(len(sorted_values) - 1, int(q * (len(sorted_values) - 1))))
    return sorted_values[index]


def format_duration(seconds: float) -> str:
    total = max(0, int(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def render_progress(done: int, total: int, start_ts: float, bar_width: int = 28) -> None:
    done = max(0, min(done, total))
    ratio = (done / total) if total > 0 else 1.0
    filled = int(ratio * bar_width)
    bar = "#" * filled + "-" * (bar_width - filled)
    elapsed = time.perf_counter() - start_ts
    eta = ((elapsed / done) * (total - done)) if done > 0 else 0.0
    line = (
        f"\r[{bar}] {done}/{total}  {ratio * 100:5.1f}%  "
        f"Elapsed {format_duration(elapsed)}  ETA {format_duration(eta)}"
    )
    print(line, end="", flush=True)


def benchmark_ns_per_op(
    op: Callable[[], None],
    loops_per_sample: int,
    samples: int,
    tick: Callable[[], None] | None = None,
) -> Dict[str, float]:
    observed: List[float] = []
    for _ in range(samples):
        start = time.perf_counter_ns()
        for _ in range(loops_per_sample):
            op()
        elapsed = time.perf_counter_ns() - start
        observed.append(elapsed / float(loops_per_sample))
        if tick is not None:
            tick()
    observed.sort()
    return {
        "mean_ns": statistics.fmean(observed),
        "p95_ns": quantile(observed, 0.95),
        "p99_ns": quantile(observed, 0.99),
    }


def run_case(case: PositionCase, loops: int, samples: int, tick: Callable[[], None] | None = None) -> Dict[str, Dict[str, float]]:
    board = build_board(case)
    ai = GomokuAI(depth=2, time_limit_ms=80)
    candidates = board.focused_candidate_moves(distance=2, limit_area=6) or board.candidate_moves()
    move_pool = [(m.x, m.y) for m in candidates if board.get(m.x, m.y) == 0]
    if not move_pool:
        center = board.size // 2
        move_pool = [(center, center)]
    state_store: Dict[Tuple[Tuple[int, ...], ...], int] = {}

    idx = {"v": 0}

    def next_xy() -> Tuple[int, int]:
        i = idx["v"] % len(move_pool)
        idx["v"] += 1
        return move_pool[i]

    def op_make_unmake() -> None:
        x, y = next_xy()
        if board.get(x, y) != 0:
            return
        if board.place(x, y, case.side_to_move):
            board.remove(x, y)

    def op_eval() -> None:
        ai.evaluate_board(board, case.side_to_move)

    def op_candidates() -> None:
        board.focused_candidate_moves(distance=2, limit_area=6)

    def op_legality() -> None:
        x, y = next_xy()
        is_forbidden_move(board, x, y, BLACK)

    def op_tt_probe_store() -> None:
        key = board.state_key()
        val = state_store.get(key, 0)
        state_store[key] = val + 1

    return {
        "make_unmake": benchmark_ns_per_op(op_make_unmake, loops, samples, tick=tick),
        "eval_board": benchmark_ns_per_op(op_eval, loops, samples, tick=tick),
        "candidate_generation": benchmark_ns_per_op(op_candidates, loops, samples, tick=tick),
        "legality_check": benchmark_ns_per_op(op_legality, loops, samples, tick=tick),
        "state_probe_store": benchmark_ns_per_op(op_tt_probe_store, loops, samples, tick=tick),
    }


def print_table(results: Dict[str, Dict[str, float]]) -> None:
    print("| Metric | Mean(ns) | p95(ns) | p99(ns) |")
    print("|---|---:|---:|---:|")
    for metric, vals in results.items():
        print(
            f"| {metric} | {vals['mean_ns']:.1f} | {vals['p95_ns']:.1f} | {vals['p99_ns']:.1f} |"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run micro-benchmarks for Gomoku engine modules.")
    parser.add_argument("--dataset", type=str, default="bench/midgame.json")
    parser.add_argument("--loops", type=int, default=5000, help="Loops per sample.")
    parser.add_argument("--samples", type=int, default=30, help="Sample count.")
    parser.add_argument("--output", type=str, default="", help="Optional JSON output path.")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress bar output.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = Path(args.dataset)
    cases = load_positions(dataset)
    if not cases:
        raise SystemExit(f"No positions found in {dataset}")

    show_progress = not args.no_progress
    total_steps = len(cases) * 5 * args.samples
    done_steps = 0
    start_ts = time.perf_counter()

    def tick() -> None:
        nonlocal done_steps
        done_steps += 1
        if show_progress:
            render_progress(done_steps, total_steps, start_ts)

    if show_progress:
        render_progress(0, total_steps, start_ts)

    merged: Dict[str, List[float]] = {}
    for case in cases:
        case_result = run_case(case, loops=args.loops, samples=args.samples, tick=tick)
        for metric, vals in case_result.items():
            merged.setdefault(f"{metric}:mean", []).append(vals["mean_ns"])
            merged.setdefault(f"{metric}:p95", []).append(vals["p95_ns"])
            merged.setdefault(f"{metric}:p99", []).append(vals["p99_ns"])

    if show_progress:
        print()

    summary: Dict[str, Dict[str, float]] = {}
    metrics = sorted({k.split(":")[0] for k in merged})
    for metric in metrics:
        summary[metric] = {
            "mean_ns": statistics.fmean(merged[f"{metric}:mean"]),
            "p95_ns": statistics.fmean(merged[f"{metric}:p95"]),
            "p99_ns": statistics.fmean(merged[f"{metric}:p99"]),
        }

    print(f"Dataset: {dataset}")
    print(f"Cases: {len(cases)}")
    print_table(summary)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "dataset": str(dataset),
            "cases": len(cases),
            "loops_per_sample": args.loops,
            "samples": args.samples,
            "summary": summary,
        }
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved: {out_path.resolve()}")


if __name__ == "__main__":
    main()
