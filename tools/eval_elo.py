from __future__ import annotations

import argparse
import math
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gomoku_core import BLACK, EMPTY, WHITE, GameBoard, GomokuAI, is_forbidden_move, opponent


@dataclass
class EngineConfig:
    name: str
    depth: int
    time_ms: int
    use_pvs: bool
    use_quiescence: bool
    use_threat_space: bool
    use_lmr: bool = True
    use_segment_core_eval: bool = False
    use_vcf_probe: bool = True
    use_vct_probe: bool = True
    use_defense_urgency: bool = True
    enemy_threat_penalty_scale: float = 1.35
    enemy_pattern_scale: float = 1.0
    score_open_four: int = 240_000
    score_half_four: int = 62_000
    score_open_three: int = 28_000
    score_half_three: int = 6_200
    score_open_two: int = 1_500
    score_half_two: int = 360
    own_win_point_bonus: int = 170_000
    enemy_win_point_penalty: int = 420_000
    own_open_four_bonus: int = 85_000
    enemy_open_four_penalty: int = 160_000
    enemy_major_threat_penalty: int = 42_000
    vcf_max_nodes: int = 1800
    vcf_max_width_attack: int = 8
    vcf_max_width_defense: int = 10
    vct_max_nodes: int = 2500
    vct_max_width_attack: int = 10
    vct_max_width_defense: int = 12


@dataclass
class MatchResult:
    winner: int
    moves: int
    avg_move_time_a_ms: float
    avg_move_time_b_ms: float
    opening: List[Tuple[int, int, int]]


@dataclass
class EvalResult:
    games: int
    score_a: float
    elo_a_minus_b: float
    elo_low_a_minus_b: float
    elo_high_a_minus_b: float
    avg_moves: float
    avg_time_a_ms: float
    avg_time_b_ms: float


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


def legal_checker(board: GameBoard, x: int, y: int, stone: int) -> bool:
    if stone != BLACK:
        return True
    return not is_forbidden_move(board, x, y, stone)


def build_ai(config: EngineConfig, competitive: bool) -> GomokuAI:
    return GomokuAI(
        depth=config.depth,
        time_limit_ms=config.time_ms,
        legal_move_checker=legal_checker if competitive else None,
        use_pvs=config.use_pvs,
        use_quiescence=config.use_quiescence,
        use_threat_space=config.use_threat_space,
        use_lmr=config.use_lmr,
        use_segment_core_eval=config.use_segment_core_eval,
        use_vcf_probe=config.use_vcf_probe,
        use_vct_probe=config.use_vct_probe,
        use_defense_urgency=config.use_defense_urgency,
        enemy_threat_penalty_scale=config.enemy_threat_penalty_scale,
        enemy_pattern_scale=config.enemy_pattern_scale,
        score_open_four=config.score_open_four,
        score_half_four=config.score_half_four,
        score_open_three=config.score_open_three,
        score_half_three=config.score_half_three,
        score_open_two=config.score_open_two,
        score_half_two=config.score_half_two,
        own_win_point_bonus=config.own_win_point_bonus,
        enemy_win_point_penalty=config.enemy_win_point_penalty,
        own_open_four_bonus=config.own_open_four_bonus,
        enemy_open_four_penalty=config.enemy_open_four_penalty,
        enemy_major_threat_penalty=config.enemy_major_threat_penalty,
        vcf_max_nodes=config.vcf_max_nodes,
        vcf_max_width_attack=config.vcf_max_width_attack,
        vcf_max_width_defense=config.vcf_max_width_defense,
        vct_max_nodes=config.vct_max_nodes,
        vct_max_width_attack=config.vct_max_width_attack,
        vct_max_width_defense=config.vct_max_width_defense,
    )


def fallback_legal_move(board: GameBoard, stone: int, competitive: bool) -> Tuple[int, int]:
    for move in board.candidate_moves():
        if board.get(move.x, move.y) != EMPTY:
            continue
        if competitive and stone == BLACK and is_forbidden_move(board, move.x, move.y, stone):
            continue
        return move.x, move.y
    center = board.size // 2
    return center, center


