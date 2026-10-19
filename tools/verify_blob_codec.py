"""Experiment E1b: check the facial-blob codec against every Sim in your saves.

READ-ONLY.  For each .save file, decodes every Sim's facial_attr and genetic
copy with ts4face.facial_blob, re-encodes it, and checks the bytes are
identical.  Also counts aged modifiers and fields the codec does not know.

    python tools/verify_blob_codec.py                 # all saves in Documents/.../saves
    python tools/verify_blob_codec.py --saves D:\\backup\\saves --out e1b.json

The JSON output contains only counts and modifier IDs, not names or photos.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ts4face.facial_blob import FacialData  # noqa: E402
from ts4face.paths import user_data_dir  # noqa: E402
from ts4face.savegame import load_sims  # noqa: E402


def check_blob(raw: bytes, stats: Counter, key_counts: Counter) -> str | None:
    try:
        fd = FacialData.decode(raw)
    except ValueError as e:
        stats["decode_errors"] += 1
        return f"decode error: {e}"
    stats["blobs"] += 1
    stats["sculpts"] += len(fd.sculpts)
    for name in ("face_modifiers", "body_modifiers", "aged_face_modifiers", "aged_body_modifiers"):
        mods = getattr(fd, name)
        stats[name] += len(mods)
        stats["modifiers_with_unknown_fields"] += sum(1 for m in mods if m.unknown)
        stats["modifiers_missing_key_or_amount"] += sum(1 for m in mods if m.key is None or m.amount is None)
        stats["amounts_outside_0_1"] += sum(1 for m in mods if m.amount is not None and not 0 <= m.amount <= 1)
        if name == "face_modifiers":
            key_counts.update(f"0x{m.key:016X}" for m in mods if m.key is not None)
    if fd.unknown:
        stats["blobs_with_unknown_fields"] += 1
    if fd.sculpts_packed:
        stats["packed_sculpts"] += 1
    if fd.encode() != raw:
        stats["not_byte_identical"] += 1
        return "re-encoding is not byte-identical"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--saves", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=Path("e1b_codec_report.json"))
    args = ap.parse_args()
    saves_dir = args.saves or user_data_dir() / "saves"
    files = sorted(saves_dir.glob("*.save"))
    if not files:
        print(f"No .save files in {saves_dir}", file=sys.stderr)
        return 2

    stats, key_counts, problems = Counter(), Counter(), []
    for path in files:
        try:
            sims = load_sims(str(path))
        except (ValueError, OSError, NotImplementedError) as e:
            problems.append(f"{path.name}: cannot read save: {e}")
            continue
        stats["saves"] += 1
        for sim in sims:
            stats["sims"] += 1
            for label, raw in (("facial_attr", sim.facial_attr), ("genetic", sim.genetic_facial_attr)):
                if raw:
                    err = check_blob(raw, stats, key_counts)
                    if err:
                        problems.append(f"{path.name} sim {sim.sim_id} {label}: {err}")

    report = {"stats": dict(stats), "problems": problems[:200],
              "most_common_face_modifiers": key_counts.most_common(60)}
    args.out.write_text(json.dumps(report, indent=2))
    print(json.dumps({"stats": report["stats"], "problem_count": len(problems)}, indent=2))
    print(f"Full report: {args.out.resolve()}")
    ok = stats["blobs"] > 0 and not problems
    print("RESULT:", "PASS - every blob round-trips byte for byte" if ok else "CHECK THE PROBLEMS LIST")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
