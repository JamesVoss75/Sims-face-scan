"""Shared test helpers: synthetic DBPF packages and save files."""
import struct
import zlib

from ts4face.protowire import tag, write_varint


def write_package(path, resources):
    """Write a minimal DBPF 2.1 file. resources: list of (type, group, instance, bytes, compress)."""
    body = bytearray()
    index = bytearray(struct.pack("<I", 0))  # no constant fields
    offset = 96
    for t, g, inst, data, compress in resources:
        stored = zlib.compress(data) if compress else data
        index += struct.pack("<IIIIII", t, g, inst >> 32, inst & 0xFFFFFFFF, offset + len(body), len(stored) | 0x80000000)
        index += struct.pack("<IHH", len(data), 0x5A42 if compress else 0, 1)
        body += stored
    path.parent.mkdir(parents=True, exist_ok=True)
    hdr = bytearray(96)
    hdr[:4] = b"DBPF"
    struct.pack_into("<II", hdr, 4, 2, 1)
    struct.pack_into("<I", hdr, 36, len(resources))
    struct.pack_into("<I", hdr, 44, len(index))
    struct.pack_into("<Q", hdr, 64, 96 + len(body))
    path.write_bytes(bytes(hdr) + bytes(body) + bytes(index))


def _len_field(num, payload):
    return tag(num, 2) + write_varint(len(payload)) + payload


def sim_data(sim_id, first, last, facial, age=0x10, gender=0x2000, genetic=None):
    """SimData message with the fields ts4face.savegame reads, plus an unrelated field."""
    msg = tag(1, 0) + write_varint(sim_id) + _len_field(5, first.encode()) + _len_field(6, last.encode())
    msg += tag(7, 0) + write_varint(gender) + tag(8, 0) + write_varint(age)
    msg += _len_field(18, facial) + tag(60, 0) + write_varint(1)
    msg += _len_field(12, b"0.5,0,0,0,0,0,0,0")  # physique, ignored
    if genetic is not None:
        msg += _len_field(28, _len_field(1, genetic))
    return msg


def write_save(path, sims):
    """A .save-like package: one zlib-compressed SaveGameData resource (type 0x0D)."""
    data = _len_field(2, _len_field(9, b"Test slot"))
    for s in sims:
        data += _len_field(6, s)
    write_package(path, [(0x0000000D, 0, 0x1, data, True), (0x12345678, 0, 0x2, b"other", False)])