def generate_opening(
    board_size: int,
    opening_plies: int,
    rng: random.Random,
    competitive: bool,
) -> List[Tuple[int, int, int]]:
    board = GameBoard(size=board_size)
    opening: List[Tuple[int, int, int]] = []
    current = BLACK
    for _ in range(opening_plies):
        if board.is_game_over:
            break
        candidates = board.focused_candidate_moves(distance=2, limit_area=6)
        if not candidates:
            candidates = board.candidate_moves()
        legal: List[Tuple[int, int]] = []
        for move in candidates:
            if board.get(move.x, move.y) != EMPTY:
                continue
            if competitive and current == BLACK and is_forbidden_move(board, move.x, move.y, BLACK):
                continue
            legal.append((move.x, move.y))
        if not legal:
            x, y = fallback_legal_move(board, current, competitive)
        else:
            x, y = legal[rng.randrange(len(legal))]
        if not board.place(x, y, current):
            break
        opening.append((x, y, current))
        current = opponent(current)
    return opening


def play_game(
    board_size: int,
    opening: Sequence[Tuple[int, int, int]],
    config_a: EngineConfig,
    config_b: EngineConfig,
    a_is_black: bool,
    competitive: bool,
    max_moves: int = 225,
) -> MatchResult:
    board = GameBoard(size=board_size)
    for x, y, stone in opening:
        if board.get(x, y) != EMPTY:
            continue
        board.place(x, y, stone)

    ai_a = build_ai(config_a, competitive)
    ai_b = build_ai(config_b, competitive)

    owner_by_stone = {
        BLACK: "A" if a_is_black else "B",
        WHITE: "B" if a_is_black else "A",
    }
    current = BLACK if not opening else opponent(opening[-1][2])

    move_time_a: List[float] = []
    move_time_b: List[float] = []

    while not board.is_game_over and board.move_count < max_moves:
        owner = owner_by_stone[current]
        ai = ai_a if owner == "A" else ai_b
        t0 = time.perf_counter()
        move = ai.best_move(board, current)
        dt_ms = (time.perf_counter() - t0) * 1000.0

        x, y = move.x, move.y
        illegal = not board.is_inside(x, y) or board.get(x, y) != EMPTY
        forbidden = competitive and current == BLACK and is_forbidden_move(board, x, y, current)
        if illegal or forbidden:
            x, y = fallback_legal_move(board, current, competitive)
        placed = board.place(x, y, current)
        if not placed:
            x, y = fallback_legal_move(board, current, competitive)
            if not board.place(x, y, current):
                break

        if owner == "A":
            move_time_a.append(dt_ms)
        else:
            move_time_b.append(dt_ms)
        current = opponent(current)

    return MatchResult(
        winner=board.winner,
        moves=board.move_count,
        avg_move_time_a_ms=(sum(move_time_a) / len(move_time_a)) if move_time_a else 0.0,
        avg_move_time_b_ms=(sum(move_time_b) / len(move_time_b)) if move_time_b else 0.0,
        opening=list(opening),
    )


def score_for_a(result: MatchResult, a_is_black: bool) -> float:
    if result.winner == EMPTY:
        return 0.5
    if a_is_black:
        return 1.0 if result.winner == BLACK else 0.0
    return 1.0 if result.winner == WHITE else 0.0


def elo_from_score(p: float) -> float:
    p = min(0.999, max(0.001, p))
    return -400.0 * math.log10(1.0 / p - 1.0)


def confidence_interval(score: float, n: int) -> Tuple[float, float]:
    if n <= 1:
        return score, score
    se = math.sqrt(max(1e-9, score * (1.0 - score) / n))
    low = max(0.001, score - 1.96 * se)
    high = min(0.999, score + 1.96 * se)
    return low, high


