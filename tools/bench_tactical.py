from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gomoku_core import BLACK, GameBoard, GomokuAI, is_forbidden_move


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


@dataclass
class TacticalCase:
    case_id: str
    size: int
    moves: List[Tuple[int, int, int]]
    side_to_move: int
    expected_best: List[Tuple[int, int]]
    tags: List[str]


@dataclass
class RuleCase:
    case_id: str
    size: int
    moves: List[Tuple[int, int, int]]
    check: Tuple[int, int, int]
    expected_forbidden: bool


def load_tactical(path: Path) -> List[TacticalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: List[TacticalCase] = []
    for index, item in enumerate(payload.get("positions", [])):
        expected = [tuple(p) for p in item.get("expected", {}).get("best_moves", [])]
        out.append(
            TacticalCase(
                case_id=str(item.get("id", f"tactical_{index+1}")),
                size=int(item.get("size", 15)),
                moves=[(int(x), int(y), int(s)) for x, y, s in item.get("moves", [])],
                side_to_move=int(item.get("side_to_move", BLACK)),
                expected_best=[(int(x), int(y)) for x, y in expected],
                tags=[str(t) for t in item.get("tags", [])],
            )
        )
    return out


def load_rules(path: Path) -> List[RuleCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: List[RuleCase] = []
    for index, item in enumerate(payload.get("cases", [])):
        x, y, s = item.get("check", [0, 0, BLACK])
        out.append(
            RuleCase(
                case_id=str(item.get("id", f"rule_{index+1}")),
                size=int(item.get("size", 15)),
                moves=[(int(mx), int(my), int(ms)) for mx, my, ms in item.get("moves", [])],
                check=(int(x), int(y), int(s)),
                expected_forbidden=bool(item.get("expected_forbidden", False)),
            )
        )
    return out


def build_board(size: int, moves: List[Tuple[int, int, int]]) -> GameBoard:
    board = GameBoard(size=size)
    for x, y, stone in moves:
        board.place(x, y, stone)
    return board


def eval_tactical_case(ai: GomokuAI, case: TacticalCase) -> Dict[str, object]:
    board = build_board(case.size, case.moves)
    t0 = time.perf_counter()
    move = ai.best_move(board, case.side_to_move)
    dt = (time.perf_counter() - t0) * 1000.0
    predicted = (move.x, move.y)
    hit = predicted in case.expected_best if case.expected_best else True
    return {
        "id": case.case_id,
        "tags": case.tags,
        "predicted": list(predicted),
        "expected": [list(p) for p in case.expected_best],
        "hit": hit,
        "time_ms": dt,
    }


def eval_rule_case(case: RuleCase) -> Dict[str, object]:
    board = build_board(case.size, case.moves)
    x, y, stone = case.check
    predicted = is_forbidden_move(board, x, y, stone)
    return {
        "id": case.case_id,
        "check": [x, y, stone],
        "expected_forbidden": case.expected_forbidden,
        "predicted_forbidden": predicted,
        "hit": predicted == case.expected_forbidden,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tactical and forbidden-rule benchmark.")
    parser.add_argument("--tactical", type=str, default="bench/tactical.json")
    parser.add_argument("--rules", type=str, default="bench/rules.json")
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--time-ms", type=int, default=800)
    parser.add_argument("--enable-segment-core", action="store_true", help="Use experimental incremental segment-line core eval.")
    parser.add_argument("--output", type=str, default="", help="Optional JSON output path.")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress bar output.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tactical_cases = load_tactical(Path(args.tactical))
    rule_cases = load_rules(Path(args.rules))
    if not tactical_cases and not rule_cases:
        raise SystemExit("No benchmark cases found.")

    ai = GomokuAI(
        depth=args.depth,
        time_limit_ms=args.time_ms,
        use_pvs=True,
        use_quiescence=True,
        use_threat_space=True,
        use_segment_core_eval=bool(args.enable_segment_core),
    )

    show_progress = not args.no_progress
    total_steps = len(tactical_cases) + len(rule_cases)
    done_steps = 0
    start_ts = time.perf_counter()
    if show_progress:
        render_progress(0, total_steps, start_ts)

    tactical_results: List[Dict[str, object]] = []
    for case in tactical_cases:
        tactical_results.append(eval_tactical_case(ai, case))
        done_steps += 1
        if show_progress:
            render_progress(done_steps, total_steps, start_ts)

    rule_results: List[Dict[str, object]] = []
    for case in rule_cases:
        rule_results.append(eval_rule_case(case))
        done_steps += 1
        if show_progress:
            render_progress(done_steps, total_steps, start_ts)

    if show_progress:
        print()

    tactical_acc = statistics.fmean([1.0 if r["hit"] else 0.0 for r in tactical_results]) if tactical_results else 0.0
    tactical_time = statistics.fmean([float(r["time_ms"]) for r in tactical_results]) if tactical_results else 0.0
    rules_acc = statistics.fmean([1.0 if r["hit"] else 0.0 for r in rule_results]) if rule_results else 0.0

    print("| Metric | Value |")
    print("|---|---:|")
    print(f"| tactical_cases | {len(tactical_results)} |")
    print(f"| tactical_accuracy | {tactical_acc:.4f} |")
    print(f"| tactical_avg_time_ms | {tactical_time:.2f} |")
    print(f"| rules_cases | {len(rule_results)} |")
    print(f"| rules_accuracy | {rules_acc:.4f} |")

    payload = {
        "tactical_dataset": args.tactical,
        "rules_dataset": args.rules,
        "depth": args.depth,
        "time_ms": args.time_ms,
        "summary": {
            "tactical_cases": len(tactical_results),
            "tactical_accuracy": tactical_acc,
            "tactical_avg_time_ms": tactical_time,
            "rules_cases": len(rule_results),
            "rules_accuracy": rules_acc,
        },
        "tactical_results": tactical_results,
        "rules_results": rule_results,
    }
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved: {out.resolve()}")


if __name__ == "__main__":
    main()
