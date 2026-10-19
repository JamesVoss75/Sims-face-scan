from ts4face.catalog import load_tuning_xml, pair_axes
from ts4face.fnv import fnv64

# Instance IDs as they appear in the game's packages (from TS4 MorphMaker's ModifierList.txt).
KNOWN = {
    "yfheadNose_TipWide": 0x8088D1E4B2013F98,
    "yfheadChin_Wide": 0x814F11012B65B21C,
    "ymheadFeet_Big": 0x814A1078EB0A9302,
    "yfheadJaw_Down": 0x8D3B32D6AFB7EDFF,
}

TUNING = b"""<?xml version="1.0" encoding="utf-8"?>
<I c="Client_CASModifierTuning" i="casmodifiertuning" n="client_CASModifierTuning_Test" s="1">
  <L n="Modifiers">
    <U><T n="ModifierName">yfheadNose_Wide</T><T n="LimitDirectManip">1</T><T n="Scale">0.5</T></U>
    <U><T n="ModifierName">yfheadNose_Narrow</T><T n="Scale">0.25</T><T n="MinValue">0.1</T></U>
    <U><T n="ModifierName">yfheadModifier_Eyes_RotateUp</T></U>
    <U><T n="ModifierName">yfheadModifier_Eyes_RotateDown</T></U>
    <U><T n="ModifierName">yfheadModifier_Cheeks_Gaunt</T></U>
    <U><T n="ModifierName">yfheadThighs_Big</T></U>
  </L>
</I>"""


def test_fnv64_matches_game_instance_ids():
    for name, inst in KNOWN.items():
        assert fnv64(name) == inst, name


def test_load_and_pair():
    mods = load_tuning_xml(TUNING)
    assert len(mods) == 6
    nose_wide = next(m for m in mods if m.name == "yfheadNose_Wide")
    assert (nose_wide.region, nose_wide.feature, nose_wide.scale, nose_wide.limit_direct_manip) == ("Nose", "Wide", 0.5, 1.0)
    face = [m for m in mods if m.is_face]
    assert len(face) == 5
    axes = {a.name: a for a in pair_axes(face)}
    nose = axes["Nose[Wide/Narrow]"]
    assert nose.to_amounts(0.4) == {fnv64("yfheadNose_Wide"): 0.4}
    assert nose.to_amounts(-0.4) == {fnv64("yfheadNose_Narrow"): 0.4}
    assert "Eyes[RotateUp/RotateDown]" in axes
    assert axes["Gaunt"].negative is None
