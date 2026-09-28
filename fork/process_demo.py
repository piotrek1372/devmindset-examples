#!/usr/bin/env python3
"""
Demonstrates fork() semantics: copy-on-write, zombie prevention, fork+exec.
Article: https://devmindset.dev/en/what-fork-in-linux-really-does-and-why-it-matters-more-than-you-think/

Three self-contained demos run in sequence. PID-tagged output lets you
follow parent/child execution interleaving.

Requirements: Python 3.10+, Linux (os.fork unavailable on Windows)
"""

from __future__ import annotations

import os
import sys
import time


def demo_cow() -> None:
    """
    fork() shares physical pages between parent and child (CoW).
    The first write triggers a page fault; the kernel copies only
    the touched page — not the entire address space.
    """
    buf = bytearray(10 * 1024 * 1024)  # 10 MB shared until first write
    buf[0] = 0xFF

    pid = os.fork()
    if pid == 0:
        print(f"[child  {os.getpid()}] before write: buf[0]={buf[0]:#x}")
        buf[0] = 0xAB  # CoW page fault — only this page gets copied
        print(f"[child  {os.getpid()}] after write:  buf[0]={buf[0]:#x}")
        os._exit(0)

    time.sleep(0.05)
    # The parent value is unchanged; this output alone does not measure page sharing.
    print(f"[parent {os.getpid()}] buf[0]={buf[0]:#x}  (unchanged after child write)")
    os.waitpid(pid, 0)


def demo_zombie() -> None:
    """
    A child that exits before the parent calls waitpid() can become a zombie:
    its process table entry stays until it is reaped, unless SIGCHLD policy
    causes the kernel to discard the status. The pause below does not verify
    the child's actual process state; waitpid() reaps it in this demo.
    """
    pid = os.fork()
    if pid == 0:
        print(f"[child  {os.getpid()}] exiting — zombie until parent reaps")
        os._exit(42)  # use os._exit to skip Python atexit handlers

    time.sleep(0.3)   # allow the child to exit before reaping; not a state check
    print(f"[parent {os.getpid()}] reaping child {pid}...")
    _, status = os.waitpid(pid, 0)
    print(f"[parent {os.getpid()}] reaped — exit code: {os.WEXITSTATUS(status)}")


def demo_exec() -> None:
    """
    fork() + exec() is the canonical Unix process creation pattern.
    The child replaces its entire address space via execvp().
    On success, nothing after execvp() in the child runs; failure raises OSError.
    """
    pid = os.fork()
    if pid == 0:
        try:
            os.execvp("uname", ["uname", "-r"])
        except OSError as exc:
            print(f"[child  {os.getpid()}] execvp failed: {exc}", file=sys.stderr, flush=True)
            os._exit(127)

    _, status = os.waitpid(pid, 0)
    code = os.waitstatus_to_exitcode(status)
    print(f"[parent {os.getpid()}] child exit status: {code}")
    if code != 0:
        raise SystemExit(1)


def main() -> None:
    if sys.platform != "linux":
        sys.exit("This demo requires Linux.")

    print("=== 1. Copy-on-write ===")
    demo_cow()
    print()
    print("=== 2. Zombie prevention via waitpid() ===")
    demo_zombie()
    print()
    print("=== 3. fork() + exec() ===")
    demo_exec()


if __name__ == "__main__":
    main()
