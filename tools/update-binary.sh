#!/sbin/sh
# Frozen user-tested PCHM30 ROM. Never writes GPT, Recovery or userdata.
set -eu
CHECK=0
if [ "${1:-}" = --check ]; then CHECK=1; OUTFD=1; ZIP=${2:?ZIP required}; else OUTFD=${2:?Recovery FD required}; ZIP=${3:?ZIP required}; fi
case "$OUTFD" in ''|*[!0-9]*) exit 1;; esac
ui() { if [ "$OUTFD" = 1 ]; then printf 'ui_print %s\nui_print\n' "$*"; else printf 'ui_print %s\nui_print\n' "$*" > "/proc/self/fd/$OUTFD"; fi; }
abort() { ui "ERROR: $*"; exit 1; }
BB=
for candidate in /sbin/busybox /system/bin/busybox /system/xbin/busybox; do [ ! -x "$candidate" ] || { BB=$candidate; break; }; done
[ -n "$BB" ] || abort 'PBRP busybox required; no partitions were written.'
set -o pipefail 2>/dev/null || abort 'Recovery shell must support pipefail.'
[ -f "$ZIP" ] || abort 'Installation ZIP missing.'
[ -n "$(getprop ro.twrp.version)" ] || abort 'Run in the tested PBRP/TWRP.'
case "$(getprop ro.product.device)" in PCHM30|CPH1937) ;; *) abort 'Wrong device.';; esac
BASE=/dev/block/bootdevice/by-name
TMP=/tmp/pchm30-los-frozen-v1.$$
MOUNTED=0
cleanup() { status=$?; trap - 0; if [ "$MOUNTED" = 1 ]; then "$BB" umount "$TMP/system" || status=1; fi; exit "$status"; }
trap cleanup 0
trap 'exit 1' 1 2 15
[ ! -e "$TMP" ] || abort 'Unexpected temporary directory.'
"$BB" mkdir -p "$TMP/system" || abort 'Cannot prepare temporary directory.'
for file in chunks.list partition-sizes.list final-files.list; do "$BB" unzip -p "$ZIP" "$file" > "$TMP/$file" || abort "Missing $file"; done
EXPECTED_LINES=0
SEEN=' '
while read -r part size node; do
    case "$part:$size:$node" in system:5473566720:sda7|vendor:1681915904:sde16|dtbo:25165824:sde18|boot:100663296:sde11|vbmeta:65536:sde17) ;; *) abort "Unknown partition contract: $part";; esac
    case "$SEEN" in *" $part "*) abort 'Duplicate partition contract.';; esac
    SEEN="$SEEN$part "
    block=$BASE/$part
    [ -b "$block" ] || abort "Missing $part"
    [ "$("$BB" readlink -f "$block")" = "/dev/block/$node" ] || abort "Wrong physical mapping: $part"
    [ "$("$BB" blockdev --getsize64 "$block")" = "$size" ] || abort "Wrong partition size: $part"
    EXPECTED_LINES=$((EXPECTED_LINES + 1))
done < "$TMP/partition-sizes.list"
[ "$EXPECTED_LINES" = 5 ] || abort 'Incomplete layout contract.'
ui 'PCHM30 LOS23.2 FROZEN V1: all Stage1-12 fixes are already inside the System image.'
ui 'Verifying every image chunk before the first partition write.'
for part in system vendor dtbo boot vbmeta; do
    case "$part" in system) expected=5473566720;; vendor) expected=1681915904;; dtbo) expected=25165824;; boot) expected=100663296;; vbmeta) expected=65536;; esac
    next=0; index=0
    while read -r current offset blocks wanted member; do
        case "$current" in system|vendor|dtbo|boot|vbmeta) ;; *) abort 'Unknown destination.';; esac
        [ "$current" = "$part" ] || continue
        case "$offset:$blocks" in *[!0-9:]*|:*) abort 'Invalid chunk offset.';; esac
        [ "$offset" = "$next" ] || abort "Non-contiguous image: $part"
        [ "$blocks" -gt 0 ] && [ "$blocks" -le 131072 ] || abort 'Invalid chunk length.'
        suffix=$("$BB" printf '%03d' "$index")
        [ "$member" = "images/$part.$suffix.raw" ] || abort 'Unexpected member path.'
        [ "${#wanted}" = 64 ] || abort 'Bad SHA256 length.'
        case "$wanted" in *[!0-9a-f]*) abort 'Bad SHA256 digits.';; esac
        ui "Checking $member"
        actual=$("$BB" unzip -p "$ZIP" "$member" | "$BB" sha256sum) || abort "Cannot hash $member"
        [ "${actual%% *}" = "$wanted" ] || abort "Chunk checksum mismatch: $member"
        bytes=$("$BB" unzip -p "$ZIP" "$member" | "$BB" wc -c) || abort 'Cannot count chunk bytes.'
        [ "$bytes" -eq $((blocks * 4096)) ] || abort 'Chunk length mismatch.'
        next=$((next + blocks)); index=$((index + 1))
    done < "$TMP/chunks.list"
    [ $((next * 4096)) -eq "$expected" ] || abort "Incomplete image: $part"
done
if [ "$CHECK" = 1 ]; then ui 'FULL ZIP PRECHECK PASSED. All layout and chunk hashes verified. No partition writes.'; exit 0; fi
# Release only the target-system mounts, never format/unmount userdata.
for point in /my_manifest /odm /mnt/product/odm /mnt/product/my_manifest /system_ext /product /vendor /system /system_root; do "$BB" umount "$point" 2>/dev/null || true; done
while read -r source point rest; do
    real=$("$BB" readlink -f "$source" 2>/dev/null) || real=$source
    case "$real" in /dev/block/sda7|/dev/block/sde16|/dev/block/sde11|/dev/block/sde18|/dev/block/sde17) abort "Target remains mounted: $point";; esac
done < /proc/mounts
ui 'Writing the frozen System, Vendor, DTBO, boot and vbmeta images.'
while read -r part offset blocks wanted member; do
    case "$part" in system|vendor|dtbo|boot|vbmeta) ;; *) abort 'Unknown destination.';; esac
    ui "Writing $member"
    "$BB" unzip -p "$ZIP" "$member" | "$BB" dd of="$BASE/$part" bs=4096 seek="$offset" conv=notrunc || abort "Write failed: $part. Remain in Recovery."
    "$BB" sync
    actual=$("$BB" dd if="$BASE/$part" bs=4096 skip="$offset" count="$blocks" 2>/dev/null | "$BB" sha256sum) || abort 'Readback failed.'
    [ "${actual%% *}" = "$wanted" ] || abort 'Readback mismatch. Remain in Recovery.'
done < "$TMP/chunks.list"
"$BB" mount -t ext4 -o ro,noload "$BASE/system" "$TMP/system" || abort 'Cannot verify the installed System image.'
MOUNTED=1
while read -r wanted relative; do
    case "$relative" in system/*) ;; *) abort 'Unexpected final-file path.';; esac
    case "$relative" in *..*) abort 'Unsafe final-file path.';; esac
    actual=$("$BB" sha256sum "$TMP/system/$relative") || abort "Missing final patch: $relative"
    [ "${actual%% *}" = "$wanted" ] || abort "Final patch differs: $relative"
done < "$TMP/final-files.list"
"$BB" umount "$TMP/system" || abort 'Unmount failed; remain in Recovery.'
MOUNTED=0
ui 'Frozen images and final Stage1-12 file hashes verified. No separate patch ZIPs needed.'
ui 'GPT, Recovery, physical ODM and userdata were preserved. No automatic reboot.'
exit 0
