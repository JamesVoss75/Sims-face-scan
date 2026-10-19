"""Experiment E1: inventory the facial customization data in a Sims 4 install.

READ-ONLY.  Opens the game's .package files for reading only and writes its
results to --out.  Run on the Windows machine with the game (or use
scripts/windows/run_experiment1.bat, which finds the game for you):

    python tools/inventory_game_files.py "C:/Program Files/EA Games/The Sims 4" --out e1_results

Writes:
    summary.json   counts, parse failures, cross-reference checks  -> send back
    catalog.json   every face SMOD / sculpt / preset / hotspot with names where known -> send back
    tuning/*.xml   EA's CAS modifier tuning (stays on your machine)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ts4face.catalog import load_tuning_xml  # noqa: E402
from ts4face.dbpf import Package  # noqa: E402
from ts4face.paths import find_install_dirs  # noqa: E402
from ts4face.resources import (BGEO_TYPE, BOND_TYPE, CPRE_TYPE, DMAP_TYPE, FACE_REGION_IDS,  # noqa: E402
                               GEOM_TYPE, HOTC_TYPE, HOTSPOT_LEVELS, PARSERS, REGIONS, SCULPT_TYPE,
                               SMOD_TYPE, VIEW_FLAGS, age_gender, decode_flags)

TYPE_NAMES = {SMOD_TYPE: "SimModifier", SCULPT_TYPE: "Sculpt", CPRE_TYPE: "CASPreset",
              HOTC_TYPE: "HotSpotControl", BGEO_TYPE: "BlendGeometry", DMAP_TYPE: "DeformerMap",
              BOND_TYPE: "BoneDelta", GEOM_TYPE: "GEOM", 0x8EAF13DE: "Rig", 0x034AEECB: "CASPart",
              0x0354796A: "SkinTone"}
TUNING_TYPES = (0xF3ABFF3C, 0x03B33DDF)
PARSE_TYPES = (SMOD_TYPE, SCULPT_TYPE, CPRE_TYPE, HOTC_TYPE, BOND_TYPE)


def package_order(paths: list[Path]) -> list[Path]:
    # Base game first, packs next, Delta builds last, so later entries override earlier ones.
    def key(p: Path):
        s = str(p).lower()
        return ("delta" in s, "\\data\\" not in s and "/data/" not in s, s)
    return sorted(paths, key=key)


def region_name(r: int) -> str:
    return REGIONS.get(r, str(r))


def pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.1f}% ({n}/{d})" if d else "n/a (0)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("game_dir", type=Path, nargs="?", help="Sims 4 install folder (auto-detected if omitted)")
    ap.add_argument("--out", type=Path, default=Path("e1_results"))
    args = ap.parse_args()

    game_dir = args.game_dir
    if game_dir is None:
        found = find_install_dirs()
        if not found:
            print("Could not find The Sims 4. Pass the install folder as an argument.", file=sys.stderr)
            return 1
        game_dir = found[0]
    print(f"Game folder: {game_dir}")
    packages = package_order(list(game_dir.rglob("Client*Build*.package")) + list(game_dir.rglob("Simulation*Build*.package")))
    if not packages:
        print(f"No Client*/Simulation* build packages under {game_dir}", file=sys.stderr)
        return 1
    (args.out / "tuning").mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    totals: Counter = Counter()
    present: dict[int, set[int]] = defaultdict(set)
    parsed: dict[int, dict[int, object]] = defaultdict(dict)
    failures: Counter = Counter()
    failure_examples: dict[str, str] = {}
    tuning_files = 0
    names: dict[int, str] = {}
    tuning_rows: dict[str, list[dict]] = {}
    per_package = {}

    for i, path in enumerate(packages, 1):
        print(f"[{i}/{len(packages)}] {path.relative_to(game_dir)}", flush=True)
        try:
            pkg = Package(str(path))
        except (ValueError, OSError) as e:
            failures[f"package:{type(e).__name__}"] += 1
            failure_examples.setdefault("package", f"{path}: {e}")
            continue
        with pkg:
            counts = Counter()
            for e in pkg.entries:
                if e.type in TYPE_NAMES:
                    counts[TYPE_NAMES[e.type]] += 1
                    present[e.type].add(e.instance)
                if e.type in PARSE_TYPES:
                    try:
                        parsed[e.type][e.instance] = PARSERS[e.type](pkg.read(e))
                    except Exception as ex:  # record and continue: format drift shows up here
                        k = f"{TYPE_NAMES[e.type]}:{type(ex).__name__}"
                        failures[k] += 1
                        failure_examples.setdefault(k, f"{e.tgi} in {path.name}: {ex}")
                elif e.type in TUNING_TYPES:
                    try:
                        data = pkg.read(e)
                    except Exception:
                        continue
                    if b"CASModifierTuning" in data[:400]:
                        (args.out / "tuning" / f"{e.instance:016X}.xml").write_bytes(data)
                        tuning_files += 1
                        try:
                            label = ET.fromstring(data.decode("utf-8-sig")).get("n", f"{e.instance:016X}")
                            mods = load_tuning_xml(data)
                        except Exception as ex:
                            failures["tuning:" + type(ex).__name__] += 1
                            continue
                        tuning_rows[label] = [{"name": m.name, "key": f"0x{m.key:016X}", "scale": m.scale,
                                               "limit_direct_manip": m.limit_direct_manip,
                                               "limit_randomize": m.limit_randomize, "min_value": m.min_value}
                                              for m in mods]
                        for m in mods:
                            names[m.key] = m.name
            if counts:
                per_package[str(path.relative_to(game_dir))] = dict(counts)
                totals.update(counts)

    smods, sculpts = parsed[SMOD_TYPE], parsed[SCULPT_TYPE]
    hotcs, cpres = parsed[HOTC_TYPE], parsed[CPRE_TYPE]

    def nm(k):
        return names.get(k)

    def link_ok(key, typ):
        return key is not None and bool(key) and key.instance in present[typ]

    # Cross-reference checks: if a parser misreads a field, these rates collapse.
    hot_refs = [m for h in hotcs.values() for s in h.sliders for m in s.modifiers if m]
    pre_mods = [m for p in cpres.values() for m, _ in p.modifiers]
    pre_sculpts = [s for p in cpres.values() for s in p.sculpts if s]
    smod_links = [(s.dmap_shape, DMAP_TYPE) for s in smods.values() if s.dmap_shape] + \
                 [(s.bone_pose, BOND_TYPE) for s in smods.values() if s.bone_pose] + \
                 [(s.bgeo, BGEO_TYPE) for s in smods.values() if s.bgeo]
    checks = {
        "hotspot_smod_refs_resolve": pct(sum(m in present[SMOD_TYPE] for m in hot_refs), len(hot_refs)),
        "preset_modifier_refs_resolve": pct(sum(m in present[SMOD_TYPE] for m in pre_mods), len(pre_mods)),
        "preset_sculpt_refs_resolve": pct(sum(s in present[SCULPT_TYPE] for s in pre_sculpts), len(pre_sculpts)),
        "smod_links_resolve": pct(sum(link_ok(k, t) for k, t in smod_links), len(smod_links)),
        "tuning_names_match_smods": pct(sum(k in present[SMOD_TYPE] for k in names), len(names)),
        "smod_regions_known": pct(sum(s.region in REGIONS for s in smods.values()), len(smods)),
        "preset_weights_in_0_1": pct(sum(0 <= w <= 1 for p in cpres.values() for _, w in p.modifiers), len(pre_mods)),
    }

    face_smods = {k: s for k, s in smods.items() if s.region in FACE_REGION_IDS}
    catalog = {
        "game_dir": str(game_dir),
        "smods": [{"key": f"0x{k:016X}", "name": nm(k), "region": region_name(s.region), "version": s.version,
                   **age_gender(s.age_gender), "bgeo": bool(s.bgeo), "dmap_shape": bool(s.dmap_shape),
                   "dmap_normal": bool(s.dmap_normal), "bond": bool(s.bone_pose),
                   "bone_entries": len(s.bone_entries)} for k, s in sorted(face_smods.items())],
        "sculpts": [{"key": f"0x{k:016X}", "region": region_name(s.region), **age_gender(s.age_gender),
                     "bgeo": bool(s.bgeo), "dmap_shape": bool(s.dmap_shape), "bond": bool(s.bone_delta)}
                    for k, s in sorted(sculpts.items()) if s.region in FACE_REGION_IDS],
        "presets": [{"key": f"0x{k:016X}", "region": region_name(p.region), **age_gender(p.age_gender),
                     "frame": age_gender(p.frame)["genders"], "species": p.species, "archetype": p.archetype,
                     "display_index": p.display_index, "sculpts": [f"0x{s:016X}" for s in p.sculpts],
                     "modifiers": [{"key": f"0x{m:016X}", "name": nm(m), "weight": w} for m, w in p.modifiers]}
                    for k, p in sorted(cpres.items()) if p.region in FACE_REGION_IDS],
        "hotspots": [{"key": f"0x{k:016X}", "region": region_name(h.region), "level": HOTSPOT_LEVELS.get(h.level, h.level),
                      **age_gender(h.age_frame), "species": h.species, "gender_restriction": h.gender_restriction,
                      "sliders": [{"views": decode_flags(s.views, VIEW_FLAGS), "flip": s.flip,
                                   "modifiers": [{"key": f"0x{m:016X}", "name": nm(m)} if m else None
                                                 for m in s.modifiers]} for s in h.sliders]}
                     for k, h in sorted(hotcs.items()) if h.region in FACE_REGION_IDS],
        "tuning": tuning_rows,
    }
    summary = {
        "tool": "inventory_game_files 2", "game_dir": str(game_dir), "seconds": round(time.time() - t0, 1),
        "packages_scanned": len(packages), "resource_totals": dict(totals),
        "unique_instances": {TYPE_NAMES[t]: len(v) for t, v in present.items()},
        "parsed": {TYPE_NAMES[t]: len(v) for t, v in parsed.items()},
        "parse_failures": dict(failures), "parse_failure_examples": failure_examples,
        "versions_seen": {TYPE_NAMES[t]: dict(Counter(getattr(o, "version", None) for o in v.values()))
                          for t, v in parsed.items()},
        "face_counts": {"smods": len(catalog["smods"]), "named_smods": sum(1 for s in catalog["smods"] if s["name"]),
                        "sculpts": len(catalog["sculpts"]), "presets": len(catalog["presets"]),
                        "hotspots": len(catalog["hotspots"])},
        "sculpts_per_region": dict(Counter(s["region"] for s in catalog["sculpts"])),
        "cross_reference_checks": checks,
        "cas_modifier_tuning_files": tuning_files,
        "per_package": per_package,
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2))
    (args.out / "catalog.json").write_text(json.dumps(catalog, indent=1))
    print(json.dumps({k: v for k, v in summary.items() if k not in ("per_package", "versions_seen")}, indent=2))
    print(f"\nResults in {args.out.resolve()}  (send summary.json and catalog.json)")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(3)
