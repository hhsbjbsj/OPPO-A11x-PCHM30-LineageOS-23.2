#!/usr/bin/env bash
set -eo pipefail
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd /workspace
mkdir -p artifacts
LOG=/workspace/artifacts/vendor-run140-$(date -u +%Y%m%dT%H%M%SZ).log
exec > >(tee "$LOG") 2>&1
echo "Reuse existing ROM and device-tested Run140 kernel. No source sync or compilation. Log: $LOG"
python3 "$HERE/with_tested_kernel.py" "$@" &
worker=$!
(while kill -0 "$worker" 2>/dev/null; do sleep 35; if kill -0 "$worker" 2>/dev/null; then echo "[Run140 integration] running $(date -u +%T)"; fi; done) &
heartbeat=$!
trap 'kill "$heartbeat" 2>/dev/null || true' EXIT
trap 'kill "$worker" 2>/dev/null || true; exit 130' INT TERM
result=0
wait "$worker" || result=$?
kill "$heartbeat" 2>/dev/null || true
wait "$heartbeat" 2>/dev/null || true
exit "$result"
