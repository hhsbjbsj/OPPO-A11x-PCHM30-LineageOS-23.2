#!/usr/bin/env bash
set -eo pipefail
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd /workspace
mkdir -p artifacts
LOG=/workspace/artifacts/vendor-native1-resume-$(date -u +%Y%m%dT%H%M%SZ).log
exec > >(tee "$LOG") 2>&1
echo "Reuse existing candidate images. No compilation, no image edits. Log: $LOG"
python3 "$HERE/resume.py" "$@" &
worker=$!
(while kill -0 "$worker" 2>/dev/null; do sleep 35; if kill -0 "$worker" 2>/dev/null; then echo "[candidate resume] running $(date -u +%T)"; fi; done) &
heartbeat=$!
cleanup() { kill "$heartbeat" 2>/dev/null || true; }
trap cleanup EXIT
trap 'kill "$worker" 2>/dev/null || true; exit 130' INT TERM
result=0
wait "$worker" || result=$?
kill "$heartbeat" 2>/dev/null || true
wait "$heartbeat" 2>/dev/null || true
exit "$result"
