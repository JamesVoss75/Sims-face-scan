"""Schema-less protobuf wire-format helpers.

Enough to walk EA's save/blob messages by field number without generated
classes or a protobuf runtime dependency.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Iterator

VARINT, FIXED64, LEN, FIXED32 = 0, 1, 2, 5


def read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        if pos >= len(buf):
            raise ValueError("truncated varint")
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, pos
        shift += 7
        if shift >= 70:
            raise ValueError("varint too long")


def write_varint(value: int) -> bytes:
    if value < 0:
        value &= 0xFFFFFFFFFFFFFFFF
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def tag(num: int, wire: int) -> bytes:
    return write_varint(num << 3 | wire)


@dataclass(frozen=True)
class Field:
    num: int
    wire: int
    payload: bytes  # varint: the encoded varint bytes; LEN: the content without length prefix
    raw: bytes      # the complete field including tag, for verbatim preservation

    @property
    def int(self) -> int:
        if self.wire == VARINT:
            return read_varint(self.payload, 0)[0]
        if self.wire == FIXED64:
            return struct.unpack("<Q", self.payload)[0]
        if self.wire == FIXED32:
            return struct.unpack("<I", self.payload)[0]
        raise ValueError(f"field {self.num} is not numeric")

    @property
    def float32(self) -> float:
        return struct.unpack("<f", self.payload)[0]

    @property
    def text(self) -> str:
        return self.payload.decode("utf-8", errors="replace")


def iter_fields(buf: bytes) -> Iterator[Field]:
    pos = 0
    n = len(buf)
    while pos < n:
        start = pos
        key, pos = read_varint(buf, pos)
        num, wire = key >> 3, key & 7
        if num == 0:
            raise ValueError("field number 0")
        if wire == VARINT:
            _, end = read_varint(buf, pos)
            payload = buf[pos:end]
        elif wire == FIXED64:
            end = pos + 8
            payload = buf[pos:end]
        elif wire == FIXED32:
            end = pos + 4
            payload = buf[pos:end]
        elif wire == LEN:
            length, pos = read_varint(buf, pos)
            end = pos + length
            payload = buf[pos:end]
        else:
            raise ValueError(f"unsupported wire type {wire} at offset {start}")
        if end > n:
            raise ValueError(f"truncated field {num} at offset {start}")
        yield Field(num, wire, bytes(payload), bytes(buf[start:end]))
        pos = end


def fields_by_num(buf: bytes) -> dict[int, list[Field]]:
    out: dict[int, list[Field]] = {}
    for f in iter_fields(buf):
        out.setdefault(f.num, []).append(f)
    return out


def unpack_varints(payload: bytes) -> list[int]:
    vals, pos = [], 0
    while pos < len(payload):
        v, pos = read_varint(payload, pos)
        vals.append(v)
    return vals
