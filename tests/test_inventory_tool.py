import json
import struct
import sys
from pathlib import Path

from tests.helpers import write_package
from tests.test_resources import context_header, itg
from ts4face.fnv import fnv64

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import inventory_game_files  # noqa: E402

TUNING = (b'<?xml version="1.0" encoding="utf-8"?><I c="Client_CASModifierTuning" n="Client_CASModifierTuning_YoungAdult">'
          b'<L n="Modifiers"><U><T n="ModifierName">yfheadNose_Wide</T><T n="Scale">0.5</T></U></L></I>')


def smod(region=1):
    body = struct.pack("<IIIII", 144, 0x10 | 0x3000, region, 0, 0) + itg(0) + itg(0xD1) + itg(0) + struct.pack("<I", 0)
    return context_header() + body


def hotspot(refs):
    d = struct.pack("<IIII", 0x0F, 0x10 | 0x3000, 1, 0) + struct.pack("<BBB", 0, 1, 1) + struct.pack("<II", 1, 0)
    d += struct.pack("<BQI", 0, 0, 0) + struct.pack("<B", 1) + struct.pack("<BBff", 1, 0, 0, 1) + struct.pack("<4Q", *refs)
    return d


def test_inventory_builds_catalog(tmp_path, monkeypatch):
    wide = fnv64("yfheadNose_Wide")
    game = tmp_path / "The Sims 4"
    write_package(game / "Data" / "Client" / "ClientFullBuild0.package", [
        (0xC5F6763E, 0, wide, smod(), False),
        (0xC5F6763E, 0, 0x77, b"garbage", False),                 # counted as a parse failure
        (0xDB43E069, 0, 0xD1, b"dmap", True),
        (0x8B18FF6E, 0, 0x6658, hotspot((wide, 0x77, 0, 0x1234)), False),
        (0x03B33DDF, 0, 0x99, TUNING, True),
    ])
    out = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["x", str(game), "--out", str(out)])
    assert inventory_game_files.main() == 0
    summary = json.loads((out / "summary.json").read_text())
    catalog = json.loads((out / "catalog.json").read_text())
    assert summary["parse_failures"] == {"SimModifier:ValueError": 1}
    assert summary["cross_reference_checks"]["hotspot_smod_refs_resolve"] == "66.7% (2/3)"
    assert summary["cross_reference_checks"]["smod_links_resolve"] == "100.0% (1/1)"
    assert catalog["smods"][0]["name"] == "yfheadNose_Wide" and catalog["smods"][0]["region"] == "NOSE"
    assert catalog["hotspots"][0]["sliders"][0]["modifiers"][0]["name"] == "yfheadNose_Wide"
    assert catalog["tuning"]["Client_CASModifierTuning_YoungAdult"][0]["scale"] == 0.5
