"""Read-only access to the Sims in a Sims 4 save file.

A .save file is a DBPF package; resource type 0x0000000D holds the
SaveGameData protobuf (as read by TS4 SimRipper).  Field numbers used here
(from SimRipper's src/Proto/FileSerialization.cs and Outfits.cs):

    SaveGameData: 6 = repeated SimData sims
    SimData:      1 sim_id, 4 household_id, 5 first_name, 6 last_name,
                  7 gender, 8 age, 18 facial_attr (bytes), 28 genetic_data,
                  60 extended_species
    GeneticData:  1 sculpts_and_mods_attr (bytes, same blob format)

Nothing in this module writes to disk.
"""
from __future__ import annotations

from dataclasses import dataclass

from .dbpf import Package
from .facial_blob import FacialData
from .protowire import LEN, fields_by_num

SAVE_GAME_DATA_TYPE = 0x0000000D

AGES = {0x1: "BABY", 0x80: "INFANT", 0x2: "TODDLER", 0x4: "CHILD", 0x8: "TEEN",
        0x10: "YOUNGADULT", 0x20: "ADULT", 0x40: "ELDER"}
GENDERS = {0x1000: "MALE", 0x2000: "FEMALE"}


@dataclass
class SavedSim:
    sim_id: int
    household_id: int | None
    first_name: str
    last_name: str
    age: str
    gender: str
    extended_species: int | None
    facial_attr: bytes
    genetic_facial_attr: bytes | None

    @property
    def facial(self) -> FacialData:
        return FacialData.decode(self.facial_attr)

    @property
    def name(self) -> str:
        return f"{self.first_name} {self.last_name}"


def _one(fields, num, default=None):
    fs = fields.get(num)
    return fs[0] if fs else default


def parse_sim(buf: bytes) -> SavedSim:
    f = fields_by_num(buf)

    def num(n):
        x = _one(f, n)
        return x.int if x is not None else None

    def text(n):
        x = _one(f, n)
        return x.text if x is not None else ""

    genetic = None
    g = _one(f, 28)
    if g is not None and g.wire == LEN:
        gf = _one(fields_by_num(g.payload), 1)
        genetic = gf.payload if gf is not None else None
    face = _one(f, 18)
    age, gender = num(8), num(7)
    return SavedSim(
        sim_id=num(1) or 0, household_id=num(4), first_name=text(5), last_name=text(6),
        age=AGES.get(age, str(age)), gender=GENDERS.get(gender, str(gender)),
        extended_species=num(60), facial_attr=face.payload if face is not None else b"",
        genetic_facial_attr=genetic,
    )


def read_save_game_data(path: str) -> bytes:
    with Package(path) as pkg:
        entries = pkg.find(SAVE_GAME_DATA_TYPE)
        if not entries:
            raise ValueError(f"{path}: no SaveGameData resource (type 0x0000000D)")
        return pkg.read(entries[0])


def iter_sims(save_game_data: bytes):
    for fld in fields_by_num(save_game_data).get(6, []):
        if fld.wire == LEN:
            yield parse_sim(fld.payload)


def load_sims(path: str) -> list[SavedSim]:
    return list(iter_sims(read_save_game_data(path)))
