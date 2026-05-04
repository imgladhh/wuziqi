from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.eval_elo import EngineConfig, EvalResult, run_evaluation


@dataclass
class Profile:
    name: str
    config: EngineConfig
    bench_flags: List[str]


def parse_elo_from_report(path: Path) -> Tuple[float, float, float]:
    text = path.read_text(encoding="utf-8")
    elo = 0.0
    ci_low = 0.0
    ci_high = 0.0
    for line in text.splitlines():
        if line.startswith("- Elo(A-B):"):
            elo = float(line.split(":", 1)[1].strip())
        if line.startswith("- Elo 95% CI:"):
            raw = line.split("[", 1)[1].split("]", 1)[0]
            left, right = raw.split(",")
            ci_low = float(left.strip())
            ci_high = float(right.strip())
    return elo, ci_low, ci_high


def run_bench_search(
    profile: Profile,
    *,
    depth: int,
    time_ms: int,
    repeat: int,
    output: Path,
    no_progress: bool,
) -> Dict[str, float]:
    cmd = [
        sys.executable,
        str(ROOT / "tools" / "bench_search.py"),
        "--dataset",
        str(ROOT / "bench" / "midgame.json"),
        "--depth",
        str(depth),
        "--time-ms",
        str(time_ms),
        "--repeat",
        str(repeat),
        "--disable-forced",
        "--disable-opening-book",
        "--output",
        str(output),
    ]
    cmd.extend(profile.bench_flags)
    if no_progress:
        cmd.append("--no-progress")
    subprocess.run(cmd, cwd=str(ROOT), check=True)
    payload = json.loads(output.read_text(encoding="utf-8"))
    summary = payload.get("summary", {})
    return {k: float(v) for k, v in summary.items() if isinstance(v, (int, float))}


