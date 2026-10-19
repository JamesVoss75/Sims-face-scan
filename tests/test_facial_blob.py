import math
import random
import struct

import pytest
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

from ts4face.facial_blob import FacialData, Modifier, diff
from ts4face.protowire import tag, write_varint


def _reference_message_class():
    """Build EA's schema (as published in TS4 SimRipper) with the real protobuf runtime."""
    fdp = descriptor_pb2.FileDescriptorProto(name="blob_test.proto", package="EA.Sims4.Persistence", syntax="proto2")
    msg = fdp.message_type.add(name="BlobSimFacialCustomizationData")
    mod = msg.nested_type.add(name="Modifier")
    F = descriptor_pb2.FieldDescriptorProto
    mod.field.add(name="key", number=1, type=F.TYPE_UINT64, label=F.LABEL_OPTIONAL)
    mod.field.add(name="amount", number=2, type=F.TYPE_FLOAT, label=F.LABEL_OPTIONAL)
    msg.field.add(name="sculpts", number=1, type=F.TYPE_UINT64, label=F.LABEL_REPEATED)
    for i, n in enumerate(["face_modifiers", "body_modifiers", "aged_face_modifiers", "aged_body_modifiers"], start=2):
        msg.field.add(name=n, number=i, type=F.TYPE_MESSAGE, label=F.LABEL_REPEATED,
                      type_name=".EA.Sims4.Persistence.BlobSimFacialCustomizationData.Modifier")
    pool = descriptor_pool.DescriptorPool()
    pool.Add(fdp)
    desc = pool.FindMessageTypeByName("EA.Sims4.Persistence.BlobSimFacialCustomizationData")
    if hasattr(message_factory, "GetMessageClass"):
        return message_factory.GetMessageClass(desc)
    return message_factory.MessageFactory(pool).GetPrototype(desc)  # protobuf 3.x (Python 3.7 runs)


Blob = _reference_message_class()
LISTS = ["face_modifiers", "body_modifiers", "aged_face_modifiers", "aged_body_modifiers"]


def _sample():
    return FacialData(
        sculpts=[0x8000000000001234, 42],
        face_modifiers=[Modifier(0x8088D1E4B2013F98, 0.5), Modifier(0x814F11012B65B21C, 1.0)],
        body_modifiers=[Modifier(0x814A1078EB0A9302, 0.25)],
        aged_face_modifiers=[Modifier(0x8D3B32D6AFB7EDFF, 0.125)],
        aged_body_modifiers=[Modifier(7, 0.75)],
    )


def test_encoding_matches_protobuf_runtime():
    ours = _sample().encode()
    ref = Blob()
    ref.ParseFromString(ours)
    assert list(ref.sculpts) == [0x8000000000001234, 42]
    assert [(m.key, m.amount) for m in ref.face_modifiers] == [(0x8088D1E4B2013F98, 0.5), (0x814F11012B65B21C, 1.0)]
    assert [(m.key, m.amount) for m in ref.aged_face_modifiers] == [(0x8D3B32D6AFB7EDFF, 0.125)]
    assert [(m.key, m.amount) for m in ref.aged_body_modifiers] == [(7, 0.75)]
    assert ref.SerializeToString() == ours


def _random_reference(rng):
    ref = Blob()
    ref.sculpts.extend(rng.getrandbits(64) for _ in range(rng.randint(0, 8)))
    for name in LISTS:
        for _ in range(rng.randint(0, 6)):
            m = getattr(ref, name).add()
            if rng.random() < 0.9:
                m.key = rng.getrandbits(64)
            if rng.random() < 0.9:
                m.amount = struct.unpack("<f", struct.pack("<f", rng.uniform(-2, 2)))[0]
    return ref


def _unknown_field(rng):
    num = rng.randint(6, 300)
    kind = rng.choice(["varint", "len", "fixed32", "fixed64"])
    if kind == "varint":
        return tag(num, 0) + write_varint(rng.getrandbits(40))
    if kind == "len":
        body = bytes(rng.getrandbits(8) for _ in range(rng.randint(0, 12)))
        return tag(num, 2) + write_varint(len(body)) + body
    if kind == "fixed32":
        return tag(num, 5) + struct.pack("<I", rng.getrandbits(32))
    return tag(num, 1) + struct.pack("<Q", rng.getrandbits(64))