def default_configs(depth_a: int, depth_b: int, time_a: int, time_b: int) -> Tuple[EngineConfig, EngineConfig]:
    baseline = EngineConfig(
        name="baseline",
        depth=depth_a,
        time_ms=time_a,
        use_pvs=False,
        use_quiescence=False,
        use_threat_space=False,
    )
    enhanced = EngineConfig(
        name="enhanced",
        depth=depth_b,
        time_ms=time_b,
        use_pvs=True,
        use_quiescence=True,
        use_threat_space=True,
    )
    return baseline, enhanced


def run_evaluation(
    *,
    board_size: int,
    opening_plies: int,
    seed: int,
    competitive: bool,
    games: int,
    config_a: EngineConfig,
    config_b: EngineConfig,
    show_progress: bool,
    progress_title: Optional[str] = None,
) -> EvalResult:
    rng = random.Random(seed)
    total_games = max(2, games)
    pair_count = (total_games + 1) // 2
    results: List[float] = []
    move_counts: List[int] = []
    times_a: List[float] = []
    times_b: List[float] = []
    start_ts = time.perf_counter()

    if show_progress:
        if progress_title:
            print(progress_title)
        render_progress(done=0, total=total_games, start_ts=start_ts)

    for _ in range(pair_count):
        opening = generate_opening(board_size, opening_plies, rng, competitive)
        g1 = play_game(
            board_size=board_size,
            opening=opening,
            config_a=config_a,
            config_b=config_b,
            a_is_black=True,
            competitive=competitive,
        )
        results.append(score_for_a(g1, a_is_black=True))
        move_counts.append(g1.moves)
        times_a.append(g1.avg_move_time_a_ms)
        times_b.append(g1.avg_move_time_b_ms)
        if show_progress:
            render_progress(done=len(results), total=total_games, start_ts=start_ts)
        if len(results) >= total_games:
            break

        g2 = play_game(
            board_size=board_size,
            opening=opening,
            config_a=config_a,
            config_b=config_b,
            a_is_black=False,
            competitive=competitive,
        )
        results.append(score_for_a(g2, a_is_black=False))
        move_counts.append(g2.moves)
        times_a.append(g2.avg_move_time_a_ms)
        times_b.append(g2.avg_move_time_b_ms)
        if show_progress:
            render_progress(done=len(results), total=total_games, start_ts=start_ts)
        if len(results) >= total_games:
            break

    if show_progress:
        print()

    n = len(results)
    score_a = sum(results) / n if n else 0.5
    elo = elo_from_score(score_a)
    low_p, high_p = confidence_interval(score_a, n)
    elo_low = elo_from_score(low_p)
    elo_high = elo_from_score(high_p)
    avg_moves = sum(move_counts) / len(move_counts) if move_counts else 0.0
    avg_time_a = sum(times_a) / len(times_a) if times_a else 0.0
    avg_time_b = sum(times_b) / len(times_b) if times_b else 0.0
    return EvalResult(
        games=n,
        score_a=score_a,
        elo_a_minus_b=elo,
        elo_low_a_minus_b=elo_low,
        elo_high_a_minus_b=elo_high,
        avg_moves=avg_moves,
        avg_time_a_ms=avg_time_a,
        avg_time_b_ms=avg_time_b,
    )


