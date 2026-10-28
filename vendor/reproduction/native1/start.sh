#!/usr/bin/env bash
set -eo pipefail
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd /workspace
mkdir -p artifacts
LOG=/workspace/artifacts/vendor-native1-$(date -u +%Y%m%dT%H%M%SZ).log
exec > >(tee "$LOG") 2>&1
echo "PCHM30 native vendor migration; source cache reused; no repo sync. Log: $LOG"
test -f /opt/lineage/.cnb-los23.2-ready
test "$(git branch --show-current)" = los
worker=
heartbeat=
cleanup() {
    if [ -n "$heartbeat" ]; then kill "$heartbeat" 2>/dev/null || true; fi
    if [ -n "$worker" ]; then kill "$worker" 2>/dev/null || true; fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM
progress() {
    "$@" & worker=$!
    (while kill -0 "$worker" 2>/dev/null; do sleep 35; if kill -0 "$worker" 2>/dev/null; then echo "[vendor-native1] running $(date -u +%T)"; fi; done) & heartbeat=$!
    local result=0
    wait "$worker" || result=$?
    kill "$heartbeat" 2>/dev/null || true
    wait "$heartbeat" 2>/dev/null || true
    worker= heartbeat=
    if [ "$result" -ne 0 ]; then echo "Stopped at an actual error ($result). Log: $LOG"; return "$result"; fi
}
progress python3 "$HERE/port.py" prepare
git add -- pchm30-los23.2-vendor-native1
if ! git diff --cached --quiet -- pchm30-los23.2-vendor-native1; then
    git commit -m "Build native PCHM30 vendor Java modules and derive a recovery installer from saved images" --only -- pchm30-los23.2-vendor-native1
fi
git push origin HEAD:los
cd /opt/lineage
export OUT_DIR=out-pchm30-vendor-native1
unset OUT_DIR_COMMON_BASE
source build/envsetup.sh
source vendor/lineage/vars/aosp_target_release
lunch "lineage_PCHM30_vendorport-${aosp_target_release}-userdebug"
mapfile -t targets < "$HERE/generated/build-targets.txt"
progress m -j64 "${targets[@]}"
progress python3 "$HERE/port.py" finish
echo "Vendor migration and candidate packaging finished. No phone was flashed."
