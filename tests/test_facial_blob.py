import pytest
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory

from ts4face.facial_blob import FacialData, Modifier


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
    return message_factory.GetMessageClass(pool.FindMessageTypeByName("EA.Sims4.Persistence.BlobSimFacialCustomizationData"))


Blob = _reference_message_class()


def _sample():
    return FacialData(
        sculpts=[0x8000000000001234, 42],
        face_modifiers=[Modifier(0x8088D1E4B2013F98, 0.5), Modifier(0x814F11012B65B21C, 1.0)],
        body_modifiers=[Modifier(0x814A1078EB0A9302, 0.25)],
    )


def test_encoding_matches_protobuf_runtime():
    ours = _sample().encode()
    ref = Blob()
    ref.ParseFromString(ours)
    assert list(ref.sculpts) == [0x8000000000001234, 42]
    assert [(m.key, m.amount) for m in ref.face_modifiers] == [(0x8088D1E4B2013F98, 0.5), (0x814F11012B65B21C, 1.0)]
    assert ref.SerializeToString() == ours


def test_decodes_protobuf_runtime_output():
    ref = Blob()
    ref.sculpts.extend([7, 0xFFFFFFFFFFFFFFFF])
    m = ref.aged_face_modifiers.add()
    m.key, m.amount = 99, -0.75
    fd = FacialData.decode(ref.SerializeToString())
    assert fd.sculpts == [7, 0xFFFFFFFFFFFFFFFF]
    assert fd.aged_face_modifiers[0].key == 99
    assert fd.aged_face_modifiers[0].amount == pytest.approx(-0.75)
    assert fd.encode() == ref.SerializeToString()


def test_unknown_fields_survive_round_trip():
    raw = _sample().encode() + bytes([0x50, 0x05])  # field 10, varint 5
    fd = FacialData.decode(raw)
    assert fd.encode() == raw


def test_json_round_trip_and_set_face():
    fd = _sample()
    fd.set_face(0x8088D1E4B2013F98, 0.0)
    fd.set_face(123, 0.3)
    again = FacialData.from_json(fd.to_json())
    assert again.face_dict() == pytest.approx({0x814F11012B65B21C: 1.0, 123: 0.3})
    assert again.sculpts == fd.sculpts


def test_truncated_input_raises():
    with pytest.raises(ValueError):
        FacialData.decode(_sample().encode()[:-3])
