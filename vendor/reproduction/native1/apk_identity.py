import hashlib
from pathlib import Path
import struct
import zipfile

def lp(data, pos):
    size = struct.unpack_from('<I', data, pos)[0]
    end = pos + 4 + size
    assert end <= len(data)
    return data[pos + 4:end], end


def certificates(path):
    """Read signer certificate identity, not a cryptographic signature verdict."""
    data = path.read_bytes()
    eocd = data.rfind(b'PK\x05\x06', max(0, len(data) - 65557))
    assert eocd >= 0
    central = struct.unpack_from('<I', data, eocd + 16)[0]
    assert data[central - 16:central] == b'APK Sig Block 42', 'APK v2/v3 certificate reader needs a signing block: ' + str(path)
    size = struct.unpack_from('<Q', data, central - 24)[0]
    pos, end = central - size, central - 24
    found = set()
    while pos < end:
        length = struct.unpack_from('<Q', data, pos)[0]
        ident = struct.unpack_from('<I', data, pos + 8)[0]
        assert length >= 4 and pos + 8 + length <= end
        value = data[pos + 12:pos + 8 + length]
        pos += 8 + length
        if ident not in (0x7109871a, 0xf05368c0):
            continue
        signers, _ = lp(value, 0)
        index = 0
        while index < len(signers):
            signer, index = lp(signers, index)
            signed, _ = lp(signer, 0)
            _, cursor = lp(signed, 0)
            chain, _ = lp(signed, cursor)
            cursor = 0
            while cursor < len(chain):
                cert, cursor = lp(chain, cursor)
                found.add(hashlib.sha256(cert).hexdigest())
    assert found, 'No signer certificate found'
    return sorted(found)


def content_identity(before, after):
    with zipfile.ZipFile(before) as old, zipfile.ZipFile(after) as new:
        names = {n for n in old.namelist() if not n.endswith('/') and not n.upper().startswith('META-INF/')}
        assert names == {n for n in new.namelist() if not n.endswith('/') and not n.upper().startswith('META-INF/')}
        for name in names:
            assert old.read(name) == new.read(name), 'Signing changed payload: ' + name
