from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import audit_helpers as audit
import apex_helpers as apex
HERE = Path(__file__).resolve().parent
WORKSPACE = Path('/workspace')
ROOT = Path('/opt/lineage')
TOOLS = WORKSPACE / 'out-los23.2-vendor-native1/host/linux-x86/bin'
CHUNK_BYTES = 512 * 2**20
SIZES = {'system': 5473566720, 'vendor': 1681915904, 'boot': 100663296, 'dtbo': 25165824, 'vbmeta': 65536}
NODES = {'system': 'sda7', 'vendor': 'sde16', 'boot': 'sde11', 'dtbo': 'sde18', 'vbmeta': 'sde17'}
LEGACY_HAL_INSTANCES = {('android.hardware.gnss', '1.0', 'IGnss', 'gnss_vendor'), ('android.hardware.memtrack', '1.0', 'IMemtrack', 'default'), ('android.hardware.wifi.hostapd', '1.2', 'IHostapd', 'wigighostapd')}

def stamp():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def checked(args, log):
    code = audit.command(args, log)
    if code:
        print('\n'.join(log.read_text(errors='replace').splitlines()[-90:]), flush=True)
        raise RuntimeError('Command failed (%d); see %s' % (code, log))


def materialize_telephony(odm, mode):
    assert mode in ('dsds', 'ssss')
    link = odm / 'etc/vintf/manifest/telephony_manifest.xml'
    assert link.is_symlink() and str(link.readlink()) == '/proc/oppoVersion/telephony_manifest', \
        'Unexpected telephony selector; refusing to guess its meaning'
    variant = odm / ('etc/vintf/telephony_manifest_' + mode + '.xml')
    tree = ET.parse(variant)
    assert tree.getroot().tag == 'manifest' and tree.getroot().get('type') == 'device'
    link.unlink()
    shutil.copyfile(variant, link)
    return {'mode': mode, 'factory_variant': str(variant),
            'sha256': audit.digest(variant),
            'scope': 'host metadata copy only; original embedded ODM and proc selector retained'}


