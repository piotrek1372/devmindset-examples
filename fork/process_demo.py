#!/usr/bin/env python3
"""
Demonstrates fork() semantics: copy-on-write, zombie prevention, fork+exec.
Article: https://devmindset.dev/en/what-fork-in-linux-really-does-and-why-it-matters-more-than-you-think/

Three self-contained demos run in sequence. PID-tagged output lets you
follow parent/child execution interleaving in real time.

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
    the touched page -- not the entire address space.
    """
    buf = bytearray(10 * 1024 * 1024)  # 10 MB shared until first write
    buf[0] = 0xFF

    pid = os.fork()
    if pid == 0:
        print(f"[child  {os.getpid()}] before write: buf[0]={buf[0]:#x}")
        buf[0] = 0xAB  # CoW page fault -- only this page gets copied
        print(f"[child  {os.getpid()}] after write:  buf[0]={buf[0]:#x}")
        os._exit(0)

    time.sleep(0.05)
    # Parent page is unaffected -- child received a separate physical copy
    print(f"[parent {os.getpid()}] buf[0]={buf[0]:#x}  (unchanged)")
    os.waitpid(pid, 0)


def demo_zombie() -> None:
    """
    A child that exits before the parent calls waitpid() becomes a zombie:
    the process table entry stays until the parent reaps it.
    Always call waitpid() or install a SIGCHLD handler.
    """
    pid = os.fork()
    if pid == 0:
        print(f"[child  {os.getpid()}] exiting -- zombie until parent reaps")
        os._exit(42)  # use os._exit to skip Python atexit handlers

    time.sleep(0.3)   # child is zombie during this window
    print(f"[parent {os.getpid()}] reaping child {pid}...")
    _, status = os.waitpid(pid, 0)
    print(f"[parent {os.getpid()}] reaped -- exit code: {os.WEXITSTATUS(status)}")


def demo_exec() -> None:
    """
    fork() + exec() is the canonical Unix process creation pattern.
    The child replaces its entire address space via execvp().
    Nothing after execvp() in the child ever runs.
    """
    pid = os.fork()
    if pid == 0:
        os.execvp("uname", ["uname", "-r"])
        os._exit(1)   # unreachable if execvp succeeds

    _, status = os.waitpid(pid, 0)
    print(f"[parent {os.getpid()}] child exited with {os.WEXITSTATUS(status)}")


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
