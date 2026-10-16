#!/usr/bin/env python3
"""
Benchmark: mmap vs read() for sequential and random file access.
Article: https://devmindset.dev/en/mmap-when-memory-mapped-i-o-beats-read-and-write/

mmap delegates page-cache management to the kernel. For random access this
eliminates seek() syscalls — each slice access is a virtual-memory lookup
+ demand paging, bypassing the stdio layer entirely.

Requirements: Python 3.10+, Linux
Usage: python3 benchmark.py [--size-mb 128] [--accesses 10000]

Random workloads share offsets generated once with --seed (default: 0).
An untimed sequential read warms the OS page cache before measurement;
this is not a cold-cache disk benchmark. Files larger than available RAM
may not stay cached. Each round reverses the previous round's order to
reduce order bias; use an even --iterations value to balance first/last
positions. Cache state, memory pressure and timings remain OS-dependent.
Sequential variants also differ in allocation: read() uses 64 KiB chunks,
whereas mmap.read() copies the whole file. Interpret those results accordingly.
"""

from __future__ import annotations

import argparse
import mmap
import os
import random
import tempfile
import time
from collections.abc import Sequence
from pathlib import Path


def create_test_file(path: Path, size_mb: int) -> None:
    chunk = os.urandom(64 * 1024)
    target = size_mb * 1024 * 1024
    with path.open("wb") as f:
        written = 0
        while written < target:
            n = min(len(chunk), target - written)
            f.write(chunk[:n])
            written += n


def bench_read_sequential(path: Path) -> float:
    t = time.perf_counter()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            pass
    return time.perf_counter() - t


def bench_mmap_sequential(path: Path) -> float:
    t = time.perf_counter()
    with path.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        mm.read()
    return time.perf_counter() - t


def bench_read_random(path: Path, offsets: Sequence[int]) -> float:
    t = time.perf_counter()
    with path.open("rb") as f:
        for off in offsets:
            f.seek(off)
            f.read(4096)
    return time.perf_counter() - t


def bench_mmap_random(path: Path, offsets: Sequence[int]) -> float:
    t = time.perf_counter()
    with path.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        for off in offsets:
            _ = mm[off: off + 4096]
    return time.perf_counter() - t


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size-mb", type=positive_int, default=128)
    ap.add_argument("--accesses", type=positive_int, default=10_000)
    ap.add_argument("--iterations", type=positive_int, default=3)
    ap.add_argument("--seed", type=int, default=0, help="random-offset seed (default: 0)")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bench.bin"
        print(f"Creating {args.size_mb} MB test file...")
        create_test_file(p, args.size_mb)

        rng = random.Random(args.seed)
        size = p.stat().st_size
        offsets = tuple(rng.randrange(size - 4096 + 1)
                        for _ in range(args.accesses))
        print(f"Seed: {args.seed}; shared random offsets: {len(offsets)}")
        print("Untimed warm-up; OS page cache is not cleared between runs.")
        print("Alternating order; use even --iterations for balanced positions.")
        bench_read_sequential(p)

        results: dict[str, tuple[float, float]] = {}
        runs: list[tuple[str, object]] = [
            ("read() sequential", lambda f: bench_read_sequential(f)),
            ("mmap  sequential ", lambda f: bench_mmap_sequential(f)),
            ("read() random    ", lambda f: bench_read_random(f, offsets)),
            ("mmap  random     ", lambda f: bench_mmap_random(f, offsets)),
        ]
        times = {label: [] for label, _ in runs}
        for i in range(args.iterations):
            print(f"\n=== round {i+1} ===")
            for label, fn in (runs if i % 2 == 0 else runs[::-1]):
                t = fn(p)
                times[label].append(t)
                print(f"  [{label.strip()}] run {i+1}: {t:.4f}s")
        for label, samples in times.items():
            results[label] = sum(samples) / len(samples), min(samples)

        print()
        print("=== summary ===")
        print(f"{'benchmark':<22} {'mean':>9} {'best':>9}")
        print("-" * 44)
        for label, (mean, best) in results.items():
            print(f"{label:<22} {mean:>8.4f}s {best:>8.4f}s")


if __name__ == "__main__":
    main()