def write_matrix_report(
    path: Path,
    *,
    games: int,
    baseline: Profile,
    rows: List[Tuple[Profile, EvalResult, Dict[str, float]]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    lines.append("# Phase-1 Ablation Matrix Report")
    lines.append("")
    lines.append(f"- Games per profile: {games}")
    lines.append(f"- Baseline: `{baseline.name}`")
    lines.append("")
    lines.append("| Profile(B) | Elo(B-A) | 95% CI | NPS(est) | AvgDepth | VCF Impact | Root Volatility | 1st-move Fail-high(proxy) |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for profile, result, bench in rows:
        elo_b_minus_a = -result.elo_a_minus_b
        ci_low = -result.elo_high_a_minus_b
        ci_high = -result.elo_low_a_minus_b
        lines.append(
            f"| {profile.name} | {elo_b_minus_a:.2f} | [{ci_low:.2f}, {ci_high:.2f}] | "
            f"{bench.get('nps_estimate', 0.0):.2f} | {bench.get('avg_depth_mean', 0.0):.2f} | "
            f"{bench.get('vcf_impact_rate_mean', 0.0):.4f} | {bench.get('root_score_volatility_mean', 0.0):.2f} | "
            f"{bench.get('first_move_fail_high_proxy', 0.0):.4f} |"
        )
    lines.append("")
    lines.append("Rule of thumb: if Elo(B-A) > 0 and CI mostly above 0, profile B is a likely upgrade.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run Phase-1 A/B/C/D/E ablation matrix for Elo-oriented tuning.")
    p.add_argument("--games", type=int, default=400)
    p.add_argument("--board-size", type=int, default=15)
    p.add_argument("--opening-plies", type=int, default=4)
    p.add_argument("--seed", type=int, default=20260418)
    p.add_argument("--depth-a", type=int, default=3)
    p.add_argument("--depth-b", type=int, default=3)
    p.add_argument("--time-a", type=int, default=500)
    p.add_argument("--time-b", type=int, default=500)
    p.add_argument("--bench-depth", type=int, default=3)
    p.add_argument("--bench-time-ms", type=int, default=800)
    p.add_argument("--bench-repeat", type=int, default=3)
    p.add_argument("--output", type=str, default="reports/ablation_matrix.md")
    p.add_argument("--no-progress", action="store_true")
    p.add_argument("--competitive", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    show_progress = not args.no_progress

    baseline = Profile(
        name="A_baseline",
        config=EngineConfig(
            name="A_baseline",
            depth=args.depth_a,
            time_ms=args.time_a,
            use_pvs=True,
            use_quiescence=True,
            use_threat_space=True,
            use_vcf_probe=True,
            use_vct_probe=True,
            use_defense_urgency=True,
            enemy_threat_penalty_scale=1.35,
        ),
        bench_flags=[],
    )

    profiles: List[Profile] = [
        Profile(
            name="B_p3_off",
            config=EngineConfig(
                name="B_p3_off",
                depth=args.depth_b,
                time_ms=args.time_b,
                use_pvs=True,
                use_quiescence=True,
                use_threat_space=True,
                use_vcf_probe=True,
                use_vct_probe=True,
                use_defense_urgency=False,
                enemy_threat_penalty_scale=1.0,
            ),
            bench_flags=["--disable-defense-urgency", "--enemy-threat-scale", "1.0"],
        ),
        Profile(
            name="C_vcf_off",
            config=EngineConfig(
                name="C_vcf_off",
                depth=args.depth_b,
                time_ms=args.time_b,
                use_pvs=True,
                use_quiescence=True,
                use_threat_space=True,
                use_vcf_probe=False,
                use_vct_probe=False,
                use_defense_urgency=True,
                enemy_threat_penalty_scale=1.35,
            ),
            bench_flags=["--disable-vcf-vct"],
        ),
        Profile(
            name="D_p3_half_strict_vcf",
            config=EngineConfig(
                name="D_p3_half_strict_vcf",
                depth=args.depth_b,
                time_ms=args.time_b,
                use_pvs=True,
                use_quiescence=True,
                use_threat_space=True,
                use_vcf_probe=True,
                use_vct_probe=True,
                use_defense_urgency=True,
                enemy_threat_penalty_scale=1.15,
                vcf_max_nodes=900,
                vct_max_nodes=1200,
                vcf_max_width_attack=6,
                vcf_max_width_defense=8,
                vct_max_width_attack=7,
                vct_max_width_defense=9,
            ),
            bench_flags=[
                "--enemy-threat-scale",
                "1.15",
                "--vcf-max-nodes",
                "900",
                "--vct-max-nodes",
                "1200",
                "--vcf-width-attack",
                "6",
                "--vcf-width-defense",
                "8",
                "--vct-width-attack",
                "7",
                "--vct-width-defense",
                "9",
            ],
        ),
        Profile(
            name="E_p3_half_only",
            config=EngineConfig(
                name="E_p3_half_only",
                depth=args.depth_b,
                time_ms=args.time_b,
                use_pvs=True,
                use_quiescence=True,
                use_threat_space=True,
                use_vcf_probe=True,
                use_vct_probe=True,
                use_defense_urgency=True,
                enemy_threat_penalty_scale=1.15,
            ),
            bench_flags=["--enemy-threat-scale", "1.15"],
        ),
    ]

    rows: List[Tuple[Profile, EvalResult, Dict[str, float]]] = []
    for i, profile in enumerate(profiles, start=1):
        title = f"[{i}/{len(profiles)}] baseline vs {profile.name}"
        result = run_evaluation(
            board_size=args.board_size,
            opening_plies=args.opening_plies,
            seed=args.seed + i * 101,
            competitive=bool(args.competitive),
            games=max(2, args.games),
            config_a=baseline.config,
            config_b=profile.config,
            show_progress=show_progress,
            progress_title=title,
        )
        bench_output = ROOT / "reports" / f"bench_{profile.name}.json"
        bench = run_bench_search(
            profile,
            depth=args.bench_depth,
            time_ms=args.bench_time_ms,
            repeat=args.bench_repeat,
            output=bench_output,
            no_progress=not show_progress,
        )
        rows.append((profile, result, bench))
        elo_b_minus_a = -result.elo_a_minus_b
        ci_low = -result.elo_high_a_minus_b
        ci_high = -result.elo_low_a_minus_b
        print(f"{profile.name}: Elo(B-A) {elo_b_minus_a:.2f} [{ci_low:.2f}, {ci_high:.2f}]")

    out_path = ROOT / args.output
    write_matrix_report(out_path, games=max(2, args.games), baseline=baseline, rows=rows)
    print(f"Matrix report: {out_path.resolve()}")


if __name__ == "__main__":
    main()
