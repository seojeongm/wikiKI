#!/usr/bin/env python3
"""Sweep commit-batch size and plot us/evict to locate the optimal batch.

Reuses the building blocks from ``bench_evict_lookup`` (same synthetic Zipf
workload, same real-disk DB, same per-evict / batched commit logic) and runs a
finer, log-spaced batch sweep on the two strategies we'd actually ship
(baseline = current code, upsert = SELECT removed). For each batch size it
reports the median us/evict over ``--repeat`` runs, auto-detects the knee of
the curve (diminishing-returns point), and writes a PNG.

The knee is the practical "optimal" batch: past it, extra batching buys little
throughput while only increasing how many evictions a crash could lose.

Usage:
    python scripts/plot_batch_sweep.py
    python scripts/plot_batch_sweep.py --evictions 50000 --repeat 5 --out docs/meeting-notes/batch_sweep.png
"""
from __future__ import annotations

import argparse
import math
import os
import random
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bench_evict_lookup import (  # noqa: E402
    build_titles, fresh_db, prepopulate, run_baseline, run_upsert, zipf_sampler,
)

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def knee_index(xs: list[float], ys: list[float]) -> int:
    """Elbow of a convex-decreasing curve via max distance to the end-chord.

    Computed on **log-log** axes to match the plot (batch sizes are log-spaced
    and us/evict spans an order of magnitude). Using a linear y here would let
    the large early absolute drop dominate and push the knee artificially low.
    Both normalised axes make the distance scale-free.
    """
    lx = [math.log10(x) for x in xs]
    ly = [math.log10(y) for y in ys]
    x0, x1 = lx[0], lx[-1]
    y0, y1 = ly[0], ly[-1]
    nx = [(v - x0) / (x1 - x0) if x1 != x0 else 0.0 for v in lx]
    ny = [(v - y0) / (y1 - y0) if y1 != y0 else 0.0 for v in ly]
    # perpendicular distance of each point to the line (0,0)->(1,1)
    best_i, best_d = 0, -1.0
    for i in range(len(xs)):
        d = abs(ny[i] - nx[i]) / math.sqrt(2)
        if d > best_d:
            best_d, best_i = d, i
    return best_i


def measure(strategy, run_fn, batches, args, titles, stream):
    n = len(stream)
    meds, lo, hi = [], [], []
    for b in batches:
        samples = []
        for _ in range(args.repeat):
            conn = fresh_db(args.db)
            prepopulate(conn, titles, args.prepopulate, random.Random(args.seed))
            dt, _lookups, _extra = run_fn(conn, stream, b)
            conn.close()
            samples.append(dt / n * 1e6)
        meds.append(statistics.median(samples))
        lo.append(min(samples))
        hi.append(max(samples))
        print(f"  {strategy:<9} batch={b:<5} median={meds[-1]:7.2f} us/evict "
              f"(min {lo[-1]:.2f}, max {hi[-1]:.2f})")
    return meds, lo, hi


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--titles", type=int, default=50_000)
    ap.add_argument("--evictions", type=int, default=50_000)
    ap.add_argument("--zipf", type=float, default=1.05)
    ap.add_argument("--prepopulate", type=float, default=0.30)
    ap.add_argument("--repeat", type=int, default=5)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--db", default="./bench_evict.db")
    ap.add_argument("--batches", default="1,2,4,8,16,32,64,128,256,512")
    ap.add_argument("--out", default="docs/meeting-notes/batch_sweep.png")
    args = ap.parse_args()

    batches = [int(x) for x in args.batches.split(",")]

    rng = random.Random(args.seed)
    titles = build_titles(args.titles)
    draw = zipf_sampler(args.titles, args.zipf, rng)
    stream = [(titles[draw()], rng.randint(1, 10)) for _ in range(args.evictions)]

    print(f"sweep: titles={args.titles:,} evictions={args.evictions:,} "
          f"zipf={args.zipf} repeat={args.repeat} batches={batches}")
    base_med, base_lo, base_hi = measure("baseline", run_baseline, batches, args, titles, stream)
    up_med, up_lo, up_hi = measure("upsert", run_upsert, batches, args, titles, stream)

    ki = knee_index(batches, base_med)
    knee_b, knee_y = batches[ki], base_med[ki]
    floor = base_med[-1]
    speedup = base_med[0] / knee_y
    print(f"\nknee (baseline): batch={knee_b}  -> {knee_y:.2f} us/evict "
          f"({speedup:.1f}x vs batch=1; floor ~{floor:.2f} us/evict at batch={batches[-1]})")

    # --- plot ---
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.fill_between(batches, base_lo, base_hi, alpha=0.15, color="C0")
    ax.plot(batches, base_med, "o-", color="C0", label="baseline (SELECT then UP/INSERT)")
    ax.fill_between(batches, up_lo, up_hi, alpha=0.15, color="C1")
    ax.plot(batches, up_med, "s-", color="C1", label="upsert (no SELECT)")

    ax.axvline(knee_b, color="C3", ls="--", lw=1.2)
    ax.annotate(f"knee ≈ batch {knee_b}\n{knee_y:.1f} us/evict ({speedup:.0f}x)",
                xy=(knee_b, knee_y), xytext=(knee_b * 1.3, knee_y * 2.2),
                color="C3", fontsize=9,
                arrowprops=dict(arrowstyle="->", color="C3"))

    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xticks(batches)
    ax.set_xticklabels([str(b) for b in batches])
    ax.set_xlabel("commit batch size (evictions per commit, log2)")
    ax.set_ylabel("us / evict  (median of %d runs, log)" % args.repeat)
    ax.set_title("Eviction-path cost vs commit batch size\n"
                 f"({args.evictions:,} evicts, Zipf {args.zipf}, ext4/NVMe)")
    ax.grid(True, which="both", ls=":", alpha=0.5)
    ax.legend()
    fig.tight_layout()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    fig.savefig(args.out, dpi=130)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
