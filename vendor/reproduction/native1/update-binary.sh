#!/sbin/sh
# PCHM30 native LOS integration TEST1, installed explicitly from PBRP.
# Raw image chunks deliberately avoid sparse writes and >4GiB ZIP entries.
OUTFD=$2
ZIP=$3
case "$OUTFD" in ''|*[!0-9]*) exit 1 ;; esac
ui() { echo "ui_print $*" > "/proc/self/fd/$OUTFD"; echo ui_print > "/proc/self/fd/$OUTFD"; }
abort() { ui "ERROR: $*"; exit 1; }
BB=
for candidate in /sbin/busybox /system/bin/busybox /system/xbin/busybox; do
    if [ -x "$candidate" ]; then BB=$candidate; break; fi
done
[ -n "$BB" ] || abort 'PBRP busybox is required. No partitions were written.'
set -o pipefail 2>/dev/null || abort 'Recovery shell must support pipefail.'
[ -f "$ZIP" ] || abort 'Installation ZIP is missing.'
[ -n "$(getprop ro.twrp.version)" ] || [ -n "$(getprop ro.pbrp.version)" ] || abort 'Run this package in the tested PBRP recovery.'
DEVICE=$(getprop ro.product.device)
case "$DEVICE" in PCHM30|CPH1937) ;; *) abort "Unexpected device: $DEVICE" ;; esac
BASE=/dev/block/bootdevice/by-name
[ -d "$BASE" ] || abort 'Expected factory partition links are unavailable.'
TMP=/tmp/pchm30-los-vendor-native1
[ ! -e "$TMP" ] || abort "Temporary directory exists; restart recovery before retrying."
"$BB" mkdir "$TMP" || abort 'Cannot prepare temporary directory.'
"$BB" unzip -p "$ZIP" chunks.list > "$TMP/chunks.list" || abort 'Missing image chunk list.'
"$BB" unzip -p "$ZIP" partition-sizes.list > "$TMP/partition-sizes.list" || abort 'Missing layout contract.'
EXPECTED_LINES=0
SEEN=" "
while read -r part size node; do
    case "$part:$size:$node" in
        system:5473566720:sda7|vendor:1681915904:sde16|dtbo:25165824:sde18|boot:100663296:sde11|vbmeta:65536:sde17) ;;
        *) abort "Unknown partition contract: $part" ;;
    esac
    case "$SEEN" in *" $part "*) abort "Duplicate partition: $part" ;; esac
    SEEN="$SEEN$part "
    block=$BASE/$part
    [ -b "$block" ] || abort "Missing block device: $part"
    real=$("$BB" readlink -f "$block") || abort 'Cannot resolve partition link.'
    [ "$real" = "/dev/block/$node" ] || abort "Physical mapping differs for $part: $real"
    actual=$("$BB" blockdev --getsize64 "$block") || abort "Cannot read size of $part"
    [ "$actual" = "$size" ] || abort "Partition size differs: $part"
    EXPECTED_LINES=$((EXPECTED_LINES + 1))
done < "$TMP/partition-sizes.list"
[ "$EXPECTED_LINES" = 5 ] || abort 'Incomplete partition contract.'
ui 'PCHM30 LOS23.2 VENDOR NATIVE1: verifying all package chunks before writing.'
# Verify fixed sizes and contiguous chunk ranges, not merely the supplied hashes.
for part in system vendor dtbo boot vbmeta; do
    case "$part" in
        system) expected=5473566720 ;; vendor) expected=1681915904 ;;
        dtbo) expected=25165824 ;; boot) expected=100663296 ;; vbmeta) expected=65536 ;;
    esac
    next=0
    index=0
    while read -r current offset blocks wanted member; do
        case "$current" in system|vendor|dtbo|boot|vbmeta) ;; *) abort 'Unknown write destination.' ;; esac
        [ "$current" = "$part" ] || continue
        case "$offset:$blocks" in *[!0-9:]*|:*) abort 'Invalid image offset.' ;; esac
        [ "$offset" = "$next" ] || abort "Non-contiguous chunk layout: $part"
        [ "$blocks" -gt 0 ] && [ "$blocks" -le 131072 ] || abort 'Invalid chunk length.'
        suffix=$("$BB" printf '%03d' "$index")
        [ "$member" = "images/$part.$suffix.raw" ] || abort 'Unexpected chunk path.'
        [ "${#wanted}" = 64 ] || abort 'Invalid SHA256.'
        case "$wanted" in *[!0-9a-f]*) abort 'Invalid SHA256 digits.' ;; esac
        ui "Checking $member"
        # Hash and exact byte count both precede the first partition write.
        actual=$("$BB" unzip -p "$ZIP" "$member" | "$BB" sha256sum) || abort "Cannot read $member"
        actual=${actual%% *}
        [ "$actual" = "$wanted" ] || abort "Checksum mismatch: $member"
        bytes=$("$BB" unzip -p "$ZIP" "$member" | "$BB" wc -c) || abort 'Cannot count chunk bytes.'
        [ "$bytes" -eq $((blocks * 4096)) ] || abort "Chunk size differs: $member"
        next=$((next + blocks))
        index=$((index + 1))
    done < "$TMP/chunks.list"
    # boot/DTBO/vbmeta may be smaller than the physical partition but are bounded.
    [ "$next" -gt 0 ] && [ $((next * 4096)) -le "$expected" ] || abort 'Image exceeds partition size.'
    case "$part" in system|vendor) [ $((next * 4096)) -eq "$expected" ] || abort 'Incomplete filesystem image.' ;; esac
done
# Release relevant mounts; never format or unmount userdata.
for mountpoint in /my_manifest /odm /mnt/product/odm /mnt/product/my_manifest /system_ext /product /vendor /system /system_root; do
    "$BB" umount "$mountpoint" 2>/dev/null || true
done
while read -r source mountpoint rest; do
    real=$("$BB" readlink -f "$source" 2>/dev/null) || real=$source
    case "$real" in /dev/block/sda7|/dev/block/sde16|/dev/block/sde11|/dev/block/sde18|/dev/block/sde17)
        abort "Target partition remains mounted: $mountpoint" ;;
    esac
done < /proc/mounts
ui 'Checks passed. Writing system, derived vendor, DTBO, boot and vbmeta.'
while read -r part offset blocks wanted member; do
    case "$part" in system|vendor|dtbo|boot|vbmeta) ;; *) abort 'Unknown destination.' ;; esac
    ui "Writing $member"
    "$BB" unzip -p "$ZIP" "$member" | "$BB" dd of="$BASE/$part" bs=4096 seek="$offset" conv=notrunc || abort "Write failed: $member. Remain in recovery."
    "$BB" sync
    actual=$("$BB" dd if="$BASE/$part" bs=4096 skip="$offset" count="$blocks" 2>/dev/null | "$BB" sha256sum) || abort "Read-back failed: $member"
    actual=${actual%% *}
    [ "$actual" = "$wanted" ] || abort "Read-back checksum differs: $member. Remain in recovery."
done < "$TMP/chunks.list"
"$BB" sync
ui 'Installed and read-back verified. Device boot remains experimental.'
ui 'PBRP, physical ODM, GPT and userdata were preserved. No automatic reboot.'
exit 0
