"""Run with: python3 -m unittest discover -s mmap -p 'test_*.py' -v"""

import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import benchmark


class BenchmarkTests(unittest.TestCase):
    def run_main(self, seed=42, file_size=8192):
        calls = []
        workloads = []

        def sequential(label):
            def measure(path):
                calls.append(label)
                return 0.1
            return measure

        def random_access(label):
            def measure(path, offsets):
                calls.append(label)
                workloads.append(offsets)
                return 0.1
            return measure

        def create_file(path, size_mb):
            path.write_bytes(b"x" * file_size)

        argv = ["benchmark.py", "--size-mb", "1", "--accesses", "20",
                "--iterations", "2", "--seed", str(seed)]
        with patch.object(sys, "argv", argv), contextlib.redirect_stdout(io.StringIO()), \
                patch.object(benchmark, "create_test_file", create_file), \
                patch.object(benchmark, "bench_read_sequential", sequential("read seq")), \
                patch.object(benchmark, "bench_mmap_sequential", sequential("mmap seq")), \
                patch.object(benchmark, "bench_read_random", random_access("read random")), \
                patch.object(benchmark, "bench_mmap_random", random_access("mmap random")):
            benchmark.main()
        return calls, workloads

    def test_shared_offsets_and_alternating_order(self):
        calls, workloads = self.run_main()
        self.assertEqual(calls, ["read seq",  # untimed warm-up
                                "read seq", "mmap seq", "read random", "mmap random",
                                "mmap random", "read random", "mmap seq", "read seq"])
        self.assertEqual(len(workloads), 4)
        self.assertTrue(all(offsets is workloads[0] for offsets in workloads))
        self.assertEqual(len(workloads[0]), 20)
        self.assertTrue(all(0 <= off <= 8192 - 4096 for off in workloads[0]))

    def test_seed_reproducibility_without_global_rng_changes(self):
        state = benchmark.random.getstate()
        first = self.run_main(seed=42)[1][0]
        self.assertEqual(first, self.run_main(seed=42)[1][0])
        self.assertNotEqual(first, self.run_main(seed=43)[1][0])
        self.assertEqual(state, benchmark.random.getstate())

    def test_single_block_file_allows_last_valid_offset(self):
        self.assertEqual(self.run_main(file_size=4096)[1][0], (0,) * 20)

    def test_random_functions_use_supplied_offsets(self):
        offsets = (0, 4096, 13, 4096)
        handle = MagicMock()
        handle.__enter__.return_value = handle
        mapping = MagicMock()
        mapping.__enter__.return_value = mapping
        with patch.object(Path, "open", return_value=handle), \
                patch.object(benchmark.mmap, "mmap", return_value=mapping), \
                patch.object(benchmark.random, "randrange", side_effect=AssertionError):
            benchmark.bench_read_random(Path("unused"), offsets)
            benchmark.bench_mmap_random(Path("unused"), offsets)
        self.assertEqual(handle.seek.call_args_list, [call(off) for off in offsets])
        self.assertEqual(handle.read.call_args_list, [call(4096)] * len(offsets))
        self.assertEqual(mapping.__getitem__.call_args_list,
                         [call(slice(off, off + 4096)) for off in offsets])

    def test_invalid_parameters_fail_before_file_creation(self):
        for option in ("--size-mb", "--accesses", "--iterations"):
            for value in ("0", "-1", "1.5", "invalid"):
                with self.subTest(option=option, value=value), \
                        patch.object(sys, "argv", ["benchmark.py", option, value]), \
                        patch.object(benchmark.tempfile, "TemporaryDirectory") as temp, \
                        contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        benchmark.main()
                    self.assertEqual(error.exception.code, 2)
                    temp.assert_not_called()


if __name__ == "__main__":
    unittest.main()
