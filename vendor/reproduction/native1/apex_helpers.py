#!/usr/bin/env python3
"""Build a VINTF host APEX view from packages in the exact built system image."""
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import runpy
import shutil
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

HERE = Path(__file__).resolve().parent
SYSTEM_SHA = '95f418c67931641e9bee4ab6cadf19a7243422a0fd9a9f61c68fc3b11e1dfb14'


def run(args, log):
    result = subprocess.run(list(map(str, args)), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    log.write_text('$ ' + ' '.join(map(str, args)) + '\n' + result.stdout + result.stderr)
    assert result.returncode == 0, 'APEX inspection failed; see ' + str(log)
    return result.stdout


def fs_type(path):
    with path.open('rb') as stream:
        head = stream.read(2048)
    if len(head) >= 1082 and head[1080:1082] == b'\x53\xef':
        return 'ext4'
    if len(head) >= 1028 and struct.unpack_from('<I', head, 1024)[0] == 0xE0F5E1E2:
        return 'erofs'
    raise AssertionError('Unrecognized APEX payload filesystem: ' + str(path))


def kernel_fs_support(config):
    flags = {}
    for line in config.read_text().splitlines():
        if line.startswith('CONFIG_') and '=' in line:
            key, value = line.split('=', 1)
            flags[key] = value
    # Early APEX activation must not depend on loading a module from /data.
    return {'ext4': flags.get('CONFIG_EXT4_FS') == 'y',
            'erofs': flags.get('CONFIG_EROFS_FS') == 'y'}


def info_entry(manifest, partition, module_path):
    name = manifest['name']
    assert re.fullmatch(r'[A-Za-z0-9_.+-]+', name) and name not in ('.', '..'), 'Invalid APEX module name'
    version = int(manifest['version'])
    assert 0 < version < 2**63
    assert partition in ('SYSTEM', 'SYSTEM_EXT', 'PRODUCT', 'VENDOR', 'ODM')
    return {'moduleName': name, 'modulePath': module_path,
            'preinstalledModulePath': module_path, 'versionCode': str(version),
            'versionName': str(manifest.get('versionName', '')),
            'isFactory': 'true', 'isActive': 'true', 'lastUpdateMillis': '0',
            'provideSharedApexLibs': 'true' if manifest.get('provideSharedApexLibs', False) else 'false',
            'partition': partition}


def write_info_list(entries, output):
    assert entries, 'Refusing to create an empty APEX catalog'
    names = [entry['moduleName'] for entry in entries]
    assert len(names) == len(set(names)), 'Duplicate preinstalled APEX module requires review'
    root = ET.Element('apex-info-list')
    for entry in sorted(entries, key=lambda x: x['moduleName']):
        ET.SubElement(root, 'apex-info', entry)
    ET.indent(root)
    ET.ElementTree(root).write(output, encoding='utf-8', xml_declaration=True)
