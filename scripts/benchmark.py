"""Monte Carlo GPU-vs-CPU benchmark — the pitch's measured AMD evidence.

Runs the same simulation on CPU and (if available) the GPU across a sweep of
run counts, prints a table, and writes it to `evidence/benchmark.json`. On a
dev laptop this produces the CPU baseline; on any AMD Instinct GPU under ROCm
it produces the real "X s on CPU → Y s on <self-reported device>" number, so
the pitch quotes the hardware actually used rather than an assumed one
(ARCHITECTURE.md §9, CLAUDE.md AMD story #2). Nothing here is estimated —
every number is measured.

Run:
    python scripts/benchmark.py                 # CPU (+ GPU if present)
    python scripts/benchmark.py --runs 10000 50000 100000
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import torch  # noqa: E402

from backend.device import device_label
from backend.simulation.monte_carlo import run_simulation  # noqa: E402
from scripts.seed_events import load_seed_events  # noqa: E402

EVENT_ID = "seed-FL-001"  # the Jakarta flood — the demo's star event
WARMUP_RUNS = 2000


def _time_run(event, n_runs: int, force_cpu: bool) -> tuple[float, float, str]:
    out = run_simulation(event, horizon="24h", n_runs=n_runs, force_cpu=force_cpu, seed=42)
    return out.metrics.wall_ms, out.metrics.runs_per_sec, out.metrics.device


def main() -> int:
    parser = argparse.ArgumentParser(description="Monte Carlo GPU-vs-CPU benchmark")
    parser.add_argument(
        "--runs", type=int, nargs="+", default=[10_000, 50_000, 100_000],
        help="run counts to sweep",
    )
    parser.add_argument("--repeats", type=int, default=3, help="best-of-N per point")
    args = parser.parse_args()

    event = next(e for e in load_seed_events() if e.id == EVENT_ID)
    has_gpu = torch.cuda.is_available()
    # device_label(): ROCm returns an empty name on some cards (gfx1100).
    device_name = device_label(0) if has_gpu else "no GPU"
    print(f"Monte Carlo benchmark — event={EVENT_ID}, GPU: {device_name}\n")

    # Warm up both paths (first call pays allocator/JIT costs).
    _time_run(event, WARMUP_RUNS, force_cpu=True)
    if has_gpu:
        _time_run(event, WARMUP_RUNS, force_cpu=False)
        torch.cuda.synchronize()

    header = f"{'runs':>10} {'CPU ms':>10} {'GPU ms':>10} {'speedup':>9} {'GPU runs/s':>14}"
    print(header)
    print("-" * len(header))

    rows = []
    for n in args.runs:
        cpu_ms = min(_time_run(event, n, force_cpu=True)[0] for _ in range(args.repeats))
        if has_gpu:
            gpu_ms, gpu_rps, _ = min(
                (_time_run(event, n, force_cpu=False) for _ in range(args.repeats)),
                key=lambda t: t[0],
            )
            speedup = cpu_ms / gpu_ms if gpu_ms > 0 else float("inf")
            print(f"{n:>10,} {cpu_ms:>10.1f} {gpu_ms:>10.1f} {speedup:>8.1f}x {gpu_rps:>14,.0f}")
            rows.append({"runs": n, "cpu_ms": round(cpu_ms, 1), "gpu_ms": round(gpu_ms, 1),
                         "speedup": round(speedup, 1), "gpu_runs_per_sec": round(gpu_rps)})
        else:
            cpu_rps = n / (cpu_ms / 1000.0)
            cpu_label = f"cpu {cpu_rps:,.0f}/s"
            print(f"{n:>10,} {cpu_ms:>10.1f} {'-':>10} {'-':>9} {cpu_label:>14}")
            rows.append({"runs": n, "cpu_ms": round(cpu_ms, 1), "cpu_runs_per_sec": round(cpu_rps)})

    out_dir = _ROOT / "evidence"
    out_dir.mkdir(exist_ok=True)
    payload = {"event": EVENT_ID, "device": device_name, "has_gpu": has_gpu, "rows": rows}
    (out_dir / "benchmark.json").write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {out_dir / 'benchmark.json'}")
    if not has_gpu:
        print("NOTE: no GPU here — run this on the AMD GPU host for the AMD number.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
