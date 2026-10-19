"""Phase 1 experiment E1: inventory the facial customization data in a Sims 4 install.

READ-ONLY.  Opens package files for reading and writes a report to --out; it
never modifies the game folder.  Run on the Windows machine with the game:

    python tools/inventory_game_files.py "C:/Program Files/EA Games/The Sims 4" --out inventory

Produces:
    inventory/summary.json      resource counts per type and per package
    inventory/tuning/*.xml      every Client_CASModifier* tuning resource
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ts4face.dbpf import Package  # noqa: E402

# Resource type IDs (from TS4 SimRipper / MorphMaker Enums.cs).
TYPES = {
    0xC5F6763E: "SimModifier",
    0x9D1AB874: "Sculpt",
    0xEAA32ADD: "CASPreset",
    0x8B18FF6E: "HotSpotControl",
    0x067CAA11: "BlendGeometry",
    0xDB43E069: "DeformerMap",
    0x0355E0A6: "BoneDelta",
    0x015A1849: "GEOM",
    0x8EAF13DE: "Rig",
    0x034AEECB: "CASPart",
    0x0354796A: "SkinTone",
}
TUNING_TYPES = (0xF3ABFF3C, 0x03B33DDF)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("game_dir", type=Path)
    ap.add_argument("--out", type=Path, default=Path("inventory"))
    args = ap.parse_args()

    packages = sorted(args.game_dir.rglob("Client*Build*.package")) + sorted(args.game_dir.rglob("Simulation*Build*.package"))
    if not packages:
        print(f"No Client*/Simulation* build packages under {args.game_dir}", file=sys.stderr)
        return 1
    (args.out / "tuning").mkdir(parents=True, exist_ok=True)

    totals: Counter = Counter()
    unique: dict[str, set[int]] = defaultdict(set)
    per_package = {}
    tuning_found = 0
    for path in packages:
        try:
            pkg = Package(str(path))
        except (ValueError, OSError) as e:
            print(f"skip {path}: {e}", file=sys.stderr)
            continue
        with pkg:
            counts = Counter()
            for e in pkg.entries:
                if e.type in TYPES:
                    counts[TYPES[e.type]] += 1
                    unique[TYPES[e.type]].add(e.instance)
                elif e.type in TUNING_TYPES:
                    try:
                        data = pkg.read(e)
                    except (NotImplementedError, ValueError):
                        continue
                    if b"Client_CASModifier" in data[:400] or b"client_CASModifier" in data[:400]:
                        (args.out / "tuning" / f"{e.instance:016X}.xml").write_bytes(data)
                        tuning_found += 1
            if counts:
                per_package[str(path.relative_to(args.game_dir))] = dict(counts)
                totals.update(counts)

    summary = {
        "packages_scanned": len(packages),
        "resource_totals": dict(totals),
        "unique_instances": {k: len(v) for k, v in unique.items()},
        "cas_modifier_tuning_files": tuning_found,
        "per_package": per_package,
    }
    (args.out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "per_package"}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
