"""Facial modifier catalog built from EA's Client_CASModifierTuning XML.

The game ships one tuning resource per age (and species) listing every CAS
modifier with its Scale (applied to the stored amount before the morph is
evaluated, per TS4 SimRipper), LimitDirectManip (cap when dragging in CAS),
LimitRandomize and optional MinValue.  Stored amounts are in [0, 1]; each
anatomical axis is normally two one-sided modifiers (e.g. Nose_Wide and
Nose_Narrow), which this module pairs into a single signed axis in [-1, 1].

The pairing here is a name heuristic.  The authoritative pairing is the
HotSpotControl (HOTC) resources, whose sliders list the SMOD for each drag
direction; Phase 1 replaces this heuristic with HOTC data.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .fnv import fnv64

FACE_REGIONS = {"Eyes", "Nose", "Mouth", "Cheeks", "Chin", "Jaw", "Head", "Brows", "Ears", "Forehead"}

# Suffix pairs (positive, negative).  Order is arbitrary but fixed.
OPPOSITES = [
    ("Big", "Small"), ("Wide", "Narrow"), ("Long", "Short"), ("Up", "Down"),
    ("Forward", "Backward"), ("Far", "Close"), ("Out", "In"), ("RotateOut", "RotateIn"),
    ("RotateUp", "RotateDown"), ("CurveUp", "CurveDown"), ("SweepUp", "SweepDown"),
    ("CornerUp", "CornerDown"), ("CornerOut", "CornerIn"), ("BumpUp", "BumpDown"),
    ("Plump", "Thin"), ("Expand", "Contract"), ("Arch", "Flat"), ("Lift", "Droop"),
    ("WideBone", "NarrowBone"), ("FaceForward", "FaceBackward"), ("IrisBig", "IrisSmall"),
    ("TipVScaleUp", "TipVScaleDown"), ("BendForward", "BendBackward"),
    ("CornersForward", "CornersBackward"), ("Thick", "Thin"), ("Deep", "Shallow"),
]

_NAME_RE = re.compile(r"^(?P<agegender>[a-z]{2})head(?:Modifier_)?\s*_?\s*(?P<region>[A-Za-z]+)_(?P<feature>.+)$")


@dataclass(frozen=True)
class ModifierInfo:
    name: str
    key: int
    region: str
    feature: str
    scale: float = 1.0
    limit_direct_manip: float | None = None
    limit_randomize: float | None = None
    min_value: float | None = None

    @property
    def is_face(self) -> bool:
        return self.region in FACE_REGIONS


@dataclass(frozen=True)
class Axis:
    """A signed slider: value > 0 drives `positive`, value < 0 drives `negative`."""
    region: str
    name: str
    positive: ModifierInfo
    negative: ModifierInfo | None

    def to_amounts(self, value: float) -> dict[int, float]:
        if value >= 0 or self.negative is None:
            return {self.positive.key: max(value, 0.0)}
        return {self.negative.key: -value}


def parse_name(name: str) -> tuple[str, str]:
    m = _NAME_RE.match(name.strip())
    if not m:
        return "Unknown", name
    return m.group("region"), m.group("feature").strip()


def load_tuning_xml(xml_bytes: bytes) -> list[ModifierInfo]:
    root = ET.fromstring(xml_bytes.decode("utf-8-sig"))
    out = []
    for u in root.iter("U"):
        d = {c.get("n"): (c.text or "").strip() for c in u}
        if "ModifierName" not in d:
            continue
        name = d["ModifierName"]
        region, feature = parse_name(name)

        def f(k):
            return float(d[k]) if d.get(k) else None
        out.append(ModifierInfo(
            name=name, key=fnv64(name), region=region, feature=feature,
            scale=f("Scale") if f("Scale") is not None else 1.0,
            limit_direct_manip=f("LimitDirectManip"),
            limit_randomize=f("LimitRandomize"),
            min_value=f("MinValue"),
        ))
    return out


def pair_axes(mods: list[ModifierInfo]) -> list[Axis]:
    by_region_feature = {(m.region, m.feature.replace(" ", "")): m for m in mods}
    used: set[int] = set()
    axes: list[Axis] = []
    # Longest suffixes first so "RotateUp" wins over "Up".
    for pos_s, neg_s in sorted(OPPOSITES, key=lambda p: -len(p[0])):
        for (region, feature), m in by_region_feature.items():
            if m.key in used or not feature.endswith(pos_s):
                continue
            stem = feature[: -len(pos_s)]
            other = by_region_feature.get((region, stem + neg_s))
            if other is None or other.key in used:
                continue
            used.update((m.key, other.key))
            axes.append(Axis(region, (stem.rstrip("_") or region) + f"[{pos_s}/{neg_s}]", m, other))
    for m in mods:
        if m.key not in used:
            axes.append(Axis(m.region, m.feature, m, None))
    return sorted(axes, key=lambda a: (a.region, a.name))
