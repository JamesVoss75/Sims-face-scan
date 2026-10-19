"""Parser tests on synthetic resources built from the documented layouts.

These check the parsers against our understanding of the formats; E1 checks
that understanding against real game files (parse-failure and cross-reference
rates in the inventory report).
"""
import struct

import pytest

from ts4face.resources import (BoneDelta, CASPreset, HotSpotControl, Sculpt, SimModifier,
                               age_gender, decode_flags, VIEW_FLAGS)


def itg(inst, typ=0, grp=0):
    return struct.pack("<QII", inst, typ, grp)


def context_header(public=(0x1111,), delay=()):
    out = struct.pack("<IIIII", 3, len(public), 0, len(delay), 1)
    out += b"".join(itg(p, 0xC5F6763E) for p in public)
    out += b"".join(itg(d, 0x067CAA11) for d in delay)
    return out + struct.pack("<II", 44, 72)


def test_smod_v144_with_bgeo_and_bones():
    body = struct.pack("<IIIII", 144, 0x2010 | 0x1000, 1, 0, 0x30000001)
    body += itg(0xB0, 0x0355E0A6) + itg(0x5A, 0xDB43E069) + itg(0x4E, 0xDB43E069)
    body += struct.pack("<I", 2) + struct.pack("<If", 0xABCD, 0.5) + struct.pack("<If", 0x1234, 1.0)
    s = SimModifier.parse(context_header(delay=(0xBE0,)) + body)
    assert (s.version, s.region, s.link_tag) == (144, 1, 0x30000001)
    assert s.bone_pose.instance == 0xB0 and s.dmap_shape.instance == 0x5A and s.dmap_normal.instance == 0x4E
    assert s.bgeo.instance == 0xBE0
    assert s.bone_entries == [(0xABCD, 0.5), (0x1234, 1.0)]
    assert age_gender(s.age_gender) == {"ages": ["YOUNGADULT"], "genders": ["MALE", "FEMALE"]}


def test_smod_pre144_has_no_subregion():
    body = struct.pack("<IIII", 143, 0x10, 0, 0) + itg(0) + itg(7) + itg(0) + struct.pack("<I", 0)
    s = SimModifier.parse(context_header() + body)
    assert s.sub_region == 0 and s.dmap_shape.instance == 7 and s.bgeo is None and not s.bone_pose


def test_sculpt():
    body = struct.pack("<IIIII", 0xB0, 0x10, 2, 0, 0) + itg(1) + itg(2) + itg(3) + b"\x00"
    body += itg(4) + itg(5) + itg(6) + struct.pack("<I", 0)
    sc = Sculpt.parse(context_header() + body)
    assert sc.region == 2 and sc.dmap_shape.instance == 4 and sc.bone_delta.instance == 6


def test_bone_delta():
    body = struct.pack("<II", 1, 1) + struct.pack("<I10f", 0xFACE, 0.1, 0.2, 0.3, 1, 1, 1, 0, 0, 0, 1)
    b = BoneDelta.parse(context_header() + body)
    a = b.adjustments[0]
    assert a.bone_hash == 0xFACE and a.offset == pytest.approx((0.1, 0.2, 0.3)) and a.rotation[3] == 1


def test_hotspot_control_v15():
    data = struct.pack("<III", 0x0F, 0x10 | 0x3000, 1) + struct.pack("<I", 0)
    data += struct.pack("<BBB", 1, 7, 2) + struct.pack("<II", 1, 0) + struct.pack("<BQI", 0, 0x99, 0)
    data += struct.pack("<B", 2)
    data += struct.pack("<BBff", 0x1, 0, 0.0, 1.0) + struct.pack("<4Q", 1, 2, 3, 4)
    data += struct.pack("<BBff", 0x8 | 0x10, 1, 0.0, 1.0) + struct.pack("<4Q", 5, 6, 0, 0)
    h = HotSpotControl.parse(data)
    assert (h.level, h.region, h.texture) == (1, 1, 0x99)
    assert h.sliders[0].modifiers == (1, 2, 3, 4)
    assert decode_flags(h.sliders[1].views, VIEW_FLAGS) == ["profile_right", "profile_left"] and h.sliders[1].flip


@pytest.mark.parametrize("version", [8, 9, 10, 11, 12])
def test_cas_preset_versions(version):
    d = struct.pack("<II", version, 0x10 | 0x2000)
    if version >= 11:
        d += struct.pack("<I", 0x2000)
    if version >= 8:
        d += struct.pack("<I", 1)
    d += struct.pack("<I", 1)                      # region NOSE
    if version >= 9:
        d += struct.pack("<I", 0)
    d += struct.pack("<IfII", 0, 3.0, 0xAA, 0xBB)
    d += struct.pack("<I", 1) + struct.pack("<Q", 0x5C) + (struct.pack("<I", 1) if version < 9 else b"")
    d += struct.pack("<I", 2)
    for inst, w in ((0x10, 0.25), (0x20, 0.75)):
        d += struct.pack("<Qf", inst, w) + (struct.pack("<I", 1) if version < 9 else b"")
    d += b"\x00"                                   # no physique
    if version >= 12:
        d += b"\x00"                               # no part set
    d += struct.pack("<f", 0.5) + struct.pack("<I", 1)
    d += struct.pack("<HI", 3, 77) if version >= 10 else struct.pack("<HH", 3, 77)
    p = CASPreset.parse(d)
    assert p.region == 1 and p.sculpts == [0x5C] and p.modifiers == [(0x10, 0.25), (0x20, 0.75)]
    assert p.display_index == 3.0 and p.tags == [(3, 77)] and p.physique is None


def test_truncated_raises():
    with pytest.raises(ValueError):
        BoneDelta.parse(context_header() + struct.pack("<II", 1, 5))
