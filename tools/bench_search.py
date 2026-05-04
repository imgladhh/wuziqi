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

from gomoku_core import BLACK, GameBoard, GomokuAI, Move


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


class CountingDict(dict):
    def __init__(self) -> None:
        super().__init__()
        self.get_calls = 0
        self.hit_calls = 0

    def get(self, key, default=None):  # type: ignore[override]
        self.get_calls += 1
        if key in self:
            self.hit_calls += 1
        return super().get(key, default)

    def clear(self) -> None:  # type: ignore[override]
        super().clear()
        self.get_calls = 0
        self.hit_calls = 0


class InstrumentedAI(GomokuAI):
    def __init__(self, disable_forced: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self.disable_forced = disable_forced
        self.nodes = 0
        self.q_nodes = 0
        self.cutoffs = 0
        self.forcing_calls = 0
        self.used_forced_root = False
        self.vcf_root_calls = 0
        self.vcf_root_hits = 0
        self.last_root_score = 0
        self._tt = CountingDict()

    def best_move(self, board: GameBoard, ai_stone: int) -> Move:
        self.nodes = 0
        self.q_nodes = 0
        self.cutoffs = 0
        self.forcing_calls = 0
        self.used_forced_root = False
        self.vcf_root_calls = 0
        self.vcf_root_hits = 0
        self.last_root_score = 0
        return super().best_move(board, ai_stone)

    def _forced_move(self, *args, **kwargs):  # type: ignore[override]
        if self.disable_forced:
            return None
        move = super()._forced_move(*args, **kwargs)
        if move is not None and self.nodes == 0:
            self.used_forced_root = True
        return move

    def _minimax(self, *args, **kwargs):  # type: ignore[override]
        self.nodes += 1
        return super()._minimax(*args, **kwargs)

    def _quiescence(self, *args, **kwargs):  # type: ignore[override]
        self.q_nodes += 1
        return super()._quiescence(*args, **kwargs)

    def _record_cutoff(self, *args, **kwargs):  # type: ignore[override]
        self.cutoffs += 1
        return super()._record_cutoff(*args, **kwargs)

    def _forcing_moves(self, *args, **kwargs):  # type: ignore[override]
        self.forcing_calls += 1
        return super()._forcing_moves(*args, **kwargs)

    def _vcf_probe_root(self, *args, **kwargs):  # type: ignore[override]
        self.vcf_root_calls += 1
        move = super()._vcf_probe_root(*args, **kwargs)
        if move is not None:
            self.vcf_root_hits += 1
        return move

    def _search_root(self, *args, **kwargs):  # type: ignore[override]
        best, score = super()._search_root(*args, **kwargs)
        self.last_root_score = score
        return best, score

    @property
    def tt_hit_rate(self) -> float:
        if self._tt.get_calls == 0:
            return 0.0
        return self._tt.hit_calls / float(self._tt.get_calls)


@dataclass
class PositionCase:
    case_id: str
    size: int
    moves: List[Tuple[int, int, int]]
    side_to_move: int
    tags: List[str]


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
                tags=[str(t) for t in item.get("tags", [])],
            )
        )
    return cases


def build_board(case: PositionCase) -> GameBoard:
    board = GameBoard(size=case.size)
    for x, y, stone in case.moves:
        board.place(x, y, stone)
    return board


