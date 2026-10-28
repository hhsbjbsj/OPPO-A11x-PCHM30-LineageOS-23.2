#!/usr/bin/env python3
"""Recheck existing images; package only with an explicitly selected kernel exception."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile

import port
import image_support as image
import audit_helpers as audit


def check_args(view, active, mode, kernel):
    args = [port.TOOLS / 'checkvintf', '--check-compat']
    for part in ('system', 'system_ext', 'product', 'vendor'):
        args += ['--dirmap', '/' + part + ':' + str(view / part)]
    args += ['--dirmap', '/odm:' + str(view / ('odm-' + mode)),
             '--dirmap', '/apex:' + str(active), '--property', 'apex.all.ready=true',
             '--property', 'ro.product.first_api_level=28']
    if kernel:
        args += ['--kernel', '4.14.180:' + str(port.HERE / 'stock-kernel.config')]
    return args


def approved_for_exception(report):
    if not report['all_candidate_hashes_match']:
        return False
    if len(report['apps']) != 5 or len(report['odm_jar_native_verification']) != 15:
        return False
    return all(code == 0 for code in report['vintf_without_runtime_info'].values()) and \
        report['selinux_runtime'] == 0 and \
        all(v['code'] == 65 and v['known_kernel_fcm_mismatch']
            for v in report['full_vintf_recheck'].values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package-with-kernel-exception', action='store_true',
                        help='Explicitly choose an experimental installer despite the retained kernel VINTF failure')
    options = parser.parse_args()
    state = json.loads(port.STATE.read_text())
    run = Path(state['run']).resolve()
    assert run.is_relative_to((port.WS / 'artifacts').resolve()) and run.is_dir()
    assert 'images' in state and isinstance(state['images'], dict), 'No finalized candidate image record exists'
    assert len(state['apps']) == 5 and len(state['odm_jar_native_verification']) == 15
    candidate, view, active = run / 'candidate', run / 'view', run / 'apex'
    assert view.is_dir() and (active / 'apex-info-list.xml').is_file()
    output = run / ('resume-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir()
    logs = output / 'logs'
    logs.mkdir()
    report = dict(state)
    report.pop('error', None)
    report.update(resume_output=str(output), source_failure_report=str(run / 'REPORT.json'),
                  install_zip_created=False, device_boot_tested=False, stable_release=False,
                  full_vintf_compatibility_passed=False, kernel_compatibility_passed=False,
                  kernel_exception_explicitly_selected=options.package_with_kernel_exception,
                  kernel_runtime_info_omitted_in_secondary_check=True,
                  native_kernel='4.14.180', kernel_fcm_level=5,
                  original_images_not_modified_by_resume=True, phone_written=False,
                  full_vintf_recheck={}, vintf_without_runtime_info={})
    try:
        for part, entry in state['images'].items():
            path = candidate / (part + '.img')
            assert path.stat().st_size == entry['bytes'] and audit.digest(path) == entry['sha256'], 'Existing candidate differs: ' + part
        report['all_candidate_hashes_match'] = True
        # These views were exported from these exact candidate images by the completed finish stage.
        report['framework_kernel_profiles'] = {}
        for p in sorted((view / 'system/etc/vintf').glob('compatibility_matrix.*.xml')):
            entries = sorted({(k.get('version'), k.get('level')) for k in ET.parse(p).getroot().findall('kernel')})
            if entries:
                report['framework_kernel_profiles'][p.name] = entries
        for mode in ('dsds', 'ssss'):
            link = view / ('odm-' + mode) / 'etc/vintf/manifest/telephony_manifest.xml'
            original = view / 'odm-source/etc/vintf' / ('telephony_manifest_' + mode + '.xml')
            assert link.is_file() and not link.is_symlink() and link.read_bytes() == original.read_bytes()
            log = logs / ('vintf-full-' + mode + '.log')
            code = audit.command(check_args(view, active, mode, True), log)
            text = log.read_text(errors='replace')
            known = 'Kernel FCM Version is 5 and kernel version is 4.14.180' in text and \
                    'first kernel FCM version allowed for kernel version 4.14.y is 6' in text
            report['full_vintf_recheck'][mode] = {'code': code, 'known_kernel_fcm_mismatch': known}
            log2 = logs / ('vintf-without-runtime-info-' + mode + '.log')
            code2 = audit.command(check_args(view, active, mode, False), log2)
            report['vintf_without_runtime_info'][mode] = code2
            print('VINTF', mode, 'full=', code, 'without runtime/kernel info=', code2, flush=True)
            if code2:
                print('\n'.join(log2.read_text(errors='replace').splitlines()[-60:]), flush=True)
        for runtime, label in ((True, 'runtime'), (False, 'strict-review')):
            report['selinux_' + label] = audit.command(
                audit.selinux_args(port.TOOLS / 'secilc', view, output / ('policy-' + label), runtime),
                logs / ('selinux-' + label + '.log'))
        if not options.package_with_kernel_exception:
            print('REPORT-ONLY: no installer produced. Full kernel VINTF failure remains recorded.', flush=True)
            print('Exception candidate checks eligible:', approved_for_exception(report), flush=True)
            return
        assert approved_for_exception(report), 'Additional incompatibility or failed integrity/policy check; exception installer withheld'
        assert shutil.disk_usage(port.WS).free > 8 * 2**30, 'Need at least 8GiB for final archive'
        bundle = output / 'installer-text'
        bundle.mkdir()
        installer = (port.HERE / 'update-binary.sh').read_text()
        installer = installer.replace("ui 'Checks passed. Writing", "ui 'Partition and image checks passed. Writing")
        marker = "ui 'PCHM30 LOS23.2 VENDOR NATIVE1: verifying all package chunks before writing.'"
        assert installer.count(marker) == 1
        banner = "ui 'EXPERIMENTAL: original kernel 4.14.180 fails full VINTF kernel requirements.'\n"
        installer = installer.replace(marker, banner + marker)
        (bundle / 'update-binary.sh').write_text(installer)
        (bundle / 'README.txt').write_text(
            'PCHM30 LOS23.2 首启实验包：内核要求例外\n\n'
            '完整 VINTF 内核检查失败：原厂4.14.180 / Kernel FCM5，与当前系统矩阵不匹配。\n'
            '只因用户显式选择内核检查例外而打包；报告中的完整检查仍保留失败，不得称作严格兼容通过。\n'
            '不提供runtime/kernel信息的二次VINTF检查，以及SELinux运行期策略链接已通过。\n'
            '额外neverallow审查结果见BUILD-REPORT.json；它与运行期链接是不同检查。\n'
            '五个APK签名迁移和15个ODM库的原生dexpreopt构建已完成；不代表JNI/Binder和硬件功能已通过。\n'
            '内核版本号、内核二进制、设备FCM等级、系统矩阵在此次续跑中均未修改。\n'
            'ZIP写system/vendor/boot/dtbo/vbmeta；不写GPT、recovery、物理ODM，不格式化data、不自动重启。\n'
            '手机启动、旧data兼容、解密和全部硬件均未测试；可能无法开机。\n', encoding='utf-8')
        image.HERE = bundle
        image.WORKSPACE = port.WS
        old_stamp = image.stamp
        image.stamp = lambda: 'KERNEL-EXCEPTION-' + old_stamp()
        package_report = dict(report, install_zip_created=True)
        result = image.package(output, {p: candidate / (p + '.img') for p in image.SIZES}, package_report)
        report.update(package_report)
        print('EXPERIMENTAL INSTALLER:', result, flush=True)
    except Exception as error:
        report['resume_error'] = str(error)
        raise
    finally:
        port.save(output / 'REPORT.json', report)
        with zipfile.ZipFile(output / 'REPORT-LOGS.zip', 'w', zipfile.ZIP_DEFLATED) as z:
            for p in sorted(logs.glob('*.log')):
                z.write(p, 'logs/' + p.name)
            z.write(output / 'REPORT.json', 'REPORT.json')
        print('RESUME_REPORT:', output / 'REPORT.json', flush=True)


if __name__ == '__main__':
    main()
