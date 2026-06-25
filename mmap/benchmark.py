#!/usr/bin/env python3
"""
Benchmark: mmap vs read() for sequential and random file access.
Article: https://devmindset.dev/en/mmap-when-memory-mapped-i-o-beats-read-and-write/

mmap delegates page-cache management to the kernel. For random access this
eliminates seek() syscalls — each slice access is a virtual-memory lookup
+ demand paging, bypassing the stdio layer entirely.

Requirements: Python 3.10+, Linux
Usage: python3 benchmark.py [--size-mb 128] [--accesses 10000]
"""

from __future__ import annotations

import argparse
import mmap
import os
import random
import tempfile
import time
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


def bench_read_random(path: Path, n: int) -> float:
    size = path.stat().st_size
    offsets = [random.randrange(0, size - 4096) for _ in range(n)]
    t = time.perf_counter()
    with path.open("rb") as f:
        for off in offsets:
            f.seek(off)
            f.read(4096)
    return time.perf_counter() - t


def bench_mmap_random(path: Path, n: int) -> float:
    size = path.stat().st_size
    offsets = [random.randrange(0, size - 4096) for _ in range(n)]
    t = time.perf_counter()
    with path.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        for off in offsets:
            _ = mm[off: off + 4096]
    return time.perf_counter() - t


def run(fn, path: Path, iters: int, label: str) -> tuple[float, float]:
    times = []
    for i in range(iters):
        t = fn(path)
        times.append(t)
        print(f"  [{label}] run {i+1}: {t:.4f}s")
    return sum(times) / iters, min(times)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--size-mb", type=int, default=128)
    ap.add_argument("--accesses", type=int, default=10_000)
    ap.add_argument("--iterations", type=int, default=3)
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "bench.bin"
        print(f"Creating {args.size_mb} MB test file...")
        create_test_file(p, args.size_mb)

        results: dict[str, tuple[float, float]] = {}
        runs: list[tuple[str, object]] = [
            ("read() sequential", lambda f: bench_read_sequential(f)),
            ("mmap  sequential ", lambda f: bench_mmap_sequential(f)),
            ("read() random    ", lambda f: bench_read_random(f, args.accesses)),
            ("mmap  random     ", lambda f: bench_mmap_random(f, args.accesses)),
        ]
        for label, fn in runs:
            print()
            print(f"=== {label.strip()} ===")
            results[label] = run(fn, p, args.iterations, label.strip())

        print()
        print("=== summary ===")
        print(f"{'benchmark':<22} {'mean':>9} {'best':>9}")
        print("-" * 44)
        for label, (mean, best) in results.items():
            print(f"{label:<22} {mean:>8.4f}s {best:>8.4f}s")


if __name__ == "__main__":
    main()
