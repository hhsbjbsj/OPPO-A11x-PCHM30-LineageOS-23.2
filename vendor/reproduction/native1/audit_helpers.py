#!/usr/bin/env python3
"""Prepare factory startup/vendor inputs and test them against the built system."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile

HERE = Path(__file__).resolve().parent
SYSTEM_SHA = '95f418c67931641e9bee4ab6cadf19a7243422a0fd9a9f61c68fc3b11e1dfb14'


def digest(path):
    value = hashlib.sha256()
    count = 0
    with path.open('rb') as stream:
        while data := stream.read(4 * 1024 * 1024):
            value.update(data)
            count += len(data)
            if count % (512 * 1024 * 1024) == 0:
                print('Input hash:', path.name, count // 2**20, 'MiB', flush=True)
    return value.hexdigest()


def inputs(workspace):
    folder = workspace / 'pchm30-los23.2-stock-inputs'
    if not (folder / 'images').is_dir():
        archive = workspace / 'PCHM30-LOS23.2-STOCK-INPUTS.zip'
        assert archive.is_file(), 'Upload the original factory-input ZIP to /workspace first'
        with zipfile.ZipFile(archive) as zipped:
            for member in zipped.infolist():
                path = PurePosixPath(member.filename)
                assert not path.is_absolute() and '..' not in path.parts
                assert path.parts and path.parts[0] == folder.name
                assert (member.external_attr >> 16) & 0o170000 != 0o120000
            zipped.extractall(workspace)
    expected = json.loads((HERE / 'expected-inputs.json').read_text())
    for name, info in expected['images'].items():
        path = folder / 'images' / name
        assert path.stat().st_size == info['bytes'], 'Unexpected size: ' + name
        assert digest(path) == info['sha256'], 'Factory input checksum differs: ' + name
    return folder / 'images'


def command(args, log):
    with log.open('w') as stream:
        stream.write('$ ' + ' '.join(map(str, args)) + '\n')
        stream.flush()
        result = subprocess.run(list(map(str, args)), stdout=stream, stderr=subprocess.STDOUT)
    return result.returncode


class ImageReader:
    def __init__(self, executable, logdir):
        self.executable = executable
        self.logdir = logdir
        self.count = 0

    def run(self, image, request):
        assert not request.startswith(('write ', 'rm ', 'set_inode_field '))
        self.count += 1
        result = subprocess.run([str(self.executable), '-R', request, str(image)],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (self.logdir / ('debugfs-%03d.log' % self.count)).write_text(result.stdout)
        return result.stdout

    def exists(self, image, path):
        return re.search(r'\bInode:\s+[1-9][0-9]*\b', self.run(image, 'stat ' + path)) is not None

    def directory(self, image, source, destination):
        if not self.exists(image, source):
            return False
        assert Path(source).name == destination.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        assert not destination.exists(), 'Refusing to overwrite extracted directory'
        self.run(image, 'rdump ' + source + ' ' + str(destination.parent))
        assert destination.is_dir(), 'Directory export failed: ' + source
        return True

    def file(self, image, source, destination):
        if not self.exists(image, source):
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        assert not destination.exists(), 'Refusing to overwrite extracted file'
        self.run(image, 'dump ' + source + ' ' + str(destination))
        assert destination.is_file(), 'File export failed: ' + source
        return True


def export_metadata(reader, image, destination, prefix=''):
    for directory in ('etc/vintf', 'etc/selinux', 'etc/init'):
        reader.directory(image, prefix + '/' + directory, destination / directory)
    for filename in ('build.prop', 'default.prop', 'ueventd.rc', 'etc/fstab.qcom', 'etc/oplus.fstab'):
        reader.file(image, prefix + '/' + filename, destination / filename)


def boot_inputs(source, output):
    blob = source.read_bytes()
    assert blob[:8] == b'ANDROID!'
    u32 = lambda offset: struct.unpack_from('<I', blob, offset)[0]
    size, ramdisk_size, page, version = u32(8), u32(16), u32(36), u32(40)
    assert version == 1 and page == 4096
    kernel = blob[page:page + size]
    assert hashlib.sha256(kernel).hexdigest() == 'd83bf44d06a1ed1aeb7c8d597bbccd627458e7619e8606218f33358d145a0f1b'
    offset = page + (size + page - 1) // page * page
    ramdisk = blob[offset:offset + ramdisk_size]
    output.mkdir(parents=True)
    (output / 'kernel').write_bytes(kernel)
    (output / 'ramdisk.cpio.gz').write_bytes(ramdisk)
    raw = gzip.decompress(ramdisk)
    position = 0
    exported = []
    while position + 110 <= len(raw):
        header = raw[position:position + 110]
        assert header[:6] in (b'070701', b'070702')
        length, namesize = int(header[54:62], 16), int(header[94:102], 16)
        position += 110
        assert 0 < namesize <= len(raw) - position
        name = raw[position:position + namesize - 1].decode().removeprefix('./')
        position = (position + namesize + 3) & ~3
        assert position + length <= len(raw)
        data = raw[position:position + length]
        position = (position + length + 3) & ~3
        if name == 'TRAILER!!!':
            break
        if name in ('fstab.qcom', 'oplus.fstab'):
            (output / name).write_bytes(data)
            exported.append(name)
    cmdline = blob[64:576].split(b'\0', 1)[0] + blob[608:1632].split(b'\0', 1)[0]
    return {'header_version': version, 'page_size': page, 'kernel_bytes': size,
            'kernel_sha256': hashlib.sha256(kernel).hexdigest(),
            'kernel_address': u32(12), 'ramdisk_address': u32(20), 'tags_address': u32(32),
            'cmdline': cmdline.decode(errors='replace'), 'exported_fstabs': exported,
            'kernel_release': '4.14.180-perf+', 'boot_image_rebuilt': False}


def selinux_args(tool, view, result, runtime):
    system, vendor = view / 'system/etc/selinux', view / 'vendor/etc/selinux'
    version = (vendor / 'plat_sepolicy_vers.txt').read_text().strip()
    assert re.fullmatch(r'[0-9]+\.[0-9]+', version)
    required = [system / 'plat_sepolicy.cil', system / 'mapping' / (version + '.cil'),
                vendor / 'plat_pub_versioned.cil', vendor / 'vendor_sepolicy.cil']
    for path in required:
        assert path.is_file(), 'Required SELinux policy file missing: ' + str(path)
    policies = [required[0], required[1]]
    optional = [system / 'mapping' / (version + '.compat.cil')]
    for partition in ('system_ext', 'product'):
        base = view / partition / 'etc/selinux'
        optional += [base / (partition + '_sepolicy.cil'), base / 'mapping' / (version + '.cil')]
        if partition == 'system_ext':
            optional += [base / 'mapping' / (version + '.compat.cil')]
    policies += [p for p in optional if p.is_file()]
    policies += required[2:]
    odm = view / 'odm/etc/selinux/odm_sepolicy.cil'
    if odm.is_file():
        policies.append(odm)
    # Runtime init uses -N; a separate strict run retains neverallow checks.
    args = [str(tool), '-m', '-M', 'true', '-G', '-c', '30']
    if runtime:
        args.append('-N')
    return args + ['-o', str(result), '-f', '/dev/null'] + list(map(str, policies))
