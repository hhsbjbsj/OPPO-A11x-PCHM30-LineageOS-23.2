#!/usr/bin/env python3
"""Apply the user's device-tested Run140 kernel to existing images, with honest gates."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import zipfile

import port
import image_support as image
import audit_helpers as audit
from tested_kernel_boot import replace_kernel


def prepare_avb_siblings(run, sources):
    """avbtool resolves descriptor partitions next to the top-level vbmeta file."""
    for part in ('system', 'vendor', 'dtbo'):
        source = sources[part].resolve(strict=True)
        assert source.is_file(), 'Missing verified source image: ' + part
        sibling = run / (part + '.img')
        if sibling.is_symlink():
            assert sibling.resolve(strict=True) == source, 'Existing AVB sibling points elsewhere: ' + part
        else:
            assert not sibling.exists(), 'Refusing to replace an existing image: ' + str(sibling)
            sibling.symlink_to(source)


def check_args(view, active, mode, config, kernel=True):
    args = [port.TOOLS / 'checkvintf', '--check-compat']
    for part in ('system', 'system_ext', 'product', 'vendor'):
        args += ['--dirmap', '/' + part + ':' + str(view / part)]
    args += ['--dirmap', '/odm:' + str(view / ('odm-' + mode)), '--dirmap', '/apex:' + str(active),
             '--property', 'apex.all.ready=true', '--property', 'ro.product.first_api_level=28']
    if kernel:
        args += ['--kernel', '4.14.357:' + str(config)]
    return args


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package-experimental', action='store_true',
                        help='Create a first-boot installer with the tested kernel even if only the known kernel FCM check fails')
    args = parser.parse_args()
    prior = json.loads(port.STATE.read_text())
    original_run = Path(prior['run']).resolve()
    assert original_run.is_relative_to((port.WS / 'artifacts').resolve())
    assert len(prior['apps']) == 5 and len(prior['odm_jar_native_verification']) == 15
    run = original_run / ('kernel-run140-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    run.mkdir()
    logs = run / 'logs'
    logs.mkdir()
    record = dict(prior)
    record.pop('error', None)
    record.update(phase='Run140 device-tested kernel first boot integration',
                  original_run=str(original_run), output=str(run), phone_written=False,
                  stable_release=False, device_boot_tested=False, full_rom_device_boot_tested=False,
                  kernel_artifact_device_tested_user_report=True, kernel_run=40327745272,
                  reported_kernel_release='4.14.357-perf+',
                  kernel_source_ref='190a49ea435d04c3d9f1974dfcb6c53334fa3524',
                  kernel_lts357_full_merge_verified=False,
                  kernel_lts_evidence_note='Run140 version-upgrade script updates version fields and fixed proof strings; real BPF/Binder backports exist separately.',
                  install_zip_created=False, full_vintf_compatibility_passed=False,
                  package_experimental_explicitly_selected=args.package_experimental,
                  full_vintf={}, vintf_without_runtime_info={})
    try:
        sources = {p: original_run / 'candidate' / (p + '.img') for p in image.SIZES}
        for part, entry in prior['images'].items():
            assert sources[part].stat().st_size == entry['bytes'] and audit.digest(sources[part]) == entry['sha256'], 'Prior candidate changed: ' + part
        payload = port.HERE / 'payload/run140'
        raw = (payload / 'Image').read_bytes()
        assert hashlib.sha256(raw).hexdigest() == 'c17660264eed69c7639c78ce4e1b12323629e69c198107b3cf1cd01913349464'
        cfg = payload / 'kernel.config'
        start, end = raw.find(b'IKCFG_ST'), raw.find(b'IKCFG_ED')
        assert start >= 0 and end > start
        assert gzip.decompress(raw[start + 8:end]) == cfg.read_bytes(), 'Published configuration differs from embedded kernel'
        assert b'# CONFIG_USERFAULTFD is not set' in cfg.read_bytes()
        assert b'CONFIG_EXT4_FS=y\n' in cfg.read_bytes(), 'Existing ext4 APEX payloads require built-in ext4 support'
        record['kernel_configuration_sha256'] = audit.digest(cfg)
        boot = run / 'boot.img'
        data, proof = replace_kernel(sources['boot'].read_bytes(), raw)
        assert proof['ramdisk_sha256'] == '0f9a47c8528bddf032be76344e27374cc8d50229882b1c6e1f7a8f548b652a7a'
        assert len(data) < image.SIZES['boot'] - 128 * 1024
        boot.write_bytes(data)
        record['kernel_boot_integration'] = proof
        key = port.ROOT / 'external/avb/test/data/testkey_rsa4096.pem'
        misc = (original_run / 'input-misc_info.txt').read_text()
        footer_text = next(line.split('=', 1)[1] for line in misc.splitlines() if line.startswith('avb_boot_add_hash_footer_args='))
        footer_args = shlex.split(footer_text)
        assert len(footer_args) % 2 == 0 and all(v == '--prop' for v in footer_args[::2]), 'Unexpected boot AVB metadata arguments'
        record['preserved_boot_avb_property_arguments'] = footer_args
        port.checked([port.TOOLS / 'avbtool', 'add_hash_footer', '--image', boot,
                      '--partition_name', 'boot', '--partition_size', str(image.SIZES['boot']),
                      '--algorithm', 'SHA256_RSA4096', '--key', key] + footer_args, logs / 'boot-avb-new.log')
        port.checked([port.TOOLS / 'avbtool', 'verify_image', '--image', boot], logs / 'boot-avb-verify.log')
        sources['boot'] = boot
        vbmeta = run / 'vbmeta.img'
        command = [port.TOOLS / 'avbtool', 'make_vbmeta_image', '--output', vbmeta,
                   '--key', key, '--algorithm', 'SHA256_RSA4096', '--flags', '3',
                   '--padding_size', '65536', '--rollback_index', '0']
        for part in ('system', 'vendor', 'boot', 'dtbo'):
            command += ['--include_descriptors_from_image', sources[part]]
        port.checked(command, logs / 'vbmeta-new.log')
        prepare_avb_siblings(run, sources)
        port.checked([port.TOOLS / 'avbtool', 'verify_image', '--image', vbmeta], logs / 'vbmeta-verify.log')
        sources['vbmeta'] = vbmeta
        for part in ('boot', 'vbmeta'):
            assert sources[part].stat().st_size == image.SIZES[part]
            record['images'] = dict(record['images'])
            record['images'][part] = {'bytes': sources[part].stat().st_size, 'sha256': audit.digest(sources[part])}
        view, active = original_run / 'view', original_run / 'apex'
        assert view.is_dir() and (active / 'apex-info-list.xml').is_file()
        for mode in ('dsds', 'ssss'):
            full_log = logs / ('vintf-full-' + mode + '.log')
            full = audit.command(check_args(view, active, mode, cfg), full_log)
            text = full_log.read_text(errors='replace')
            known = 'Kernel FCM Version is 5 and kernel version is 4.14.357' in text and \
                    'first kernel FCM version allowed for kernel version 4.14.y is 6' in text
            record['full_vintf'][mode] = {'code': full, 'known_kernel_fcm_mismatch': known}
            other_log = logs / ('vintf-without-runtime-info-' + mode + '.log')
            other = audit.command(check_args(view, active, mode, cfg, False), other_log)
            record['vintf_without_runtime_info'][mode] = other
            print('RUN140 VINTF:', mode, 'full=', full, 'without kernel/runtime info=', other, flush=True)
            if other:
                print('\n'.join(other_log.read_text(errors='replace').splitlines()[-70:]), flush=True)
        for runtime, label in ((True, 'runtime'), (False, 'strict-review')):
            record['selinux_' + label] = audit.command(
                audit.selinux_args(port.TOOLS / 'secilc', view, run / ('policy-' + label), runtime),
                logs / ('selinux-' + label + '.log'))
        full_ok = all(v['code'] == 0 for v in record['full_vintf'].values())
        exception_only = all(v['code'] == 65 and v['known_kernel_fcm_mismatch'] for v in record['full_vintf'].values())
        record['full_vintf_compatibility_passed'] = full_ok
        record['kernel_check_exception_used'] = not full_ok and args.package_experimental
        assert all(v == 0 for v in record['vintf_without_runtime_info'].values()), 'Non-kernel incompatibility remains; installer withheld'
        assert record['selinux_runtime'] == 0, 'Runtime SELinux policy link failed; installer withheld'
        assert full_ok or exception_only, 'Unexpected full VINTF failure; installer withheld'
        if not args.package_experimental:
            print('Boot image prepared and checks recorded; no installer requested.', flush=True)
            return
        assert shutil.disk_usage(port.WS).free > 8 * 2**30
        text_files = run / 'installer-text'
        text_files.mkdir()
        installer = (port.HERE / 'update-binary.sh').read_text()
        marker = "ui 'PCHM30 LOS23.2 VENDOR NATIVE1: verifying all package chunks before writing.'"
        assert installer.count(marker) == 1
        banner = "ui 'EXPERIMENTAL: device-tested Run140 kernel; full kernel VINTF is not certified.'\n"
        installer = installer.replace(marker, banner + marker).replace("ui 'Checks passed. Writing", "ui 'Partition and image checks passed. Writing")
        (text_files / 'update-binary.sh').write_text(installer)
        (text_files / 'README.txt').write_text(
            'PCHM30 LOS23.2 Run140 首启实验包\n\n'
            '内核来自用户提供且已实测的GitHub Actions Run140，原始Image SHA256:\n'
            'c17660264eed69c7639c78ce4e1b12323629e69c198107b3cf1cd01913349464\n'
            '保留原厂DTB、ramdisk、boot header布局；生成新boot ID和AVB。system/vendor沿用已构建候选。\n'
            '产物内核报告4.14.357；工作流的357升级脚本只更新版本字段，完整LTS357补丁合入未获验证。\n'
            '原厂FCM5与系统的内核要求仍有冲突；完整内核VINTF结果如实保留，未称为严格兼容通过。\n'
            '不提供runtime/kernel信息的VINTF检查及运行期SELinux链接均须通过，才允许本实验打包。\n'
            '额外neverallow审查结果单独保留；JNI/Binder、旧data、解密和硬件运行状态尚未完成ROM实测。\n'
            '内核在原系统上可用不代表这套新ROM已经能启动。\n'
            '安装器写system/vendor/boot/dtbo/vbmeta，不写GPT、recovery和物理ODM，不格式化data、不自动重启。\n', encoding='utf-8')
        image.HERE = text_files
        image.WORKSPACE = port.WS
        stamp = image.stamp
        image.stamp = lambda: 'RUN140-EXPERIMENTAL-' + stamp()
        package_record = dict(record, install_zip_created=True)
        result = image.package(run, sources, package_record)
        record.update(package_record)
        print('FIRST BOOT INSTALLER:', result, flush=True)
    except Exception as error:
        record['error'] = str(error)
        raise
    finally:
        port.save(run / 'REPORT.json', record)
        with zipfile.ZipFile(run / 'REPORT-LOGS.zip', 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(run / 'REPORT.json', 'REPORT.json')
            for p in logs.glob('*.log'):
                z.write(p, 'logs/' + p.name)
        print('RUN140 REPORT:', run / 'REPORT.json', flush=True)


if __name__ == '__main__':
    main()
