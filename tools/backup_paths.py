#!/usr/bin/env python3
"""Keep original source files outside the tree scanned by Soong."""
from pathlib import Path
import datetime
import os
import shutil


def backup_base(root):
    root = Path(root).resolve()
    configured = os.environ.get('PCHM30_SOURCE_BACKUP_ROOT')
    if configured:
        base = Path(configured).resolve()
    elif Path('/workspace').is_dir():
        base = Path('/workspace/artifacts/pchm30-source-baseline-backups').resolve()
    else:
        base = root.parent / '.pchm30-source-baseline-backups'
    base = (base / root.name).resolve()
    if base.is_relative_to(root):
        raise RuntimeError('Backup location must be outside the Android source tree: ' + str(base))
    return base


def prepare_backup_base(root):
    root = Path(root).resolve()
    base = backup_base(root)
    legacy = root / '.pchm30-source-baseline-backups'
    if legacy.is_symlink():
        raise RuntimeError('Refusing to relocate a symlink backup directory: ' + str(legacy))
    if legacy.exists():
        if not legacy.is_dir():
            raise RuntimeError('Legacy backup location is not a directory: ' + str(legacy))
        base.mkdir(parents=True, exist_ok=True)
        destination = base / ('relocated-' + datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        if destination.exists():
            raise RuntimeError('Relocation destination already exists: ' + str(destination))
        # shutil.move preserves symlinks and handles EXDEV with copy/remove.
        shutil.move(str(legacy), str(destination))
        print('Original source backups preserved outside Soong tree: ' + str(destination), flush=True)
    return base


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    print('Backup location: ' + str(prepare_backup_base(args.root)))
