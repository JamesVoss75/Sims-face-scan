from tests.helpers import write_package as _write_package
from ts4face.dbpf import Package, _refpack_decompress


def test_read_plain_and_zlib(tmp_path):
    p = tmp_path / "t.package"
    _write_package(p, [
        (0xC5F6763E, 0, 0x8088D1E4B2013F98, b"smod-bytes", False),
        (0x03B33DDF, 0, 0x1234, b"<I>xml</I>" * 50, True),
    ])
    with Package(str(p)) as pkg:
        assert len(pkg.entries) == 2
        smod = pkg.find(0xC5F6763E)[0]
        assert smod.instance == 0x8088D1E4B2013F98
        assert pkg.read(smod) == b"smod-bytes"
        assert pkg.read(pkg.find(instance=0x1234)[0]) == b"<I>xml</I>" * 50


def test_refpack_literal_and_copy():
    # header: flags 0x10, magic 0xFB, 3-byte size 6; literal "abc" via 0xE0 (4 literals) is too many,
    # so use a 2-byte copy command with 3 plain bytes then copy 3 from distance 3, then stop.
    data = bytes([0x10, 0xFB, 0x00, 0x00, 0x06, 0b0000_0011, 0x02, ord("a"), ord("b"), ord("c"), 0xFC])
    assert _refpack_decompress(data) == b"abcabc"
