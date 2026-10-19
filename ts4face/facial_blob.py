"""Codec for EA's BlobSimFacialCustomizationData protobuf.

This is the blob stored in SimData.facial_attr (save files, field 18), in
GeneticData.sculpts_and_mods_attr, and exposed to script mods as
``sim_info.facial_attributes``.  Schema (field numbers as published in the
protobuf classes of TS4 SimRipper, src/Proto/PersistenceBlobs.cs):

    message BlobSimFacialCustomizationData {
        repeated uint64   sculpts             = 1;
        repeated Modifier face_modifiers      = 2;
        repeated Modifier body_modifiers      = 3;
        repeated Modifier aged_face_modifiers = 4;
        repeated Modifier aged_body_modifiers = 5;
        message Modifier { optional uint64 key = 1; optional float amount = 2; }
    }

``key`` is a SimModifier instance ID (see fnv.fnv64); ``sculpts`` are Sculpt
instance IDs.  Pure Python so the desktop tools need no protobuf runtime; the
in-game mod uses EA's own ``protocolbuffers.PersistenceBlobs_pb2`` instead.

Preservation guarantees (tested against the protobuf runtime):
  * every known field, including the aged_* lists, list order and duplicates;
  * presence of optional ``key``/``amount`` (an absent field stays absent);
  * packed or unpacked sculpt encoding;
  * unknown fields, at both message and Modifier level, byte for byte.
Re-encoding is byte-identical for canonically serialized input (what the
game's protobuf library produces).  Non-canonical field order is normalised to
field-number order with unknown fields last, which protobuf treats as equal.
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field

from .protowire import FIXED32, LEN, VARINT, iter_fields, tag, unpack_varints, write_varint

MODIFIER_FIELDS = {
    2: "face_modifiers",
    3: "body_modifiers",
    4: "aged_face_modifiers",
    5: "aged_body_modifiers",
}


@dataclass
class Modifier:
    key: int | None
    amount: float | None
    unknown: bytes = b""

    @classmethod
    def decode(cls, buf: bytes) -> "Modifier":
        key = amount = None
        unknown = bytearray()
        for f in iter_fields(buf):
            if f.num == 1 and f.wire == VARINT:
                key = f.int
            elif f.num == 2 and f.wire == FIXED32:
                amount = f.float32
            else:
                unknown += f.raw
        return cls(key, amount, bytes(unknown))

    def encode(self) -> bytes:
        out = bytearray()
        if self.key is not None:
            out += tag(1, VARINT) + write_varint(self.key)
        if self.amount is not None:
            out += tag(2, FIXED32) + struct.pack("<f", self.amount)
        return bytes(out + self.unknown)


@dataclass
class FacialData:
    sculpts: list[int] = field(default_factory=list)
    face_modifiers: list[Modifier] = field(default_factory=list)
    body_modifiers: list[Modifier] = field(default_factory=list)
    aged_face_modifiers: list[Modifier] = field(default_factory=list)
    aged_body_modifiers: list[Modifier] = field(default_factory=list)
    unknown: bytes = b""
    sculpts_packed: bool = False

    @classmethod
    def decode(cls, buf: bytes) -> "FacialData":
        fd = cls()
        unknown = bytearray()
        for f in iter_fields(buf):
            if f.num == 1 and f.wire == VARINT:
                fd.sculpts.append(f.int)
            elif f.num == 1 and f.wire == LEN:
                fd.sculpts.extend(unpack_varints(f.payload))
                fd.sculpts_packed = True
            elif f.num in MODIFIER_FIELDS and f.wire == LEN:
                getattr(fd, MODIFIER_FIELDS[f.num]).append(Modifier.decode(f.payload))
            else:
                unknown += f.raw
        fd.unknown = bytes(unknown)
        return fd

    def encode(self) -> bytes:
        out = bytearray()
        if self.sculpts_packed and self.sculpts:
            body = b"".join(write_varint(s) for s in self.sculpts)
            out += tag(1, LEN) + write_varint(len(body)) + body
        else:
            for s in self.sculpts:
                out += tag(1, VARINT) + write_varint(s)
        for num, name in MODIFIER_FIELDS.items():
            for m in getattr(self, name):
                body = m.encode()
                out += tag(num, LEN) + write_varint(len(body)) + body
        out += self.unknown
        return bytes(out)

    def face_dict(self) -> dict[int, float]:
        return {m.key: m.amount for m in self.face_modifiers if m.key is not None}

    def set_face(self, key: int, amount: float) -> None:
        """Set a face modifier; amount 0 removes it, matching how CAS stores defaults (LIKELY)."""
        self.face_modifiers = [m for m in self.face_modifiers if m.key != key]
        if amount:
            self.face_modifiers.append(Modifier(key, float(amount)))

    def to_json(self) -> dict:
        def mods(ms):
            out = []
            for m in ms:
                d = {"key": None if m.key is None else f"0x{m.key:016X}", "amount": m.amount}
                if m.unknown:
                    d["unknown_hex"] = m.unknown.hex()
                out.append(d)
            return out
        d = {
            "sculpts": [f"0x{s:016X}" for s in self.sculpts],
            **{name: mods(getattr(self, name)) for name in MODIFIER_FIELDS.values()},
        }
        if self.unknown:
            d["unknown_hex"] = self.unknown.hex()
        if self.sculpts_packed:
            d["sculpts_packed"] = True
        return d

    @classmethod
    def from_json(cls, d: dict) -> "FacialData":
        def mods(ms):
            return [Modifier(None if m.get("key") is None else int(m["key"], 0),
                             None if m.get("amount") is None else float(m["amount"]),
                             bytes.fromhex(m.get("unknown_hex", "")))
                    for m in ms]
        return cls(
            sculpts=[int(s, 0) for s in d.get("sculpts", [])],
            **{name: mods(d.get(name, [])) for name in MODIFIER_FIELDS.values()},
            unknown=bytes.fromhex(d.get("unknown_hex", "")),
            sculpts_packed=bool(d.get("sculpts_packed", False)),
        )


def _f32(x: float) -> float:
    return struct.unpack("<f", struct.pack("<f", x))[0]


def diff(expected: FacialData, actual: FacialData, tol: float = 1e-6) -> list[str]:
    """Human-readable differences; empty list means equivalent.

    Modifier lists are compared as key -> amount maps (order is reported
    separately because the game may legitimately reorder entries).
    Amounts are compared after rounding both to float32.
    """
    problems: list[str] = []
    if sorted(expected.sculpts) != sorted(actual.sculpts):
        missing = sorted(set(expected.sculpts) - set(actual.sculpts))
        extra = sorted(set(actual.sculpts) - set(expected.sculpts))
        problems.append("sculpts differ: missing " + ", ".join(f"0x{s:016X}" for s in missing)
                        + "; unexpected " + ", ".join(f"0x{s:016X}" for s in extra))
    elif expected.sculpts != actual.sculpts:
        problems.append("sculpts reordered (same set)")
    for name in MODIFIER_FIELDS.values():
        exp = {m.key: m.amount for m in getattr(expected, name)}
        act = {m.key: m.amount for m in getattr(actual, name)}
        for k in sorted(set(exp) | set(act), key=lambda k: (k is None, k or 0)):
            ks = "None" if k is None else f"0x{k:016X}"
            if k not in act:
                problems.append(f"{name}: {ks} missing (expected {exp[k]})")
            elif k not in exp:
                problems.append(f"{name}: {ks} unexpected (= {act[k]})")
            else:
                a, b = exp[k], act[k]
                if (a is None) != (b is None):
                    problems.append(f"{name}: {ks} amount presence differs ({a} vs {b})")
                elif a is not None and not (math.isclose(_f32(a), _f32(b), abs_tol=tol)
                                            or (math.isnan(a) and math.isnan(b))):
                    problems.append(f"{name}: {ks} amount {a!r} -> {b!r}")
        if len(getattr(expected, name)) != len(getattr(actual, name)) and len(exp) == len(act):
            problems.append(f"{name}: duplicate-key count differs")
    if expected.unknown != actual.unknown:
        problems.append(f"unknown top-level fields differ ({len(expected.unknown)} vs {len(actual.unknown)} bytes)")
    return problems
