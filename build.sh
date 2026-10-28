#!/usr/bin/env bash
set -eo pipefail
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=${ANDROID_BUILD_TOP:-/opt/lineage}
MODE=${1:---modules}
FIRMWARE=${2:-/workspace/PCHM30-LOS23.2-TESTED-FIRMWARE-V1.zip}
case "$MODE" in --modules|--system) ;; *) echo 'Usage: bash build.sh --modules|--system /path/to/firmware.zip' >&2; exit 1;; esac
python3 "$HERE/tools/setup.py" --root "$ROOT" --firmware "$FIRMWARE"
cd "$ROOT"
# Keep OUT_DIR source-relative: Soong rejects absolute paths outside the tree.
export OUT_DIR=out-pchm30-source-baseline
unset OUT_DIR_COMMON_BASE
mkdir -p /workspace/out-pchm30-source-baseline
if [ -e "$ROOT/$OUT_DIR" ] || [ -L "$ROOT/$OUT_DIR" ]; then
    test -L "$ROOT/$OUT_DIR"
    test "$(readlink -f "$ROOT/$OUT_DIR")" = /workspace/out-pchm30-source-baseline
else
    ln -s /workspace/out-pchm30-source-baseline "$ROOT/$OUT_DIR"
fi
source build/envsetup.sh
source vendor/lineage/vars/aosp_target_release
lunch "lineage_PCHM30-${aosp_target_release}-userdebug"
worker= heartbeat=
cleanup() { [ -z "$heartbeat" ] || kill "$heartbeat" 2>/dev/null || true; [ -z "$worker" ] || kill "$worker" 2>/dev/null || true; }
trap cleanup EXIT
run() {
    "$@" & worker=$!
    (while kill -0 "$worker" 2>/dev/null; do sleep 35; if kill -0 "$worker" 2>/dev/null; then echo "[PCHM30 source build] running $(date -u +%T)"; fi; done) & heartbeat=$!
    local code=0; wait "$worker" || code=$?
    kill "$heartbeat" 2>/dev/null || true; wait "$heartbeat" 2>/dev/null || true; worker= heartbeat=
    return "$code"
}
if [ "$MODE" = --modules ]; then
    run m -j64 services framework-res netd lmkd com.android.tethering com.android.resolv SystemUI
    python3 "$HERE/tools/apply.py" --root "$ROOT" --check
    python3 - "$HERE/SOURCE-BUILD-REPORT.json" <<'PY'
import datetime,json,sys
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'core_android_modules_compiled':True,'targets':['services','framework-res','netd','lmkd','com.android.tethering','com.android.resolv','SystemUI'],'full_system_built':False,'phone_flashed_or_tested':False},indent=2)+'\n')
PY
    echo 'SOURCE MODULE BUILD PASSED. No ROM installation or phone test performed.'
else
    run m -j64 systemimage simg2img debugfs
    echo "SOURCE SYSTEM IMAGE BUILT: $ROOT/$OUT_DIR/target/product/PCHM30/system.img"
    run python3 "$HERE/tools/package_build.py" --root "$ROOT" --out "$ROOT/$OUT_DIR"
fi
