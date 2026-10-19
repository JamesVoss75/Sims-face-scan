"""Codec for EA's BlobSimFacialCustomizationData protobuf.

This is the blob stored in SimData.facial_attr (save files, field 18) and
exposed to script mods as ``sim_info.facial_attributes``.  Schema, from the
protobuf classes shipped in TS4 SimRipper (src/Proto/PersistenceBlobs.cs):

    message BlobSimFacialCustomizationData {
        repeated uint64   sculpts             = 1;
        repeated Modifier face_modifiers      = 2;
        repeated Modifier body_modifiers      = 3;
        repeated Modifier aged_face_modifiers = 4;
        repeated Modifier aged_body_modifiers = 5;
        message Modifier { optional uint64 key = 1; optional float amount = 2; }
    }

``key`` is a SimModifier instance ID (see fnv.fnv64); ``sculpts`` are Sculpt
instance IDs.  Pure Python so the desktop app needs no protobuf runtime; the
in-game mod uses EA's own ``protocolbuffers.PersistenceBlobs_pb2`` instead.
Unknown fields are preserved verbatim so a round trip never drops data that a
future game version adds.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

MODIFIER_FIELDS = {
    2: "face_modifiers",
    3: "body_modifiers",
    4: "aged_face_modifiers",
    5: "aged_body_modifiers",
}


def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
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


def _write_varint(value: int) -> bytes:
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


def _skip(buf: bytes, pos: int, wire: int) -> int:
    if wire == 0:
        return _read_varint(buf, pos)[1]
    if wire == 1:
        return pos + 8
    if wire == 2:
        n, pos = _read_varint(buf, pos)
        return pos + n
    if wire == 5:
        return pos + 4
    raise ValueError(f"unsupported wire type {wire}")


def _iter_fields(buf: bytes):
    pos = 0
    while pos < len(buf):
        start = pos
        tag, pos = _read_varint(buf, pos)
        num, wire = tag >> 3, tag & 7
        end = _skip(buf, pos, wire)
        if end > len(buf):
            raise ValueError("truncated field")
        yield num, wire, buf[pos:end], buf[start:end]
        pos = end


@dataclass
class Modifier:
    key: int
    amount: float
    unknown: bytes = b""

    @classmethod
    def decode(cls, buf: bytes) -> "Modifier":
        key, amount, unknown = 0, 0.0, bytearray()
        for num, wire, payload, raw in _iter_fields(buf):
            if num == 1 and wire == 0:
                key = _read_varint(payload, 0)[0]
            elif num == 2 and wire == 5:
                amount = struct.unpack("<f", payload)[0]
            else:
                unknown += raw
        return cls(key, amount, bytes(unknown))

    def encode(self) -> bytes:
        return (_write_varint(1 << 3 | 0) + _write_varint(self.key)
                + _write_varint(2 << 3 | 5) + struct.pack("<f", self.amount)
                + self.unknown)


@dataclass
class FacialData:
    sculpts: list[int] = field(default_factory=list)
    face_modifiers: list[Modifier] = field(default_factory=list)
    body_modifiers: list[Modifier] = field(default_factory=list)
    aged_face_modifiers: list[Modifier] = field(default_factory=list)
    aged_body_modifiers: list[Modifier] = field(default_factory=list)
    unknown: bytes = b""

    @classmethod
    def decode(cls, buf: bytes) -> "FacialData":
        fd = cls()
        unknown = bytearray()
        for num, wire, payload, raw in _iter_fields(buf):
            if num == 1 and wire == 0:
                fd.sculpts.append(_read_varint(payload, 0)[0])
            elif num == 1 and wire == 2:  # packed encoding, accepted for robustness
                n, pos = _read_varint(payload, 0)
                body = payload[pos:pos + n]
                p = 0
                while p < len(body):
                    v, p = _read_varint(body, p)
                    fd.sculpts.append(v)
            elif num in MODIFIER_FIELDS and wire == 2:
                n, pos = _read_varint(payload, 0)
                getattr(fd, MODIFIER_FIELDS[num]).append(Modifier.decode(payload[pos:pos + n]))
            else:
                unknown += raw
        fd.unknown = bytes(unknown)
        return fd

    def encode(self) -> bytes:
        out = bytearray()
        for s in self.sculpts:
            out += _write_varint(1 << 3 | 0) + _write_varint(s)
        for num, name in MODIFIER_FIELDS.items():
            for m in getattr(self, name):
                body = m.encode()
                out += _write_varint(num << 3 | 2) + _write_varint(len(body)) + body
        out += self.unknown
        return bytes(out)

    def face_dict(self) -> dict[int, float]:
        return {m.key: m.amount for m in self.face_modifiers}

    def set_face(self, key: int, amount: float) -> None:
        """Set a face modifier; amount 0 removes it, matching how CAS stores defaults."""
        self.face_modifiers = [m for m in self.face_modifiers if m.key != key]
        if amount:
            self.face_modifiers.append(Modifier(key, float(amount)))

    def to_json(self) -> dict:
        def mods(ms):
            return [{"key": f"0x{m.key:016X}", "amount": m.amount} for m in ms]
        return {
            "sculpts": [f"0x{s:016X}" for s in self.sculpts],
            **{name: mods(getattr(self, name)) for name in MODIFIER_FIELDS.values()},
        }

    @classmethod
    def from_json(cls, d: dict) -> "FacialData":
        def mods(ms):
            return [Modifier(int(m["key"], 0), float(m["amount"])) for m in ms]
        return cls(
            sculpts=[int(s, 0) for s in d.get("sculpts", [])],
            **{name: mods(d.get(name, [])) for name in MODIFIER_FIELDS.values()},
        )