def boot_payloads(path):
    with path.open('rb') as stream:
        header = stream.read(4096)
        assert header[:8] == b'ANDROID!'
        kernel_size, ramdisk_size = struct.unpack_from('<I', header, 8)[0], struct.unpack_from('<I', header, 16)[0]
        page, version = struct.unpack_from('<II', header, 36)
        assert page == 4096 and version == 1
        assert 0 < kernel_size < SIZES['boot'] and 0 < ramdisk_size < SIZES['boot']
        stream.seek(page)
        kernel = stream.read(kernel_size)
        stream.seek(page + ((kernel_size + page - 1) // page) * page)
        ramdisk = stream.read(ramdisk_size)
        assert len(kernel) == kernel_size and len(ramdisk) == ramdisk_size
    return {'kernel': hashlib.sha256(kernel).hexdigest(), 'ramdisk': hashlib.sha256(ramdisk).hexdigest()}


def collect_system_metadata(reader, raw, destination):
    assert reader.exists(raw, '/system/build.prop'), 'Native system-as-root layout changed'
    for part, prefix in (('system', '/system'), ('system_ext', '/system/system_ext'), ('product', '/system/product')):
        audit.export_metadata(reader, raw, destination / part, prefix)
        reader.directory(raw, prefix + '/apex', destination / part / 'apex')


def make_apex_view(view, output, logs, reader):
    active = output / 'apex'
    active.mkdir()
    entries, inventory = [], []
    with tempfile.TemporaryDirectory(prefix='payload-', dir=output) as temporary:
        temp = Path(temporary)
        for part in ('system', 'system_ext', 'product', 'vendor', 'odm'):
            directory = view / part / 'apex'
            if not directory.is_dir():
                continue
            for package in sorted(directory.iterdir()):
                if package.suffix not in ('.apex', '.capex'):
                    continue
                number = len(entries) + 1
                print('APEX in new system:', part, package.name, flush=True)
                current = temp / str(number)
                current.mkdir()
                actual = package
                with zipfile.ZipFile(package) as zipped:
                    if 'original_apex' in zipped.namelist():
                        actual = current / 'original.apex'
                        with zipped.open('original_apex') as source, actual.open('xb') as target:
                            shutil.copyfileobj(source, target, 4 * 2**20)
                manifest = json.loads(apex.run([TOOLS / 'deapexer', 'info', actual], logs / ('apex-%d.log' % number)))
                entry = apex.info_entry(manifest, part.upper(), '/' + part + '/apex/' + package.name)
                assert not (active / entry['moduleName']).exists(), 'Duplicate active APEX'
                target_dir = active / entry['moduleName']
                target_dir.mkdir()
                with zipfile.ZipFile(actual) as zipped:
                    payload = current / 'payload.img'
                    with zipped.open('apex_payload.img') as source, payload.open('xb') as target:
                        shutil.copyfileobj(source, target, 4 * 2**20)
                    (target_dir / 'apex_manifest.pb').write_bytes(zipped.read('apex_manifest.pb'))
                filesystem = apex.fs_type(payload)
                assert apex.kernel_fs_support(HERE / 'stock-kernel.config').get(filesystem), \
                    'New APEX filesystem unsupported by the selected stock kernel: ' + package.name
                assert filesystem == 'ext4', 'Unsupported export path; retain error rather than omit APEX metadata'
                reader.directory(payload, '/etc/vintf', target_dir / 'etc/vintf')
                entries.append(entry)
                inventory.append({'name': entry['moduleName'], 'partition': part,
                                  'package_sha256': audit.digest(package), 'filesystem': filesystem})
    assert any(e['moduleName'] == 'com.android.vndk.v30' for e in entries)
    apex.write_info_list(entries, active / 'apex-info-list.xml')
    write_json(output / 'APEX-INVENTORY.json', inventory)
    return active


def image_chunks(path, part):
    size = path.stat().st_size
    assert 0 < size <= SIZES[part] and size % 4096 == 0, 'Image size exceeds partition or is not block-aligned: ' + part
    offset = 0
    while offset < size:
        length = min(CHUNK_BYTES, size - offset)
        yield part, offset, length
        offset += length


def write_image_chunks(zipped, path, part):
    chunks = []
    with path.open('rb') as source:
        for _, offset, size in image_chunks(path, part):
            name = 'images/%s.%03d.raw' % (part, len(chunks))
            value = hashlib.sha256()
            print('Packaging:', name, size // 2**20, 'MiB', flush=True)
            with zipped.open(name, 'w') as output:
                remaining = size
                while remaining:
                    data = source.read(min(4 * 2**20, remaining))
                    assert data, 'Truncated raw image'
                    value.update(data)
                    output.write(data)
                    remaining -= len(data)
            chunks.append({'file': name, 'partition': part, 'offset': offset, 'bytes': size, 'sha256': value.hexdigest()})
    return chunks


def package(run, sources, report):
    destination = WORKSPACE / 'DOWNLOAD-ROM-VENDOR-NATIVE1'
    destination.mkdir(exist_ok=True)
    name = 'PCHM30-LOS23.2-VENDOR-NATIVE1-' + stamp() + '.zip'
    partial = destination / (name + '.partial')
    final = destination / name
    chunks = []
    # Classic ZIP uses unsigned 32-bit offsets. Python's conservative default
    # switches to ZIP64 at 2GiB; keep the actual format limit for PBRP busybox.
    zipfile.ZIP64_LIMIT = 0xffffffff
    with zipfile.ZipFile(partial, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as zipped:
        # System/vendor first, boot and vbmeta last; no recovery/GPT/data images.
        for part in ('system', 'vendor', 'dtbo', 'boot', 'vbmeta'):
            chunks += write_image_chunks(zipped, sources[part], part)
        lines = ['%s %s %s %s %s' % (c['partition'], c['offset'] // 4096, c['bytes'] // 4096, c['sha256'], c['file']) for c in chunks]
        zipped.writestr('chunks.list', '\n'.join(lines) + '\n')
        zipped.writestr('partition-sizes.list', '\n'.join('%s %s %s' % (p, SIZES[p], NODES[p]) for p in SIZES) + '\n')
        installer = (HERE / 'update-binary.sh').read_bytes()
        entry = zipfile.ZipInfo('META-INF/com/google/android/update-binary')
        entry.create_system = 3
        entry.external_attr = 0o100755 << 16
        entry.compress_type = zipfile.ZIP_DEFLATED
        zipped.writestr(entry, installer)
        zipped.writestr('META-INF/com/google/android/updater-script', '# PCHM30 native full TEST1; see the device-specific update-binary.\n')
        zipped.writestr('BUILD-REPORT.json', json.dumps(report, indent=2) + '\n')
        zipped.writestr('README.txt', (HERE / 'README.txt').read_text(encoding='utf-8'))
    # PBRP busybox interoperability: no >4GiB ZIP archive or individual entry.
    # Chunks avoid ZIP64 payload entries even though raw system.img exceeds 4GiB.
    assert partial.stat().st_size < 0xffffffff, 'Candidate exceeds tested classic ZIP limits; use a different installer, do not flash this partial'
    with zipfile.ZipFile(partial) as zipped:
        assert {c['partition'] for c in chunks} == set(SIZES)
        assert all(i.file_size < 0xffffffff and i.extract_version < 45 for i in zipped.infolist())
        assert not any('recovery.img' in n or 'super.img' in n for n in zipped.namelist())
        for c in chunks:
            assert zipped.getinfo(c['file']).file_size == c['bytes']
    partial.rename(final)
    write_json(run / 'CHUNKS.json', chunks)
    report['candidate_zip'] = str(final)
    report['candidate_zip_sha256'] = audit.digest(final)
    report['candidate_zip_bytes'] = final.stat().st_size
    write_json(destination / (name + '.json'), report)
    (destination / (name + '.sha256')).write_text(report['candidate_zip_sha256'] + '  ' + name + '\n')
    print('Candidate PBRP ZIP:', final, flush=True)
    return final
