"""Minimal read-only reader for Sims 4 DBPF 2.1 .package files.

Format reference: s4pi (github.com/s4ptacle/Sims4Tools, s4pi/Package/*) and
TS4 SimRipper.  Supports uncompressed, zlib (0x5A42) and RefPack (0xFFFF)
resources.  Never writes to a package.
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import BinaryIO, Iterator


@dataclass(frozen=True)
class Entry:
    type: int
    group: int
    instance: int
    offset: int
    file_size: int
    mem_size: int
    compression: int

    @property
    def tgi(self) -> str:
        return f"{self.type:08X}:{self.group:08X}:{self.instance:016X}"


def _refpack_decompress(data: bytes) -> bytes:
    """EA RefPack (QFS) decompression, as used by DBPF compression type 0xFFFF."""
    pos = 0
    flags = data[0]
    if data[1] != 0xFB:
        raise ValueError("not RefPack data")
    pos = 2
    size_len = 4 if flags & 0x80 else 3
    size = int.from_bytes(data[pos:pos + size_len], "big")
    pos += size_len
    out = bytearray()
    n = len(data)
    while pos < n:
        b0 = data[pos]
        if b0 < 0x80:
            b1 = data[pos + 1]
            plain = b0 & 0x03
            copy = ((b0 & 0x1C) >> 2) + 3
            dist = ((b0 & 0x60) << 3) + b1 + 1
            pos += 2
        elif b0 < 0xC0:
            b1, b2 = data[pos + 1], data[pos + 2]
            plain = (b1 & 0xC0) >> 6
            copy = (b0 & 0x3F) + 4
            dist = ((b1 & 0x3F) << 8) + b2 + 1
            pos += 3
        elif b0 < 0xE0:
            b1, b2, b3 = data[pos + 1], data[pos + 2], data[pos + 3]
            plain = b0 & 0x03
            copy = ((b0 & 0x0C) << 6) + b3 + 5
            dist = ((b0 & 0x10) << 12) + (b1 << 8) + b2 + 1
            pos += 4
        elif b0 < 0xFC:
            plain = ((b0 & 0x1F) << 2) + 4
            copy = 0
            dist = 0
            pos += 1
        else:
            plain = b0 & 0x03
            copy = 0
            dist = 0
            pos += 1
        out += data[pos:pos + plain]
        pos += plain
        for _ in range(copy):
            out.append(out[-dist])
        if b0 >= 0xFC:
            break
    if len(out) != size:
        raise ValueError(f"RefPack size mismatch {len(out)} != {size}")
    return bytes(out)


class Package:
    def __init__(self, path: str):
        self.path = path
        self._f: BinaryIO = open(path, "rb")
        hdr = self._f.read(96)
        if hdr[:4] != b"DBPF":
            raise ValueError(f"{path}: not a DBPF file")
        major, minor = struct.unpack_from("<II", hdr, 4)
        if (major, minor) != (2, 1):
            raise ValueError(f"{path}: unsupported DBPF {major}.{minor}")
        count = struct.unpack_from("<I", hdr, 36)[0]
        # Index position: int32 at offset 64, falling back to the legacy field at 40 (as s4pi does).
        # Bytes 68+ are unrelated header fields and must not be read as part of it.
        index_pos = struct.unpack_from("<I", hdr, 64)[0] or struct.unpack_from("<I", hdr, 40)[0]
        self.entries: list[Entry] = list(self._read_index(index_pos, count))

    def _read_index(self, pos: int, count: int) -> Iterator[Entry]:
        f = self._f
        f.seek(pos)
        flags = struct.unpack("<I", f.read(4))[0]
        const = {}
        for bit, name in ((1, "type"), (2, "group"), (4, "insthi")):
            if flags & bit:
                const[name] = struct.unpack("<I", f.read(4))[0]
        for _ in range(count):
            def field(name):
                return const[name] if name in const else struct.unpack("<I", f.read(4))[0]
            t, g, ih = field("type"), field("group"), field("insthi")
            # Every entry carries the compression word (s4pi reads 8 words per entry
            # when no fields are constant), whatever the high bit of the size field says.
            il, off, fsize, msize, comp, _committed = struct.unpack("<IIIIHH", f.read(20))
            yield Entry(t, g, (ih << 32) | il, off, fsize & 0x7FFFFFFF, msize, comp)

    def read(self, e: Entry) -> bytes:
        self._f.seek(e.offset)
        raw = self._f.read(e.file_size)
        if e.compression == 0x0000:
            return raw
        if e.compression == 0x5A42:
            return zlib.decompress(raw)
        if e.compression == 0xFFFF:
            return _refpack_decompress(raw)
        raise NotImplementedError(f"compression 0x{e.compression:04X} for {e.tgi}")

    def find(self, type_: int | None = None, instance: int | None = None) -> list[Entry]:
        return [e for e in self.entries
                if (type_ is None or e.type == type_) and (instance is None or e.instance == instance)]

    def close(self) -> None:
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


if __name__ == "__main__":
    import sys
    from collections import Counter
    with Package(sys.argv[1]) as p:
        print(f"{len(p.entries)} resources")
        for t, n in Counter(e.type for e in p.entries).most_common():
            print(f"  type 0x{t:08X}: {n}")
