"""Regression tests for Soong discovering Android.bp in source backups."""
from pathlib import Path
import errno
import hashlib
import os
import tempfile
import unittest
from unittest.mock import patch

from backup_paths import backup_base, prepare_backup_base


class BackupPathsTests(unittest.TestCase):
    def test_preserve_backups_outside_source_same_and_cross_device(self):
        for cross_device in (False, True):
            with self.subTest(cross_device=cross_device), tempfile.TemporaryDirectory() as temporary:
                work = Path(temporary)
                root = work / 'lineage'
                old = root / '.pchm30-source-baseline-backups'
                source = old / 'original/packages/modules/vndk/apex/Android.bp'
                source.parent.mkdir(parents=True)
                content = b'apex { name: "com.android.vndk.v34" }\n'
                source.write_bytes(content)
                with patch.dict(os.environ, {'PCHM30_SOURCE_BACKUP_ROOT': str(work / 'artifacts')}):
                    if cross_device:
                        with patch('shutil.os.rename', side_effect=OSError(errno.EXDEV, 'different filesystems')):
                            base = prepare_backup_base(root)
                    else:
                        base = prepare_backup_base(root)
                    self.assertFalse(old.exists())
                    self.assertFalse(base.is_relative_to(root.resolve()))
                    self.assertEqual(list(root.rglob('Android.bp')), [])
                    copied = list(base.rglob('Android.bp'))
                    self.assertEqual(len(copied), 1)
                    self.assertEqual(hashlib.sha256(copied[0].read_bytes()).digest(), hashlib.sha256(content).digest())
                    self.assertEqual(prepare_backup_base(root), base)
                    self.assertEqual(len(list(base.glob('relocated-*'))), 1)

    def test_reject_backup_target_inside_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'lineage'
            root.mkdir()
            with patch.dict(os.environ, {'PCHM30_SOURCE_BACKUP_ROOT': str(root / 'bad')}):
                with self.assertRaisesRegex(RuntimeError, 'outside'):
                    backup_base(root)


if __name__ == '__main__':
    unittest.main()
