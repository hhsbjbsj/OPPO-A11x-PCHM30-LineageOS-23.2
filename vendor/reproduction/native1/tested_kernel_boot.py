"""Preserve a PCHM30 v1 boot ramdisk and appended DTBs when replacing its kernel."""
import gzip
import hashlib
import struct
import zlib


def aligned(n, page=4096):
    return (n + page - 1) // page * page


def parts(blob):
    assert blob[:8] == b'ANDROID!' and len(blob) >= 4096
    u32 = lambda offset: struct.unpack_from('<I', blob, offset)[0]
    assert u32(36) == 4096 and u32(40) == 1
    assert u32(24) == 0 and u32(1632) == 0, 'Unsupported extra boot components'
    assert struct.unpack_from('<Q', blob, 1636)[0] == 0 and u32(1644) == 1648
    ks, rs = u32(8), u32(16)
    offset = 4096 + aligned(ks)
    assert 0 < ks and 0 < rs and offset + rs <= len(blob)
    kernel, ramdisk = blob[4096:4096+ks], blob[offset:offset+rs]
    h = hashlib.sha1()
    for p in (kernel, ramdisk, b'', b''):
        h.update(p)
        h.update(struct.pack('<I', len(p)))
    assert h.digest() == blob[576:596], 'Input boot image ID mismatch'
    return blob[:4096], kernel, ramdisk


def replace_kernel(stock, image):
    header, kernel, ramdisk = parts(stock)
    assert image[56:60] == b'ARM\x64', 'Expected a raw ARM64 Image'
    assert kernel[:2] == b'\x1f\x8b', 'Original PCHM30 kernel is not gzip'
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    original_image = decoder.decompress(kernel)
    assert decoder.eof and original_image[56:60] == b'ARM\x64'
    dtbs = decoder.unused_data
    assert len(dtbs) > 100000 and dtbs[:4] == b'\xd0\x0d\xfe\xed', 'Expected original appended DTBs'
    new_kernel = gzip.compress(image, compresslevel=9, mtime=0) + dtbs
    out_header = bytearray(header)
    struct.pack_into('<I', out_header, 8, len(new_kernel))
    digest = hashlib.sha1()
    for p in (new_kernel, ramdisk, b'', b''):
        digest.update(p)
        digest.update(struct.pack('<I', len(p)))
    out_header[576:608] = digest.digest() + bytes(12)
    result = bytes(out_header) + new_kernel + bytes(aligned(len(new_kernel)) - len(new_kernel))
    result += ramdisk + bytes(aligned(len(ramdisk)) - len(ramdisk))
    new_header, check_kernel, check_ramdisk = parts(result)
    check = zlib.decompressobj(16 + zlib.MAX_WBITS)
    assert check.decompress(check_kernel) == image and check.unused_data == dtbs
    assert check_ramdisk == ramdisk
    expected = bytearray(header)
    expected[8:12] = new_header[8:12]
    expected[576:608] = new_header[576:608]
    assert bytes(expected) == new_header, 'Unexpected boot header change'
    report = {'ramdisk_sha256': hashlib.sha256(ramdisk).hexdigest(),
              'original_dtbs_sha256': hashlib.sha256(dtbs).hexdigest(),
              'original_dtbs_bytes': len(dtbs), 'original_dtbs_retained': True,
              'kernel_image_sha256': hashlib.sha256(image).hexdigest(),
              'new_kernel_field_sha256': hashlib.sha256(new_kernel).hexdigest(),
              'boot_image_id_valid': True, 'boot_payload_bytes': len(result)}
    return result, report
