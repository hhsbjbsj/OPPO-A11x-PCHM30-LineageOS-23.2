"""Host-independent checks; these do not claim CNB native compilation or boot."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

import apk_identity as apk
import image_support as image
import port


class IntegrityTests(unittest.TestCase):
    def test_framework_matrix_is_idempotent_and_keeps_existing_hal(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / 'matrix.xml'
            p.write_text('<compatibility-matrix version="1.0" type="framework"><hal format="aidl"><name>vendor.original</name><version>1</version><interface><name>IOriginal</name><instance>default</instance></interface></hal></compatibility-matrix>')
            port.patch_framework_matrix(p)
            before = p.read_bytes()
            port.patch_framework_matrix(p)
            self.assertEqual(before, p.read_bytes())
            self.assertEqual(len(ET.parse(p).getroot().findall('hal')), 4)
            self.assertIn(b'vendor.original', before)

    def test_wrong_device_backup_is_rejected(self):
        b = io.BytesIO()
        with zipfile.ZipFile(b, 'w') as z:
            z.writestr('META/misc_info.txt', 'system_size=1234\n')
        with zipfile.ZipFile(io.BytesIO(b.getvalue())) as z:
            with self.assertRaises(AssertionError):
                port.archive_manifest(z)

    def test_apk_payload_modification_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / 'old.apk', Path(temp) / 'new.apk'
            for path, payload in ((a, b'original'), (b, b'changed')):
                with zipfile.ZipFile(path, 'w') as z:
                    z.writestr('classes.dex', payload)
            with self.assertRaises(AssertionError):
                apk.content_identity(a, b)

    def test_real_chunk_packaging_ranges_and_digests(self):
        saved = image.WORKSPACE, image.SIZES, image.CHUNK_BYTES
        with tempfile.TemporaryDirectory() as temp:
            try:
                base = Path(temp)
                image.WORKSPACE = base
                image.CHUNK_BYTES = 8192
                image.SIZES = {p: 20480 for p in saved[1]}
                run = base / 'run'
                run.mkdir()
                sources = {}
                for i, part in enumerate(image.SIZES):
                    sources[part] = run / (part + '.img')
                    sources[part].write_bytes(bytes([i + 1]) * 20480)
                report = {'fixture': True, 'phone_written': False}
                result = image.package(run, sources, report)
                with zipfile.ZipFile(result) as z:
                    self.assertIsNone(z.testzip())
                    rows = z.read('chunks.list').decode().splitlines()
                    self.assertEqual(len(rows), 15)
                    self.assertTrue(all(i.extract_version < 45 for i in z.infolist()))
                    self.assertEqual(z.read('META-INF/com/google/android/update-binary'), (image.HERE / 'update-binary.sh').read_bytes())
                    for part in sources:
                        actual = b''
                        next_offset = 0
                        for row in rows:
                            part2, offset, blocks, sha, name = row.split()
                            if part2 != part:
                                continue
                            self.assertEqual(int(offset) * 4096, next_offset)
                            data = z.read(name)
                            self.assertEqual(len(data), int(blocks) * 4096)
                            self.assertEqual(hashlib.sha256(data).hexdigest(), sha)
                            actual += data
                            next_offset += len(data)
                        self.assertEqual(actual, sources[part].read_bytes())
            finally:
                image.WORKSPACE, image.SIZES, image.CHUNK_BYTES = saved


if __name__ == '__main__':
    unittest.main()
