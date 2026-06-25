#!/usr/bin/env bash
# Practical strace patterns for production debugging.
# Article: https://devmindset.dev/en/strace-as-a-debugging-primitive-when-the-stack-trace-lies/
# Usage: ./trace_process.sh <pid> [io|net|slow|all]

set -euo pipefail
readonly OUT="/tmp/strace_$$"
PID="${1:-}"
MODE="${2:-io}"

die() { echo "error: $*" >&2; exit 1; }
[[ -z "$PID" ]] && { echo "Usage: $0 <pid> [io|net|slow|all]" >&2; exit 1; }
[[ ! "$PID" =~ ^[0-9]+$ ]] && die "PID must be a number"
[[ ! -d "/proc/$PID" ]] && die "process $PID not found"
mkdir -p "$OUT"

case "$MODE" in
io)
    echo "=> file I/O for PID $PID (^C to stop)"
    # -y resolves fd numbers to actual file paths
    strace -e trace=openat,read,write,close,fstat -y -p "$PID" -o "$OUT/io.log"
    echo "=> log: $OUT/io.log"
    echo "=> top opened paths:"
    grep -oP '(?<=openat\([A-Z_]+, ")[^"]+' "$OUT/io.log" | sort | uniq -c | sort -rn | head -15
    ;;
net)
    echo "=> network syscalls for PID $PID (^C to stop)"
    # -y on connect shows TCP:[src->dst] detail
    strace -e trace=connect,bind,sendto,recvfrom -y -p "$PID" -o "$OUT/net.log"
    echo "=> log: $OUT/net.log"
    grep -oP 'sin_addr=inet_addr\("\K[^"]+' "$OUT/net.log" | sort -u
    ;;
slow)
    THRESH="${3:-0.010}"
    echo "=> syscalls > ${THRESH}s on PID $PID (^C to stop)"
    # -T appends time-in-syscall as <N.NNNNNN> at end of each line
    strace -T -p "$PID" 2>&1 | awk -v t="$THRESH" '
        match($0, /<([0-9]+\.[0-9]+)>$/, m) && m[1]+0 > t+0 {
            printf "SLOW [%ss] %s\n", m[1], $0
        }'
    ;;
all)
    echo "=> full trace for PID $PID — high overhead (^C to stop)"
    # -f follows forks, -tt microsecond timestamps
    strace -f -tt -p "$PID" -o "$OUT/full.log"
    echo "=> log: $OUT/full.log"
    echo "=> syscall frequency:"
    awk '{print $2}' "$OUT/full.log" | grep -oP '^[a-z_]+' | sort | uniq -c | sort -rn | head -20
    ;;
*)
    die "unknown mode: $MODE (use io|net|slow|all)"
    ;;
esac
