#!/usr/bin/env python3
"""Benchmark the evict-path existence check in ``accumulate_stats``.

Question under test: the bloom-filter plan wants to skip the
``SELECT 1 FROM article_stats WHERE title = ?`` (storage.py:158) that runs on
every ring-buffer eviction. This script measures whether that SELECT is worth
optimising, and compares four strategies on an identical, replayable workload:

    baseline : current code  -> SELECT, then UPDATE or (count>=3) INSERT
    bloom    : skip SELECT when a bloom filter says "definitely absent"
    exactset : skip SELECT when an in-memory set[str] says absent (no FP)
    upsert   : no SELECT at all -> UPDATE; if rowcount==0 and count>=3, INSERT

It also reports the hit/miss ratio of the evict stream (the single number that
decides whether bloom can help at all) and the bloom false-positive rate.

Pure stdlib (sqlite3 + hashlib); no redis, no third-party bloom lib, so the
hash cost charged to the bloom strategy is real and self-contained.

Usage:
    python scripts/bench_evict_lookup.py
    python scripts/bench_evict_lookup.py --titles 100000 --evictions 500000 --zipf 1.1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sqlite3
import statistics
import time

# --- workload knobs -------------------------------------------------------

def build_titles(n: int) -> list[str]:
    return [f"Article_{i}" for i in range(n)]


def zipf_sampler(n: int, s: float, rng: random.Random):
    """Return a callable drawing an index in [0, n) from a Zipf(s) law.

    Wikipedia edit traffic is heavily skewed: a few hot articles dominate
    evictions. ``s`` controls the skew (higher = more concentrated).
    """
    weights = [1.0 / ((i + 1) ** s) for i in range(n)]
    cum = []
    total = 0.0
    for w in weights:
        total += w
        cum.append(total)
    # normalise the cumulative table to [0, 1)
    cum = [c / total for c in cum]

    def draw() -> int:
        x = rng.random()
        # bisect inline to avoid import noise
        lo, hi = 0, n - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if cum[mid] < x:
                lo = mid + 1
            else:
                hi = mid
        return lo

    return draw


# --- tiny self-contained bloom filter ------------------------------------

class Bloom:
    """Minimal bloom filter using double hashing over a single SHA-256.

    Sized from expected element count ``n`` and target FP rate ``p``.
    Deliberately hand-rolled so the per-lookup hash cost is charged to the
    benchmark exactly as a real deployment would pay it.
    """

    def __init__(self, n: int, p: float = 0.01) -> None:
        n = max(1, n)
        self.m = max(8, int(-n * math.log(p) / (math.log(2) ** 2)))
        self.k = max(1, round((self.m / n) * math.log(2)))
        self.bits = bytearray((self.m + 7) // 8)

    def _slots(self, key: str):
        d = hashlib.sha256(key.encode()).digest()
        h1 = int.from_bytes(d[:8], "big")
        h2 = int.from_bytes(d[8:16], "big") | 1  # odd, so it strides the table
        for i in range(self.k):
            yield (h1 + i * h2) % self.m

    def add(self, key: str) -> None:
        for s in self._slots(key):
            self.bits[s >> 3] |= 1 << (s & 7)

    def __contains__(self, key: str) -> bool:
        for s in self._slots(key):
            if not (self.bits[s >> 3] & (1 << (s & 7))):
                return False
        return True


# --- schema / fixtures ----------------------------------------------------

_CREATE = """
CREATE TABLE article_stats (
    title         TEXT    PRIMARY KEY,
    editor_count  INTEGER NOT NULL,
    revert_count  INTEGER NOT NULL,
    edit_velocity REAL    NOT NULL,
    tension_score REAL    NOT NULL,
    status        TEXT    NOT NULL,
    flags         TEXT    NOT NULL DEFAULT '[]',
    last_seen_at  INTEGER NOT NULL DEFAULT 0
)
"""

_DUMMY = {
    "editor_count": 5, "tension_score": 42.0, "status": "watching",
    "flags": json.dumps(["3RR"]), "last_seen_at": 0,
}


def _fs_of(path: str) -> str:
    """Best-effort filesystem type for *path*'s directory (Linux /proc/mounts).

    Used to warn when the benchmark DB lands on tmpfs (RAM), which would hide
    the fsync cost the benchmark is trying to measure.
    """
    target = os.path.abspath(os.path.dirname(path) or ".")
    best_mount, best_fs = "", "unknown"
    try:
        with open("/proc/mounts") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) < 3:
                    continue
                mount, fstype = parts[1], parts[2]
                if target == mount or target.startswith(mount.rstrip("/") + "/") or mount == "/":
                    if len(mount) >= len(best_mount):
                        best_mount, best_fs = mount, fstype
    except OSError:
        return "unknown"
    return best_fs


def fresh_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("DROP TABLE IF EXISTS article_stats")
    conn.execute(_CREATE)
    conn.commit()
    return conn


def prepopulate(conn: sqlite3.Connection, titles: list[str], frac: float, rng: random.Random):
    """Insert a fraction of titles as already-existing rows (the 'hot' set)."""
    chosen = [t for t in titles if rng.random() < frac]
    conn.executemany(
        "INSERT INTO article_stats "
        "(title, editor_count, revert_count, edit_velocity, tension_score, status, flags, last_seen_at) "
        "VALUES (?, ?, 0, 1, ?, ?, ?, ?)",
        [(t, _DUMMY["editor_count"], _DUMMY["tension_score"], _DUMMY["status"],
          _DUMMY["flags"], _DUMMY["last_seen_at"]) for t in chosen],
    )
    conn.commit()
    return set(chosen)


# --- the four strategies --------------------------------------------------
# Each returns (seconds, sqlite_lookups_issued, extra_dict).
# We commit once per call to mirror accumulate_stats' per-event commit.

def _do_insert(conn, title, count):
    conn.execute(
        "INSERT INTO article_stats "
        "(title, editor_count, revert_count, edit_velocity, tension_score, status, flags, last_seen_at) "
        "VALUES (?, ?, 0, 1, ?, ?, ?, ?)",
        (title, _DUMMY["editor_count"], _DUMMY["tension_score"], _DUMMY["status"],
         _DUMMY["flags"], _DUMMY["last_seen_at"]),
    )


def _do_update(conn, title):
    return conn.execute(
        "UPDATE article_stats SET edit_velocity = edit_velocity + 1, last_seen_at = ? "
        "WHERE title = ?",
        (_DUMMY["last_seen_at"], title),
    ).rowcount


def _maybe_commit(conn, i: int, batch: int, n: int) -> None:
    """Commit every ``batch`` events (and once at the very end).

    ``batch == 1`` reproduces the current per-event commit in
    ``accumulate_stats``; larger values amortise the fsync over N evictions.
    """
    if (i + 1) % batch == 0 or (i + 1) == n:
        conn.commit()


def run_baseline(conn, stream, batch):
    lookups = 0
    n = len(stream)
    t0 = time.perf_counter()
    for i, (title, count) in enumerate(stream):
        row = conn.execute(
            "SELECT 1 FROM article_stats WHERE title = ?", (title,)
        ).fetchone()
        lookups += 1
        if row is None:
            if count >= 3:
                _do_insert(conn, title, count)
        else:
            _do_update(conn, title)
        _maybe_commit(conn, i, batch, n)
    return time.perf_counter() - t0, lookups, {}


def run_skip(conn, stream, present_oracle, oracle_name, batch):
    """bloom / exactset: skip SELECT when the oracle says 'absent'."""
    lookups = 0
    false_pos = 0
    skipped = 0
    n = len(stream)
    t0 = time.perf_counter()
    for i, (title, count) in enumerate(stream):
        if title not in present_oracle:
            # oracle says definitely-absent -> trust it, skip SELECT
            skipped += 1
            if count >= 3:
                _do_insert(conn, title, count)
                present_oracle.add(title)
        else:
            row = conn.execute(
                "SELECT 1 FROM article_stats WHERE title = ?", (title,)
            ).fetchone()
            lookups += 1
            if row is None:
                false_pos += 1  # oracle said maybe-present, DB disagreed
                if count >= 3:
                    _do_insert(conn, title, count)
                    present_oracle.add(title)
            else:
                _do_update(conn, title)
        _maybe_commit(conn, i, batch, n)
    dt = time.perf_counter() - t0
    return dt, lookups, {f"{oracle_name}_skipped": skipped, f"{oracle_name}_false_pos": false_pos}


def run_upsert(conn, stream, batch):
    """No SELECT: UPDATE first; if it touched no row and count>=3, INSERT."""
    lookups = 0  # UPDATEs are the lookups here
    n = len(stream)
    t0 = time.perf_counter()
    for i, (title, count) in enumerate(stream):
        affected = _do_update(conn, title)
        lookups += 1
        if affected == 0 and count >= 3:
            _do_insert(conn, title, count)
        _maybe_commit(conn, i, batch, n)
    return time.perf_counter() - t0, lookups, {}


# --- driver ---------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--titles", type=int, default=50_000, help="distinct article titles")
    ap.add_argument("--evictions", type=int, default=200_000, help="eviction events to replay")
    ap.add_argument("--zipf", type=float, default=1.05, help="Zipf skew (higher=more concentrated)")
    ap.add_argument("--prepopulate", type=float, default=0.30,
                    help="fraction of titles already present in article_stats at start")
    ap.add_argument("--fp", type=float, default=0.01, help="bloom target false-positive rate")
    ap.add_argument("--commit-batch", type=int, default=1,
                    help="commit once per N evictions (1 = current per-event commit)")
    ap.add_argument("--repeat", type=int, default=1,
                    help="run each strategy N times and report the median us/evict")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--db", default="./bench_evict.db",
                    help="DB path. Default is a real-disk path in CWD; avoid /tmp "
                         "as it may be tmpfs (RAM) and hide real fsync cost.")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    titles = build_titles(args.titles)
    draw = zipf_sampler(args.titles, args.zipf, rng)

    # One shared eviction stream replayed identically by every strategy.
    # count: cheap proxy for ring-buffer size at eviction time.
    stream = [(titles[draw()], rng.randint(1, 10)) for _ in range(args.evictions)]

    # Hit/miss against the INITIAL prepopulated set (the number that decides
    # whether a skip-on-absent oracle can ever help).
    n = len(stream)
    cb = args.commit_batch
    db_fs = _fs_of(args.db)
    print(f"workload: titles={args.titles:,}  evictions={args.evictions:,}  "
          f"zipf={args.zipf}  prepopulate={args.prepopulate:.0%}  "
          f"commit_batch={cb}  repeat={args.repeat}")
    print(f"db: {os.path.abspath(args.db)}  (fstype={db_fs})")
    if db_fs == "tmpfs":
        print("  !! WARNING: db is on tmpfs (RAM) -> fsync cost is NOT measured; "
              "pick a real-disk --db path.")

    def run_one(name, conn, present):
        if name == "baseline":
            return run_baseline(conn, stream, cb)
        if name == "upsert":
            return run_upsert(conn, stream, cb)
        if name == "bloom":
            bloom = Bloom(len(present) + args.titles, args.fp)
            for t in present:
                bloom.add(t)
            return run_skip(conn, stream, bloom, "bloom", cb)
        return run_skip(conn, stream, set(present), "exactset", cb)  # exactset

    results = {}  # name -> (median_us_per_evict, lookups, all_us list)
    oracle_stats = {}
    miss_rate = None

    for name in ("baseline", "bloom", "exactset", "upsert"):
        samples = []
        lookups = 0
        for _ in range(args.repeat):
            conn = fresh_db(args.db)
            present = prepopulate(conn, titles, args.prepopulate, random.Random(args.seed))
            if miss_rate is None:
                present_titles = set(present)
                miss_rate = sum(1 for t, _ in stream if t not in present_titles) / n
            dt, lookups, extra = run_one(name, conn, present)
            conn.close()
            samples.append(dt / n * 1e6)  # us/evict
            oracle_stats.update(extra)
        results[name] = (statistics.median(samples), lookups, samples)

    print(f"\nevict-stream miss rate (title absent at start): {miss_rate:.1%}")
    print(f"  -> this is the ceiling on what bloom/exactset can skip\n")

    base_med = results["baseline"][0]
    print(f"{'strategy':<10} {'us/evict (med)':>15} {'min':>8} {'max':>8} "
          f"{'sqlite ops':>12} {'vs baseline':>12}")
    for name in ("baseline", "bloom", "exactset", "upsert"):
        med, lookups, samples = results[name]
        speedup = base_med / med if med else float("inf")
        print(f"{name:<10} {med:>15.2f} {min(samples):>8.2f} {max(samples):>8.2f} "
              f"{lookups:>12,} {speedup:>11.2f}x")

    print()
    if "bloom_skipped" in oracle_stats:
        sk = oracle_stats["bloom_skipped"]; fp = oracle_stats["bloom_false_pos"]
        print(f"bloom : SELECTs skipped={sk:,} ({sk/n:.1%})  "
              f"false-positives={fp:,} ({fp/n:.2%} of stream)")
    if "exactset_skipped" in oracle_stats:
        sk = oracle_stats["exactset_skipped"]
        print(f"exact : SELECTs skipped={sk:,} ({sk/n:.1%})  false-positives=0 (by construction)")
    print("\nupsert issues 0 SELECTs; its 'sqlite ops' column counts UPDATEs (one per evict).")


if __name__ == "__main__":
    main()