def evaluate_case(ai: InstrumentedAI, case: PositionCase, repeat: int) -> Dict[str, object]:
    board = build_board(case)
    before = board.focused_candidate_moves(distance=2, limit_area=6) or board.candidate_moves()
    ordered = ai._sorted_moves(board, before, case.side_to_move, ply=0) if before else []
    first_candidate = (ordered[0].x, ordered[0].y) if ordered else None

    elapsed_samples: List[float] = []
    best_samples: List[Tuple[int, int]] = []
    nodes_samples: List[int] = []
    qnodes_samples: List[int] = []
    cutoffs_samples: List[int] = []
    tt_hit_samples: List[float] = []
    forcing_samples: List[int] = []
    forced_root_samples: List[float] = []
    vcf_impact_samples: List[float] = []
    root_score_samples: List[float] = []

    for _ in range(repeat):
        sample_board = build_board(case)
        t0 = time.perf_counter()
        move = ai.best_move(sample_board, case.side_to_move)
        dt_ms = (time.perf_counter() - t0) * 1000.0

        elapsed_samples.append(dt_ms)
        best_samples.append((move.x, move.y))
        nodes_samples.append(ai.nodes)
        qnodes_samples.append(ai.q_nodes)
        cutoffs_samples.append(ai.cutoffs)
        tt_hit_samples.append(ai.tt_hit_rate)
        forcing_samples.append(ai.forcing_calls)
        forced_root_samples.append(1.0 if ai.used_forced_root else 0.0)
        vcf_impact_samples.append(1.0 if ai.vcf_root_hits > 0 else 0.0)
        root_score_samples.append(float(ai.last_root_score))

    best_majority = max(set(best_samples), key=best_samples.count)
    stable_ratio = best_samples.count(best_majority) / float(len(best_samples))
    first_is_final = first_candidate == best_majority if first_candidate is not None else False
    return {
        "id": case.case_id,
        "tags": case.tags,
        "best_move": list(best_majority),
        "stability": stable_ratio,
        "first_candidate_is_final": first_is_final,
        "time_ms_mean": statistics.fmean(elapsed_samples),
        "nodes_mean": statistics.fmean(nodes_samples),
        "q_nodes_mean": statistics.fmean(qnodes_samples),
        "q_ratio": statistics.fmean(qnodes_samples) / max(1.0, statistics.fmean(nodes_samples)),
        "cutoffs_mean": statistics.fmean(cutoffs_samples),
        "tt_hit_rate_mean": statistics.fmean(tt_hit_samples),
        "forcing_calls_mean": statistics.fmean(forcing_samples),
        "forced_root_rate": statistics.fmean(forced_root_samples),
        "vcf_impact_rate": statistics.fmean(vcf_impact_samples),
        "root_score_volatility": statistics.pstdev(root_score_samples) if len(root_score_samples) > 1 else 0.0,
        "iterative_depth": ai._iterative_depth,
    }


