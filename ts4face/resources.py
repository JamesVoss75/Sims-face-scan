"""Parsers for the Sims 4 CAS resources that define facial customization.

Read-only.  Layouts follow the community format knowledge embodied in TS4
MorphMaker / TS4 SimRipper (GPL-3.0); this is an independent Python
implementation, not a translation of their code (see THIRD_PARTY_NOTICES.md).
None of these parsers has yet been run against current game files: E1 does
that and reports per-type parse failures, which is how format drift shows up.

    SimModifier    0xC5F6763E  one slider direction -> BGEO/DMAP/BOND links
    Sculpt         0x9D1AB874  region-level shape bundle -> BGEO/DMAP/BOND links
    BoneDelta      0x0355E0A6  per-bone offset/scale/rotation
    HotSpotControl 0x8B18FF6E  CAS drag hotspot -> per-view slider -> 4 SMODs
    CASPreset      0xEAA32ADD  preset = sculpts + (modifier, weight) pairs
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field

SMOD_TYPE, SCULPT_TYPE, BOND_TYPE = 0xC5F6763E, 0x9D1AB874, 0x0355E0A6
HOTC_TYPE, CPRE_TYPE = 0x8B18FF6E, 0xEAA32ADD
BGEO_TYPE, DMAP_TYPE, GEOM_TYPE = 0x067CAA11, 0xDB43E069, 0x015A1849

REGIONS = {0: "EYES", 1: "NOSE", 2: "MOUTH", 3: "CHEEKS", 4: "CHIN", 5: "JAW", 6: "FOREHEAD",
           8: "BROWS", 9: "EARS", 10: "HEAD", 12: "FULLFACE", 14: "CHEST", 15: "UPPERCHEST",
           16: "NECK", 17: "SHOULDERS", 18: "UPPERARM", 19: "LOWERARM", 20: "HANDS", 21: "WAIST",
           22: "HIPS", 23: "BELLY", 24: "BUTT", 25: "THIGHS", 26: "LOWERLEG", 27: "FEET",
           28: "BODY", 29: "UPPERBODY", 30: "LOWERBODY"}
FACE_REGION_IDS = {0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 12}
AGE_FLAGS = {0x1: "BABY", 0x2: "TODDLER", 0x4: "CHILD", 0x8: "TEEN", 0x10: "YOUNGADULT",
             0x20: "ADULT", 0x40: "ELDER", 0x80: "INFANT"}
GENDER_FLAGS = {0x1000: "MALE", 0x2000: "FEMALE"}
VIEW_FLAGS = {0x1: "front", 0x2: "threequarter_right", 0x4: "threequarter_left",
              0x8: "profile_right", 0x10: "profile_left", 0x20: "back"}
HOTSPOT_LEVELS = {0: "normal", 1: "micro", 2: "toplevel"}


def decode_flags(value: int, table: dict[int, str]) -> list[str]:
    return [name for bit, name in table.items() if value & bit]


def age_gender(value: int) -> dict:
    return {"ages": decode_flags(value, AGE_FLAGS), "genders": decode_flags(value, GENDER_FLAGS)}


class Reader:
    def __init__(self, data: bytes):
        self.data, self.pos = data, 0

    def take(self, fmt: str):
        size = struct.calcsize(fmt)
        if self.pos + size > len(self.data):
            raise ValueError(f"truncated at {self.pos} reading {fmt}")
        vals = struct.unpack_from(fmt, self.data, self.pos)
        self.pos += size
        return vals if len(vals) > 1 else vals[0]

    def u8(self): return self.take("<B")
    def u16(self): return self.take("<H")
    def u32(self): return self.take("<I")
    def u64(self): return self.take("<Q")
    def f32(self): return self.take("<f")

    def itg(self) -> "Key":
        inst, typ, grp = self.take("<QII")
        return Key(typ, grp, inst)

    @property
    def remaining(self) -> int:
        return len(self.data) - self.pos


@dataclass(frozen=True)
class Key:
    type: int
    group: int
    instance: int

    def __bool__(self):
        return self.instance != 0

    def __str__(self):
        return f"{self.type:08X}:{self.group:08X}:{self.instance:016X}"


@dataclass
class ContextHeader:
    """The key-table header shared by SMOD, Sculpt and BOND resources."""
    context_version: int
    public_keys: list[Key]
    external_keys: list[Key]
    delay_load_keys: list[Key]
    object_ranges: list[tuple[int, int]]

    @classmethod
    def read(cls, r: Reader) -> "ContextHeader":
        ver = r.u32()
        n_pub, n_ext, n_delay, n_obj = r.u32(), r.u32(), r.u32(), r.u32()
        if max(n_pub, n_ext, n_delay, n_obj) > 4096:
            raise ValueError("implausible key counts")
        return cls(ver, [r.itg() for _ in range(n_pub)], [r.itg() for _ in range(n_ext)],
                   [r.itg() for _ in range(n_delay)], [(r.u32(), r.u32()) for _ in range(n_obj)])


@dataclass
class SimModifier:
    header: ContextHeader
    version: int
    age_gender: int
    region: int
    sub_region: int
    link_tag: int
    bone_pose: Key
    dmap_shape: Key
    dmap_normal: Key
    bone_entries: list[tuple[int, float]]  # (bone hash, multiplier): meaning still unverified

    @property
    def bgeo(self) -> Key | None:
        keys = [k for k in self.header.delay_load_keys if k]
        return keys[0] if keys else None

    @classmethod
    def parse(cls, data: bytes) -> "SimModifier":
        r = Reader(data)
        h = ContextHeader.read(r)
        version, ag, region = r.u32(), r.u32(), r.u32()
        sub = r.u32() if version >= 144 else 0
        link = r.u32()
        bond, shape, normal = r.itg(), r.itg(), r.itg()
        n = r.u32()
        if n > 4096:
            raise ValueError("implausible bone entry count")
        entries = [(r.u32(), r.f32()) for _ in range(n)]
        return cls(h, version, ag, region, sub, link, bond, shape, normal, entries)


@dataclass
class Sculpt:
    header: ContextHeader
    version: int
    age_gender: int
    region: int
    sub_region: int
    link_tag: int
    texture: Key
    specular: Key
    bumpmap: Key
    dmap_shape: Key
    dmap_normal: Key
    bone_delta: Key

    @property
    def bgeo(self) -> Key | None:
        keys = [k for k in self.header.delay_load_keys if k]
        return keys[0] if keys else None

    @classmethod
    def parse(cls, data: bytes) -> "Sculpt":
        r = Reader(data)
        h = ContextHeader.read(r)
        version, ag, region, sub, link = r.u32(), r.u32(), r.u32(), r.u32(), r.u32()
        tex, spec, bump = r.itg(), r.itg(), r.itg()
        r.u8()
        shape, normal, bond = r.itg(), r.itg(), r.itg()
        r.u32()
        return cls(h, version, ag, region, sub, link, tex, spec, bump, shape, normal, bond)


@dataclass
class BoneAdjust:
    bone_hash: int
    offset: tuple[float, float, float]
    scale: tuple[float, float, float]
    rotation: tuple[float, float, float, float]  # quaternion x, y, z, w


@dataclass
class BoneDelta:
    header: ContextHeader
    version: int
    adjustments: list[BoneAdjust]

    @classmethod
    def parse(cls, data: bytes) -> "BoneDelta":
        r = Reader(data)
        h = ContextHeader.read(r)
        version, n = r.u32(), r.u32()
        if n > 4096:
            raise ValueError("implausible bone adjustment count")
        adj = []
        for _ in range(n):
            vals = r.take("<I10f")
            adj.append(BoneAdjust(vals[0], tuple(vals[1:4]), tuple(vals[4:7]), tuple(vals[7:11])))
        return cls(h, version, adj)


@dataclass
class HotSpotSlider:
    views: int
    flip: bool
    unknown: tuple[float, float]
    modifiers: tuple[int, int, int, int]  # SMOD instance per drag direction (order to be confirmed by E2)


@dataclass
class HotSpotControl:
    version: int
    age_frame: int
    species: int
    occult: int
    level: int
    color_id: int
    cursor: int
    region: int
    sub_region: int
    gender_restriction: int
    texture: int
    sliders: list[HotSpotSlider] = field(default_factory=list)

    @classmethod
    def parse(cls, data: bytes) -> "HotSpotControl":
        r = Reader(data)
        version, ag, species = r.u32(), r.u32(), r.u32()
        occult = r.u32() if version >= 0x0F else 0
        level, color, cursor = r.u8(), r.u8(), r.u8()
        region, sub = r.u32(), r.u32()
        gender, texture = r.u8(), r.u64()
        r.u32()
        hc = cls(version, ag, species, occult, level, color, cursor, region, sub, gender, texture)
        for _ in range(r.u8()):
            views, flip = r.u8(), bool(r.u8())
            unk = (r.f32(), r.f32())
            hc.sliders.append(HotSpotSlider(views, flip, unk, tuple(r.u64() for _ in range(4))))
        return hc


@dataclass
class CASPreset:
    version: int
    age_gender: int
    frame: int
    species: int
    region: int
    sub_region: int
    archetype: int
    display_index: float
    name_key: int
    desc_key: int
    sculpts: list[int]
    modifiers: list[tuple[int, float]]
    physique: tuple[float, float, float, float] | None
    chance_for_random: float
    tags: list[tuple[int, int]]

    @classmethod
    def parse(cls, data: bytes) -> "CASPreset":
        r = Reader(data)
        version, ag = r.u32(), r.u32()
        frame = r.u32() if version >= 11 else 0
        species = r.u32() if version >= 8 else 1
        region = r.u32()
        sub = r.u32() if version >= 9 else 0
        archetype, display = r.u32(), r.f32()
        name_key, desc_key = r.u32(), r.u32()
        sculpts = []
        for _ in range(r.u32()):
            sculpts.append(r.u64())
            if version < 9:
                r.u32()  # region
        mods = []
        for _ in range(r.u32()):
            inst, weight = r.u64(), r.f32()
            if version < 9:
                r.u32()
            mods.append((inst, weight))
        physique = (r.f32(), r.f32(), r.f32(), r.f32()) if r.u8() else None
        if version >= 12 and r.u8():
            r.u64()
            r.u32()
        chance = r.f32()
        tags = []
        for _ in range(r.u32()):
            t = r.u16()
            v = r.u32() if version >= 10 else r.u16()
            tags.append((t, v))
        return cls(version, ag, frame, species, region, sub, archetype, display, name_key, desc_key,
                   sculpts, mods, physique, chance, tags)


PARSERS = {SMOD_TYPE: SimModifier.parse, SCULPT_TYPE: Sculpt.parse, BOND_TYPE: BoneDelta.parse,
           HOTC_TYPE: HotSpotControl.parse, CPRE_TYPE: CASPreset.parse}
