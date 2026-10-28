#!/usr/bin/env python3
"""Migrate real vendor APK modules and derive images from the saved native build."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET
import zipfile

import apk_identity as apk
import audit_helpers as audit
import image_support as image

HERE = Path(__file__).resolve().parent
ROOT = Path('/opt/lineage')
WS = Path('/workspace')
OUT = WS / 'out-pchm30-vendor-native1'
PRODUCT = OUT / 'target/product/PCHM30_vendorport'
TOOLS = OUT / 'host/linux-x86/bin'
DEVICE = ROOT / 'device/oppo/PCHM30_vendorport'
STATE = HERE / 'generated/state.json'
APPS = json.loads((HERE / 'expected-apps.json').read_text())
JARS = json.loads((HERE / 'expected-odm-jars.json').read_text())
VENDOR_SHA = '87a25a17d1205e6836779566da2315001bf475a9b22da63f8219fb6bfa5d84b7'
SIZES = image.SIZES


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def checked(args, log):
    log.parent.mkdir(parents=True, exist_ok=True)
    code = audit.command(args, log)
    if code:
        print('\n'.join(log.read_text(errors='replace').splitlines()[-65:]), flush=True)
        raise RuntimeError('Command failed (%s): %s' % (code, log))


def archive_manifest(z):
    names = z.namelist()
    assert len(names) == len(set(names)), 'Duplicate archive entries'
    needed = {'IMAGES/' + n + '.img' for n in SIZES}
    assert needed <= set(names), 'Backup must contain system/vendor/boot/dtbo/vbmeta'
    info = z.read('META/misc_info.txt').decode()
    assert 'system_size=5473566720\n' in info and 'vendor' in info
    assert 'boot_size=100663296\n' in info and 'vintf_enforce=true\n' in info
    return names


class ImageEditor(audit.ImageReader):
    def __init__(self, executable, logdir, owned):
        super().__init__(executable, logdir)
        self.owned = owned.resolve()

    def run(self, img, request):
        mutating = request.split(' ', 1)[0] in {'rm', 'write', 'set_inode_field', 'ea_set'}
        if mutating:
            assert img.resolve().parent == self.owned and img.name in ('system.img', 'vendor.img'), 'Refusing to edit an input image'
            self.count += 1
            result = subprocess.run([str(self.executable), '-w', '-R', request, str(img)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            (self.logdir / ('debugfs-%03d.log' % self.count)).write_text(result.stdout)
            assert result.returncode == 0 and not re.search(r'(?i)error|not found|not enough|not open|usage:', result.stdout), result.stdout
            return result.stdout
        return super().run(img, request)


def extract_member(z, name, dest):
    # All paths below are chosen by this program, not by the archive.
    p = PurePosixPath(name)
    assert not p.is_absolute() and '..' not in p.parts
    assert not dest.is_symlink()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with z.open(name) as src, dest.open('xb') as out:
        shutil.copyfileobj(src, out, 4 * 2**20)


def prepare():
    assert (ROOT / '.cnb-los23.2-ready').is_file()
    head = subprocess.check_output(['git', '-C', str(ROOT / '.repo/manifests'), 'rev-parse', 'HEAD'], text=True).strip()
    assert head == '9776e518de506f610218c4caa6c1fddff46873af', 'Wrong cached source manifest'
    archive = WS / 'LOS23.2-BACKUP-target-files.zip'
    assert archive.is_file(), 'Upload LOS23.2-BACKUP-target-files.zip to /workspace first'
    assert shutil.disk_usage(WS).free > 35 * 2**30, 'Need at least 35GiB for image work, in addition to compiler outputs'
    run = WS / 'artifacts' / ('vendor-native1-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    run.mkdir(parents=True)
    images = run / 'input'
    with zipfile.ZipFile(archive) as z:
        names = archive_manifest(z)
        for part in SIZES:
            print('Restoring saved image:', part, flush=True)
            extract_member(z, 'IMAGES/' + part + '.img', images / (part + '.img'))
        extract_member(z, 'SYSTEM/framework/framework-res.apk', run / 'framework-res.apk')
        # Save exact package metadata, not a fabricated target-files installation.
        extract_member(z, 'META/misc_info.txt', run / 'input-misc_info.txt')
    expected = json.loads((HERE / 'expected-backup.json').read_text())
    for part, entry in expected['images'].items():
        p = images / (part + '.img')
        assert p.stat().st_size == entry['bytes'] and audit.digest(p) == entry['sha256'], 'Backup image differs from the saved copy: ' + part
    assert expected['images']['vendor']['sha256'] == VENDOR_SHA
    assert image.boot_payloads(images / 'boot.img') == {
        'kernel': 'd83bf44d06a1ed1aeb7c8d597bbccd627458e7619e8606218f33358d145a0f1b',
        'ramdisk': '0f9a47c8528bddf032be76344e27374cc8d50229882b1c6e1f7a8f548b652a7a'}, 'Backup boot payload changed'
    platform = apk.certificates(run / 'framework-res.apk')
    assert platform == ['c8a2e9bccf597c2fb6dc66bee293fc13f2fc47ec77bc6b2b0d52c11f51192ab8']
    # This new product is isolated from the previous PCHM30 tree and build output.
    assert not DEVICE.is_symlink()
    if DEVICE.exists():
        assert (DEVICE / '.vendor-native1-owned').is_file(), 'Unrecognized existing device tree'
        shutil.copytree(DEVICE, run / 'device-before', symlinks=True)
    DEVICE.mkdir(parents=True, exist_ok=True)
    for src in (HERE / 'device').rglob('*'):
        if src.is_file():
            dst = DEVICE / src.relative_to(HERE / 'device')
            assert not dst.is_symlink()
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    (DEVICE / '.vendor-native1-owned').write_text('Isolated native vendor module build\n')
    modules = []
    bp = ['soong_namespace {}', '']
    for app in APPS:
        name = Path(app['logical_path']).name
        source = HERE / 'payload/apks' / name
        assert audit.digest(source) == app['sha256'], 'Payload APK changed: ' + name
        target = DEVICE / 'apps' / name
        target.parent.mkdir(exist_ok=True)
        assert not target.is_symlink()
        shutil.copyfile(source, target)
        module = app['module']
        modules.append(module)
        bp += ['android_app_import {', '    name: ' + json.dumps(module) + ',',
               '    apk: ' + json.dumps('apps/' + name) + ',',
               '    filename: ' + json.dumps(name) + ',',
               '    certificate: "platform",', '    vendor: true,',
               '    strip_unused_jni_arch: false,', '    enforce_uses_libs: true,',
               '    dex_preopt: { enabled: true, profile_guided: false },', '}', '']
    for lib in JARS:
        name = Path(lib['path']).name
        source = HERE / 'payload/jars' / name
        assert audit.digest(source) == lib['sha256']
        target = DEVICE / 'jars' / name
        target.parent.mkdir(exist_ok=True)
        assert not target.is_symlink()
        shutil.copyfile(source, target)
        modules.append(lib['module'])
        bp += ['dex_import {', '    name: ' + json.dumps(lib['module']) + ',',
               '    jars: [' + json.dumps('jars/' + name) + '],', '    vendor: true,',
               '}', '']
    (DEVICE / 'Android.bp').write_text('\n'.join(bp))
    with (DEVICE / 'device.mk').open('a') as stream:
        stream.write('\nPRODUCT_PACKAGES += ' + ' '.join(modules) + '\n')
    # Retain factory HAL/VNDK requirements; native build supplies its SystemSDK.
    matrix = ET.parse(HERE / 'factory-device-matrix.xml')
    assert [x.text for x in matrix.getroot().findall('system-sdk/version')] == ['28']
    for node in list(matrix.getroot().findall('system-sdk')):
        matrix.getroot().remove(node)
    matrix.write(DEVICE / 'compatibility_matrix.xml', encoding='utf-8', xml_declaration=True)
    link = ROOT / 'out-pchm30-vendor-native1'
    OUT.mkdir(parents=True, exist_ok=True)
    if link.exists() or link.is_symlink():
        assert link.is_symlink() and link.resolve() == OUT.resolve(), 'Output mapping differs'
    else:
        link.symlink_to(OUT, target_is_directory=True)
    targets = modules + ['vendor_compatibility_matrix.xml', 'debugfs', 'e2fsck', 'simg2img', 'avbtool', 'checkvintf', 'secilc', 'deapexer', 'signapk']
    (HERE / 'generated').mkdir(exist_ok=True)
    (HERE / 'generated/build-targets.txt').write_text('\n'.join(targets) + '\n')
    state = {'run': str(run), 'input_images': str(images), 'platform': platform,
             'source_manifest': head, 'archive': str(archive), 'phone_written': False,
             'full_system_rebuild_requested': False, 'apps': [], 'install_zip_created': False}
    save(STATE, state)
    print('Saved system reused. Building five android_app_import modules, 15 ODM dex_import libraries, ARM64 dexpreopt, and host tools.', flush=True)


def replace_file(reader, img, path, content, run):
    """Replace one regular file in a private image copy; retain inode permissions/xattrs."""
    assert img.parent == run / 'candidate' and img.name in ('system.img', 'vendor.img')
    assert re.fullmatch(r'/[A-Za-z0-9_./@+-]+', path) and '..' not in PurePosixPath(path).parts
    before = reader.run(img, 'stat ' + path)
    assert 'Type: regular' in before and re.search(r'Links:\s+1\b', before), 'Target is not a singly-linked regular file: ' + path
    mode = re.search(r'Mode:\s+(0[0-7]+)', before).group(1)
    uid, gid = re.search(r'User:\s+(\d+)\s+Group:\s+(\d+)', before).groups()
    attrs = re.findall(r'^\s+([A-Za-z0-9_.-]+) \(\d+\)', reader.run(img, 'ea_list ' + path), re.M)
    assert 'security.selinux' in attrs, 'Missing original SELinux label: ' + path
    xattrs = []
    for i, name in enumerate(attrs):
        f = run / 'xattrs' / (str(reader.count) + '-' + str(i))
        f.parent.mkdir(exist_ok=True)
        reader.run(img, 'ea_get -f ' + str(f) + ' ' + path + ' ' + name)
        assert f.is_file() and f.stat().st_size > 0
        xattrs.append((name, f))
    reader.run(img, 'rm ' + path)
    assert not reader.exists(img, path)
    reader.run(img, 'write ' + str(content) + ' ' + path)
    assert reader.exists(img, path)
    for field, value in [('mode', '0' + format(0o100000 | int(mode, 8), 'o')), ('uid', uid), ('gid', gid)]:
        reader.run(img, 'set_inode_field ' + path + ' ' + field + ' ' + value)
    for name, f in xattrs:
        reader.run(img, 'ea_set -f ' + str(f) + ' ' + path + ' ' + name)
    after = reader.run(img, 'stat ' + path)
    assert re.search(r'Mode:\s+' + re.escape(mode) + r'\b', after)
    assert re.search(r'User:\s+' + uid + r'\s+Group:\s+' + gid + r'\b', after)
    check = run / ('readback-' + str(reader.count))
    assert reader.file(img, path, check)
    assert audit.digest(check) == audit.digest(content), 'Image file write/read-back mismatch'
    for name, f in xattrs:
        check = run / ('xattr-readback-' + str(reader.count))
        reader.run(img, 'ea_get -f ' + str(check) + ' ' + path + ' ' + name)
        assert check.read_bytes() == f.read_bytes(), 'Extended attribute differs: ' + name


def patch_framework_matrix(path):
    tree = ET.parse(path)
    root = tree.getroot()
    assert root.tag == 'compatibility-matrix' and root.get('type') == 'framework'
    for name, version, interface, instance in sorted(image.LEGACY_HAL_INSTANCES):
        present = any(h.findtext('name') == name and h.findtext('version') == version and
                      any(i.findtext('name') == interface and instance in [v.text for v in i.findall('instance')]
                          for i in h.findall('interface')) for h in root.findall('hal'))
        if present:
            continue
        h = ET.SubElement(root, 'hal', {'format': 'hidl', 'optional': 'true'})
        ET.SubElement(h, 'name').text = name
        ET.SubElement(h, 'version').text = version
        i = ET.SubElement(h, 'interface')
        ET.SubElement(i, 'name').text = interface
        ET.SubElement(i, 'instance').text = instance
    ET.indent(tree)
    tree.write(path, encoding='utf-8', xml_declaration=True)


def native_apps(state, logs):
    run = Path(state['run'])
    signer = OUT / 'host/linux-x86/framework/signapk.jar'
    javas = sorted(ROOT.glob('prebuilts/jdk/jdk*/linux-x86/bin/java'), key=lambda p: int(re.search(r'jdk(\d+)', str(p)).group(1)))
    assert javas and signer.is_file(), 'Native SignApk output missing'
    for app in APPS:
        name = Path(app['logical_path']).name
        candidates = list((PRODUCT / 'vendor/app').glob('*/' + name))
        assert len(candidates) == 1, 'Native signed APK output not unique: ' + name
        signed = candidates[0]
        assert apk.certificates(signed) == state['platform'], 'Native APK signer differs from the saved system'
        apk.content_identity(HERE / 'payload/apks' / name, signed)
        vdex = list((signed.parent / 'oat/arm64').glob('*.vdex'))
        if not vdex:
            intermediates = OUT / 'soong/.intermediates/device/oppo/PCHM30_vendorport' / app['module']
            vdex = [p for p in intermediates.rglob('*.vdex') if 'arm64' in p.parts]
        assert vdex and all(p.stat().st_size > 0 for p in vdex), 'Native ARM64 dexpreopt output missing: ' + name
        for p in vdex:
            with p.open('rb') as f:
                assert f.read(4) == b'vdex', 'Unexpected native VDEX file: ' + str(p)
        checked([javas[-1], '-Djava.library.path=' + str(OUT / 'host/linux-x86/lib64'),
                 '--class-path', signer, HERE / 'VerifyApk.java', signed], logs / (name + '-verify-signature.log'))
        record = dict(app, signed_path=str(signed), signed_sha256=audit.digest(signed),
                      native_arm64_vdex=[str(p) for p in vdex], native_payload_unchanged=True,
                      apk_signature_verified=True)
        state['apps'].append(record)
        print('NATIVE_APK_AND_ARM64_DEXPREOPT_OK:', name, flush=True)
    assert len(state['apps']) == 5
    state['odm_jar_native_verification'] = []
    for lib in JARS:
        module = lib['module']
        installed = PRODUCT / 'vendor/framework' / (module + '.jar')
        assert installed.is_file(), 'Native ODM Java import missing: ' + module
        apk.content_identity(HERE / 'payload/jars' / Path(lib['path']).name, installed)
        intermediates = OUT / 'soong/.intermediates/device/oppo/PCHM30_vendorport' / module
        vdex = [p for p in intermediates.rglob('*.vdex') if 'arm64' in p.parts]
        vdex += list((PRODUCT / 'vendor/framework/oat/arm64').glob(module + '.vdex'))
        assert vdex and all(p.stat().st_size > 0 for p in vdex), 'Native ODM library ARM64 dexpreopt output missing: ' + module
        state['odm_jar_native_verification'].append(dict(lib, native_vdex=[str(p) for p in vdex]))
    assert len(state['odm_jar_native_verification']) == 15


def candidate_images(state, logs):
    run, inputs = Path(state['run']), Path(state['input_images'])
    candidate = run / 'candidate'
    candidate.mkdir()
    reader = ImageEditor(TOOLS / 'debugfs', logs, candidate)
    checked([TOOLS / 'simg2img', inputs / 'system.img', candidate / 'system.img'], logs / 'unsparse-system.log')
    shutil.copyfile(inputs / 'vendor.img', candidate / 'vendor.img')
    for part in ('system', 'vendor'):
        checked([TOOLS / 'avbtool', 'info_image', '--image', candidate / (part + '.img')], logs / (part + '-avb-before.log'))
        checked([TOOLS / 'avbtool', 'erase_footer', '--image', candidate / (part + '.img')], logs / (part + '-erase-footer.log'))
    vendor = candidate / 'vendor.img'
    # A byte-identical source and five native migrated consumers precede the contract update.
    for app in state['apps']:
        path = app['logical_path'].removeprefix('/vendor')
        source = run / 'verify-original' / Path(path).name
        assert reader.file(inputs / 'vendor.img', path, source)
        assert audit.digest(source) == app['sha256']
        replace_file(reader, vendor, path, Path(app['signed_path']), run)
        for suffix in ('odex', 'vdex', 'art'):
            stale = str(PurePosixPath(path).parent / 'oat/arm64' / (Path(path).stem + '.' + suffix))
            if reader.exists(vendor, stale):
                reader.run(vendor, 'rm ' + stale)
                assert not reader.exists(vendor, stale)
    matrix = PRODUCT / 'vendor/etc/vintf/compatibility_matrix.xml'
    assert matrix.is_file(), 'Native device matrix output missing'
    root = ET.parse(matrix).getroot()
    versions = [v.text for v in root.findall('system-sdk/version')]
    assert versions and '28' not in versions and set(versions) <= {str(v) for v in range(29, 37)}, 'Unexpected native SystemSDK contract'
    assert root.findtext('vendor-ndk/version') == '30', 'Native matrix lost VNDK30'
    state['vendor_systemsdk_versions'] = versions
    state['old_sdk28_contract_retired_after_native_consumer_migration'] = True
    replace_file(reader, vendor, '/etc/vintf/compatibility_matrix.xml', matrix, run)
    framework = run / 'framework-compatibility_matrix.device.xml'
    path = '/system/etc/vintf/compatibility_matrix.device.xml'
    assert reader.file(candidate / 'system.img', path, framework)
    patch_framework_matrix(framework)
    replace_file(reader, candidate / 'system.img', path, framework, run)
    # Preserve the exact nested ODM, including its original telephony selector.
    embedded = run / 'odm.img'
    assert reader.file(vendor, '/euclid/odm.img', embedded)
    assert embedded.stat().st_size == 703217664
    assert audit.digest(embedded) == json.loads((HERE / 'expected-embedded-odm.json').read_text())['sha256']
    state['embedded_odm_unchanged'] = True
    e2fsck = TOOLS / 'e2fsck' if (TOOLS / 'e2fsck').is_file() else shutil.which('e2fsck') or shutil.which('fsck.ext4')
    assert e2fsck, 'e2fsck is required before finalizing candidate images'
    for part in ('system', 'vendor'):
        img = candidate / (part + '.img')
        checked([e2fsck, '-f', '-n', img], logs / (part + '-ext4-check.log'))
        # Use the original hash algorithm; omit FEC to fit existing physical sizes.
        original_info = (logs / (part + '-avb-before.log')).read_text()
        algorithm = re.search(r'Hash Algorithm:\s+(sha1|sha256)\b', original_info)
        assert algorithm, 'Cannot identify the original AVB tree algorithm'
        checked([TOOLS / 'avbtool', 'add_hashtree_footer', '--image', img,
                 '--partition_name', part, '--partition_size', str(SIZES[part]),
                 '--hash_algorithm', algorithm.group(1), '--do_not_generate_fec'], logs / (part + '-avb-new.log'))
        assert img.stat().st_size == SIZES[part]
        checked([TOOLS / 'avbtool', 'verify_image', '--image', img], logs / (part + '-avb-verify.log'))
    for part in ('boot', 'dtbo'):
        shutil.copyfile(inputs / (part + '.img'), candidate / (part + '.img'))
    args = [TOOLS / 'avbtool', 'make_vbmeta_image', '--output', candidate / 'vbmeta.img',
            '--key', ROOT / 'external/avb/test/data/testkey_rsa4096.pem', '--algorithm', 'SHA256_RSA4096',
            '--flags', '3', '--padding_size', '65536', '--rollback_index', '0']
    for part in ('system', 'vendor', 'boot', 'dtbo'):
        args += ['--include_descriptors_from_image', candidate / (part + '.img')]
    checked(args, logs / 'vbmeta-new.log')
    checked([TOOLS / 'avbtool', 'verify_image', '--image', candidate / 'vbmeta.img'], logs / 'vbmeta-verify.log')
    state['images'] = {p: {'bytes': (candidate / (p + '.img')).stat().st_size,
                           'sha256': audit.digest(candidate / (p + '.img'))} for p in SIZES}
    return reader, candidate, embedded


def compatibility(state, reader, candidate, embedded, logs):
    run = Path(state['run'])
    view = run / 'view'
    image.collect_system_metadata(reader, candidate / 'system.img', view)
    audit.export_metadata(reader, candidate / 'vendor.img', view / 'vendor')
    audit.export_metadata(reader, embedded, view / 'odm-source')
    reader.directory(candidate / 'vendor.img', '/apex', view / 'vendor/apex')
    reader.directory(embedded, '/apex', view / 'odm-source/apex')
    (view / 'odm').symlink_to(view / 'odm-source', target_is_directory=True)
    active = image.make_apex_view(view, run, logs, reader)
    state['vintf'] = {}
    for mode in ('dsds', 'ssss'):
        odm = view / ('odm-' + mode)
        shutil.copytree(view / 'odm-source', odm, symlinks=True)
        image.materialize_telephony(odm, mode)
        args = [TOOLS / 'checkvintf', '--check-compat']
        for part in ('system', 'system_ext', 'product', 'vendor'):
            args += ['--dirmap', '/' + part + ':' + str(view / part)]
        args += ['--dirmap', '/odm:' + str(odm), '--dirmap', '/apex:' + str(active),
                 '--property', 'apex.all.ready=true', '--property', 'ro.product.first_api_level=28',
                 '--kernel', '4.14.180:' + str(HERE / 'stock-kernel.config')]
        state['vintf'][mode] = audit.command(args, logs / ('vintf-' + mode + '.log'))
        print('Derived vendor VINTF:', mode, state['vintf'][mode], flush=True)
    for runtime, name in ((True, 'runtime'), (False, 'strict-review')):
        state['selinux_' + name] = audit.command(audit.selinux_args(TOOLS / 'secilc', view, run / ('policy-' + name), runtime), logs / ('selinux-' + name + '.log'))
    assert all(v == 0 for v in state['vintf'].values()), 'Actual VINTF mismatch remains; see logs, no installer will be issued'
    assert state['selinux_runtime'] == 0, 'SELinux runtime policy link failed; no installer will be issued'


def finish():
    state = json.loads(STATE.read_text())
    run = Path(state['run'])
    assert run.is_relative_to(WS / 'artifacts') and run.is_dir()
    logs = run / 'logs'
    logs.mkdir(exist_ok=True)
    for tool in ('debugfs', 'simg2img', 'avbtool', 'checkvintf', 'secilc', 'deapexer'):
        assert (TOOLS / tool).is_file(), 'Native host tool missing: ' + tool
    image.TOOLS = TOOLS
    image.HERE = HERE
    try:
        native_apps(state, logs)
        reader, candidate, embedded = candidate_images(state, logs)
        compatibility(state, reader, candidate, embedded, logs)
        state.update(device_boot_tested=False, stable_release=False,
                     entire_sdk28_restored=False, phone_written=False,
                     native_build_complete=True, install_zip_created=False,
                     vendor_derivation='original OPPO vendor + five native-migrated APKs + native device matrix')
        package_report = dict(state, install_zip_created=True)
        image.package(run, {p: candidate / (p + '.img') for p in SIZES}, package_report)
        state.update(package_report)
        destination = WS / 'DOWNLOAD-ROM-VENDOR-NATIVE1'
        # Vendor image is also supplied separately for inspection; the installer ZIP carries the full set.
        shutil.copyfile(candidate / 'vendor.img', destination / 'PCHM30-DERIVED-VENDOR-NATIVE1.img')
        (destination / 'PCHM30-DERIVED-VENDOR-NATIVE1.img.sha256').write_text(state['images']['vendor']['sha256'] + '  PCHM30-DERIVED-VENDOR-NATIVE1.img\n')
        print('CANDIDATE INSTALLER CREATED. Device boot, encryption and hardware remain untested.', flush=True)
    except Exception as e:
        state['error'] = str(e)
        print('ERROR:', e, flush=True)
        raise
    finally:
        save(run / 'REPORT.json', state)
        save(STATE, state)
        with zipfile.ZipFile(run / 'REPORT-LOGS.zip', 'w', zipfile.ZIP_DEFLATED) as z:
            for p in sorted(logs.glob('*.log')):
                z.write(p, 'logs/' + p.name)
            z.write(run / 'REPORT.json', 'REPORT.json')
        print('REPORT:', run / 'REPORT.json', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=('prepare', 'finish'))
    args = parser.parse_args()
    (prepare if args.stage == 'prepare' else finish)()