@pytest.mark.parametrize("seed", range(200))
def test_fuzz_round_trip_against_runtime(seed):
    rng = random.Random(seed)
    ref = _random_reference(rng)
    raw = ref.SerializeToString()
    # Append unknown fields the way a newer game version might.
    raw += b"".join(_unknown_field(rng) for _ in range(rng.randint(0, 3)))
    ref2 = Blob()
    ref2.ParseFromString(raw)
    canonical = ref2.SerializeToString()  # runtime keeps unknown fields at the end

    fd = FacialData.decode(raw)
    assert fd.encode() == canonical
    assert list(ref2.sculpts) == fd.sculpts
    for name in LISTS:
        ours = getattr(fd, name)
        theirs = getattr(ref2, name)
        assert len(ours) == len(theirs)
        for a, b in zip(ours, theirs):
            assert a.key == (b.key if b.HasField("key") else None)
            assert (a.amount is None) == (not b.HasField("amount"))
            if a.amount is not None:
                assert a.amount == b.amount or (math.isnan(a.amount) and math.isnan(b.amount))
    assert diff(fd, FacialData.decode(canonical)) == []


def test_presence_preserved():
    ref = Blob()
    ref.face_modifiers.add().key = 5          # no amount
    ref.face_modifiers.add().amount = 0.5     # no key
    raw = ref.SerializeToString()
    fd = FacialData.decode(raw)
    assert fd.face_modifiers[0].amount is None
    assert fd.face_modifiers[1].key is None
    assert fd.encode() == raw


def test_packed_sculpts_preserved_and_understood():
    body = write_varint(11) + write_varint(0xFFFFFFFFFFFFFFFF)
    raw = tag(1, 2) + write_varint(len(body)) + body
    fd = FacialData.decode(raw)
    assert fd.sculpts == [11, 0xFFFFFFFFFFFFFFFF]
    assert fd.encode() == raw
    ref = Blob()
    ref.ParseFromString(raw)  # the runtime accepts packed input for repeated scalars
    assert list(ref.sculpts) == fd.sculpts


def test_unknown_fields_inside_modifier_survive():
    inner = tag(1, 0) + write_varint(9) + tag(2, 5) + struct.pack("<f", 0.25) + tag(3, 0) + write_varint(1)
    raw = tag(2, 2) + write_varint(len(inner)) + inner
    fd = FacialData.decode(raw)
    assert fd.face_modifiers[0].unknown == tag(3, 0) + write_varint(1)
    assert fd.encode() == raw
    assert FacialData.from_json(fd.to_json()).encode() == raw


def test_json_round_trip_and_set_face():
    fd = _sample()
    fd.set_face(0x8088D1E4B2013F98, 0.0)
    fd.set_face(123, 0.3)
    again = FacialData.from_json(fd.to_json())
    assert again.face_dict() == pytest.approx({0x814F11012B65B21C: 1.0, 123: 0.3})
    assert again.encode() == fd.encode()


def test_diff_reports_changes():
    a = _sample()
    b = FacialData.decode(a.encode())
    assert diff(a, b) == []
    b.face_modifiers[0].amount = 0.4
    b.aged_face_modifiers.clear()
    b.sculpts.reverse()
    problems = diff(a, b)
    assert any("0x8088D1E4B2013F98 amount" in p for p in problems)
    assert any("aged_face_modifiers" in p and "missing" in p for p in problems)
    assert "sculpts reordered (same set)" in problems


def test_diff_tolerates_float32_rounding():
    a = FacialData(face_modifiers=[Modifier(1, 0.1)])
    b = FacialData.decode(a.encode())  # 0.1 -> nearest float32
    assert b.face_modifiers[0].amount != 0.1
    assert diff(a, b) == []


def test_truncated_input_raises():
    with pytest.raises(ValueError):
        FacialData.decode(_sample().encode()[:-3])