def write_report(
    output_path: Path,
    config_a: EngineConfig,
    config_b: EngineConfig,
    total_games: int,
    score_a: float,
    elo: float,
    elo_low: float,
    elo_high: float,
    avg_moves: float,
    avg_time_a: float,
    avg_time_b: float,
    competitive: bool,
    seed: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""# Gomoku Elo Evaluation Report

## Setup

- Games: {total_games}
- Competitive mode: {competitive}
- Seed: {seed}
- Engine A: {config_a}
- Engine B: {config_b}

## Results

- Score(A): {score_a:.4f}
- Win rate(A): {score_a * 100:.2f}%
- Elo(A-B): {elo:.2f}
- Elo 95% CI: [{elo_low:.2f}, {elo_high:.2f}]
- Avg moves/game: {avg_moves:.2f}
- Avg move time A (ms): {avg_time_a:.2f}
- Avg move time B (ms): {avg_time_b:.2f}
"""
    output_path.write_text(content, encoding="utf-8")


def ablation_profiles(
    *,
    depth: int,
    time_ms: int,
    mode: str,
) -> List[EngineConfig]:
    profiles = [
        EngineConfig("pvs_only", depth, time_ms, True, False, False),
        EngineConfig("quiescence_only", depth, time_ms, False, True, False),
        EngineConfig("threat_space_only", depth, time_ms, False, False, True),
        EngineConfig("full_enhanced", depth, time_ms, True, True, True),
    ]
    if mode == "all":
        profiles = [
            EngineConfig("pvs_only", depth, time_ms, True, False, False),
            EngineConfig("quiescence_only", depth, time_ms, False, True, False),
            EngineConfig("threat_space_only", depth, time_ms, False, False, True),
            EngineConfig("pvs_quiescence", depth, time_ms, True, True, False),
            EngineConfig("pvs_threat_space", depth, time_ms, True, False, True),
            EngineConfig("quiescence_threat_space", depth, time_ms, False, True, True),
            EngineConfig("full_enhanced", depth, time_ms, True, True, True),
        ]
    return profiles


def write_ablation_report(
    output_path: Path,
    baseline: EngineConfig,
    results: List[Tuple[EngineConfig, EvalResult]],
    *,
    games: int,
    competitive: bool,
    seed: int,
    mode: str,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    lines.append("# Gomoku AI Ablation Report")
    lines.append("")
    lines.append("## Setup")
    lines.append("")
    lines.append(f"- Games per variant: {games}")
    lines.append(f"- Competitive mode: {competitive}")
    lines.append(f"- Seed: {seed}")
    lines.append(f"- Ablation mode: {mode}")
    lines.append(f"- Baseline: {baseline}")
    lines.append("")
    lines.append("## Module Contribution (vs Baseline)")
    lines.append("")
    lines.append("| Variant (B) | Score(A) | Elo(B-A) | 95% CI for Elo(B-A) | Avg moves | Avg time A ms | Avg time B ms |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for profile, result in results:
        elo_b_minus_a = -result.elo_a_minus_b
        elo_b_minus_a_low = -result.elo_high_a_minus_b
        elo_b_minus_a_high = -result.elo_low_a_minus_b
        lines.append(
            "| "
            f"{profile.name} | "
            f"{result.score_a:.4f} | "
            f"{elo_b_minus_a:.2f} | "
            f"[{elo_b_minus_a_low:.2f}, {elo_b_minus_a_high:.2f}] | "
            f"{result.avg_moves:.2f} | "
            f"{result.avg_time_a_ms:.2f} | "
            f"{result.avg_time_b_ms:.2f} |"
        )
    lines.append("")
    lines.append("Interpretation note: positive Elo(B-A) means variant B is stronger than baseline.")
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate Gomoku AI Elo by self-play A/B matches.")
    parser.add_argument("--games", type=int, default=200, help="Total game count (will auto-pair by swapped colors).")
    parser.add_argument("--board-size", type=int, default=15)
    parser.add_argument("--opening-plies", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260416)
    parser.add_argument("--competitive", action="store_true", help="Enable Renju forbidden move rules for black.")
    parser.add_argument("--depth-a", type=int, default=2)
    parser.add_argument("--depth-b", type=int, default=3)
    parser.add_argument("--time-a", type=int, default=800, help="Per-move time budget for engine A (ms).")
    parser.add_argument("--time-b", type=int, default=1200, help="Per-move time budget for engine B (ms).")
    parser.add_argument("--disable-lmr-a", action="store_true", help="Disable LMR for engine A.")
    parser.add_argument("--disable-lmr-b", action="store_true", help="Disable LMR for engine B.")
    parser.add_argument("--enable-segment-core-a", action="store_true", help="Use experimental segment-line core eval for engine A.")
    parser.add_argument("--enable-segment-core-b", action="store_true", help="Use experimental segment-line core eval for engine B.")
    parser.add_argument("--disable-segment-core-a", action="store_true", help="Use the older per-stone core eval for engine A.")
    parser.add_argument("--disable-segment-core-b", action="store_true", help="Use the older per-stone core eval for engine B.")
    parser.add_argument("--output", type=str, default="reports/elo_report.md")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress bar output.")
    parser.add_argument("--ablation", action="store_true", help="Run module ablation suite against baseline in one pass.")
    parser.add_argument(
        "--ablation-mode",
        choices=("single", "all"),
        default="single",
        help="single: pvs/quiescence/threat/full; all: include pairwise combinations.",
    )
    parser.add_argument(
        "--ablation-games",
        type=int,
        default=0,
        help="Games per variant in ablation mode (0 means use --games).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config_a, config_b = default_configs(args.depth_a, args.depth_b, args.time_a, args.time_b)
    if args.disable_lmr_a:
        config_a.use_lmr = False
    if args.disable_lmr_b:
        config_b.use_lmr = False
    if args.enable_segment_core_a:
        config_a.use_segment_core_eval = True
    if args.enable_segment_core_b:
        config_b.use_segment_core_eval = True
    if args.disable_segment_core_a:
        config_a.use_segment_core_eval = False
    if args.disable_segment_core_b:
        config_b.use_segment_core_eval = False
    show_progress = not args.no_progress

    output_path = Path(args.output)

    if args.ablation:
        ab_games = args.ablation_games if args.ablation_games > 0 else args.games
        profiles = ablation_profiles(depth=args.depth_b, time_ms=args.time_b, mode=args.ablation_mode)
        suite_results: List[Tuple[EngineConfig, EvalResult]] = []
        for index, profile in enumerate(profiles, start=1):
            result = run_evaluation(
                board_size=args.board_size,
                opening_plies=args.opening_plies,
                seed=args.seed + 97 * index,
                competitive=args.competitive,
                games=ab_games,
                config_a=config_a,
                config_b=profile,
                show_progress=show_progress,
                progress_title=f"[{index}/{len(profiles)}] baseline vs {profile.name}",
            )
            suite_results.append((profile, result))
            elo_b_minus_a = -result.elo_a_minus_b
            ci_low = -result.elo_high_a_minus_b
            ci_high = -result.elo_low_a_minus_b
            print(
                f"{profile.name}: Elo(B-A) {elo_b_minus_a:.2f} "
                f"[{ci_low:.2f}, {ci_high:.2f}]"
            )

        write_ablation_report(
            output_path=output_path,
            baseline=config_a,
            results=suite_results,
            games=max(2, ab_games),
            competitive=args.competitive,
            seed=args.seed,
            mode=args.ablation_mode,
        )
        print(f"Ablation report: {output_path.resolve()}")
        return

    result = run_evaluation(
        board_size=args.board_size,
        opening_plies=args.opening_plies,
        seed=args.seed,
        competitive=args.competitive,
        games=args.games,
        config_a=config_a,
        config_b=config_b,
        show_progress=show_progress,
    )

    write_report(
        output_path=output_path,
        config_a=config_a,
        config_b=config_b,
        total_games=result.games,
        score_a=result.score_a,
        elo=result.elo_a_minus_b,
        elo_low=result.elo_low_a_minus_b,
        elo_high=result.elo_high_a_minus_b,
        avg_moves=result.avg_moves,
        avg_time_a=result.avg_time_a_ms,
        avg_time_b=result.avg_time_b_ms,
        competitive=args.competitive,
        seed=args.seed,
    )

    print(f"Games: {result.games}")
    print(f"Score(A): {result.score_a:.4f}")
    print(
        f"Elo(A-B): {result.elo_a_minus_b:.2f} "
        f"[{result.elo_low_a_minus_b:.2f}, {result.elo_high_a_minus_b:.2f}]"
    )
    print(f"Report: {output_path.resolve()}")


if __name__ == "__main__":
    main()