def summarize(results: List[Dict[str, object]]) -> Dict[str, float]:
    time_ms_mean = statistics.fmean([float(r["time_ms_mean"]) for r in results])
    nodes_mean = statistics.fmean([float(r["nodes_mean"]) for r in results])
    q_nodes_mean = statistics.fmean([float(r["q_nodes_mean"]) for r in results])
    nps = ((nodes_mean + q_nodes_mean) * 1000.0 / time_ms_mean) if time_ms_mean > 1e-9 else 0.0
    return {
        "cases": float(len(results)),
        "time_ms_mean": time_ms_mean,
        "nodes_mean": nodes_mean,
        "q_nodes_mean": q_nodes_mean,
        "q_ratio_mean": statistics.fmean([float(r["q_ratio"]) for r in results]),
        "cutoffs_mean": statistics.fmean([float(r["cutoffs_mean"]) for r in results]),
        "tt_hit_rate_mean": statistics.fmean([float(r["tt_hit_rate_mean"]) for r in results]),
        "forcing_calls_mean": statistics.fmean([float(r["forcing_calls_mean"]) for r in results]),
        "forced_root_rate_mean": statistics.fmean([float(r["forced_root_rate"]) for r in results]),
        "vcf_impact_rate_mean": statistics.fmean([float(r["vcf_impact_rate"]) for r in results]),
        "root_score_volatility_mean": statistics.fmean([float(r["root_score_volatility"]) for r in results]),
        "avg_depth_mean": statistics.fmean([float(r["iterative_depth"]) for r in results]),
        "nps_estimate": nps,
        "stability_mean": statistics.fmean([float(r["stability"]) for r in results]),
        "first_candidate_final_rate": statistics.fmean(
            [1.0 if bool(r["first_candidate_is_final"]) else 0.0 for r in results]
        ),
        "first_move_fail_high_proxy": 1.0
        - statistics.fmean([1.0 if bool(r["first_candidate_is_final"]) else 0.0 for r in results]),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Search-quality benchmark for fixed Gomoku positions.")
    parser.add_argument("--dataset", type=str, default="bench/midgame.json")
    parser.add_argument("--depth", type=int, default=3)
    parser.add_argument("--time-ms", type=int, default=800)
    parser.add_argument("--repeat", type=int, default=3, help="Repeat searches per position.")
    parser.add_argument("--disable-forced", action="store_true", help="Disable forced-move shortcut for profiling tree stats.")
    parser.add_argument("--disable-opening-book", action="store_true", help="Disable opening-book shortcut in benchmark runs.")
    parser.add_argument("--disable-vcf-vct", action="store_true", help="Disable VCF/VCT root probes in benchmark runs.")
    parser.add_argument("--disable-defense-urgency", action="store_true", help="Disable defensive urgency adjustment.")
    parser.add_argument("--enemy-threat-scale", type=float, default=1.35, help="Enemy threat penalty scale.")
    parser.add_argument("--vcf-max-nodes", type=int, default=1800)
    parser.add_argument("--vct-max-nodes", type=int, default=2500)
    parser.add_argument("--vcf-width-attack", type=int, default=8)
    parser.add_argument("--vcf-width-defense", type=int, default=10)
    parser.add_argument("--vct-width-attack", type=int, default=10)
    parser.add_argument("--vct-width-defense", type=int, default=12)
    parser.add_argument("--output", type=str, default="", help="Optional JSON output path.")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress bar output.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dataset = Path(args.dataset)
    cases = load_positions(dataset)
    if not cases:
        raise SystemExit(f"No positions found in {dataset}")

    ai = InstrumentedAI(
        depth=args.depth,
        time_limit_ms=args.time_ms,
        use_pvs=True,
        use_quiescence=True,
        use_threat_space=True,
        use_opening_book=not bool(args.disable_opening_book),
        use_vcf_probe=not bool(args.disable_vcf_vct),
        use_vct_probe=not bool(args.disable_vcf_vct),
        use_defense_urgency=not bool(args.disable_defense_urgency),
        enemy_threat_penalty_scale=float(args.enemy_threat_scale),
        vcf_max_nodes=int(args.vcf_max_nodes),
        vct_max_nodes=int(args.vct_max_nodes),
        vcf_max_width_attack=int(args.vcf_width_attack),
        vcf_max_width_defense=int(args.vcf_width_defense),
        vct_max_width_attack=int(args.vct_width_attack),
        vct_max_width_defense=int(args.vct_width_defense),
        use_lazy_smp=False,
        disable_forced=bool(args.disable_forced),
    )
    show_progress = not args.no_progress
    total_steps = len(cases) * max(1, args.repeat)
    done_steps = 0
    start_ts = time.perf_counter()
    if show_progress:
        render_progress(0, total_steps, start_ts)

    per_case: List[Dict[str, object]] = []
    for case in cases:
        per_case.append(evaluate_case(ai, case, repeat=max(1, args.repeat)))
        done_steps += max(1, args.repeat)
        if show_progress:
            render_progress(done_steps, total_steps, start_ts)

    if show_progress:
        print()
    summary = summarize(per_case)

    print(f"Dataset: {dataset}")
    print(f"Cases: {len(cases)}")
    print("| Metric | Value |")
    print("|---|---:|")
    for k, v in summary.items():
        print(f"| {k} | {v:.4f} |")

    payload = {
        "dataset": str(dataset),
        "depth": args.depth,
        "time_ms": args.time_ms,
        "repeat": args.repeat,
        "summary": summary,
        "per_case": per_case,
    }
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved: {out.resolve()}")


if __name__ == "__main__":
    main()
