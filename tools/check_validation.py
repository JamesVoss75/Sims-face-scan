"""Experiment E2 analysis: did the test face survive live mode, CAS, save and reload?

READ-ONLY.  Reads the records written by the bridge mod's validate commands
(facescan/validation/<sim_id>.json) and, optionally, the save file, then
re-checks everything independently with this project's own blob codec.

    python tools/check_validation.py                       # auto-detect folders, newest save
    python tools/check_validation.py --save path\\to\\Slot_00000002.save

Writes facescan/validation/report.md and report.json next to the records.
Exit code 0 only if every required checkpoint and the on-disk check pass.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ts4face.facial_blob import FacialData, diff  # noqa: E402
from ts4face.fnv import fnv64  # noqa: E402
from ts4face.paths import latest_save, user_data_dir  # noqa: E402
from ts4face.savegame import load_sims  # noqa: E402

REQUIRED = ["live_applied", "after_cas", "after_save", "after_reload", "after_cas_reopen"]


def split_problems(problems: list[str], probe_keys: set[int]) -> tuple[list[str], list[str]]:
    core, probe = [], []
    for p in problems:
        (probe if any(f"0x{k:016X}" in p for k in probe_keys) else core).append(p)
    return core, probe


def analyse_record(record: dict, saved_sims: dict | None) -> dict:
    expected = FacialData.decode(bytes.fromhex(record["expected_hex"]))
    baseline = FacialData.decode(bytes.fromhex(record["baseline_hex"]))
    probe_keys = {fnv64(t["name"]) for t in record["test_face"] if t["role"] == "probe"}
    result = {"sim": record["sim"], "sim_id": record["sim_id"], "mod_version": record.get("mod_version"),
              "python": record.get("python"), "checks": [], "notes": []}

    # The expected face must equal baseline + test face, and keep everything else.
    for t in record["test_face"]:
        if abs(expected.face_dict().get(int(t["key"], 16), -1) - t["amount"]) > 1e-6:
            result["notes"].append(f"expected face does not contain {t['name']}={t['amount']}")
    kept = {k: v for k, v in baseline.face_dict().items()
            if k not in {int(t["key"], 16) for t in record["test_face"] + record["removed"]}}
    for k, v in kept.items():
        if expected.face_dict().get(k) != v:
            result["notes"].append(f"unrelated modifier 0x{k:016X} was not preserved by validate_begin")
    if expected.aged_face_modifiers != baseline.aged_face_modifiers or expected.sculpts != baseline.sculpts:
        result["notes"].append("validate_begin changed sculpts or aged modifiers")

    by_label = {}
    for cp in record["checkpoints"]:
        actual = FacialData.decode(bytes.fromhex(cp["blob_hex"]))
        core, probe = split_problems(diff(expected, actual), probe_keys)
        ours = "PASS" if not core else "FAIL"
        if ours != cp["result"]:
            result["notes"].append(f"checkpoint {cp['label']}: mod said {cp['result']}, independent check says {ours}")
        by_label[cp["label"]] = {"label": cp["label"], "result": ours, "core": core, "probe": probe,
                                 "time": cp["time"]}
    for label in REQUIRED:
        result["checks"].append(by_label.get(label, {"label": label, "result": "MISSING", "core": [], "probe": []}))
    for label, c in by_label.items():
        if label not in REQUIRED:
            result["checks"].append(c)

    if saved_sims is not None:
        sim = saved_sims.get(record["sim_id"])
        if sim is None:
            check = {"label": "save_file_on_disk", "result": "MISSING", "core": ["Sim not found in save"], "probe": []}
        else:
            core, probe = split_problems(diff(expected, sim.facial), probe_keys)
            check = {"label": "save_file_on_disk", "result": "PASS" if not core else "FAIL", "core": core, "probe": probe}
            if sim.genetic_facial_attr is not None:
                result["notes"].append("genetic copy: " + ("identical to facial_attr"
                                       if sim.genetic_facial_attr == sim.facial_attr else
                                       "differs from facial_attr (expected: genetics keep the pre-test face)"))
        result["checks"].append(check)
    result["passed"] = all(c["result"] == "PASS" for c in result["checks"])
    return result


def render_markdown(results: list[dict], save_path) -> str:
    lines = ["# FaceScan validation report", "", f"Generated {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"Save file checked: {save_path or 'none'}", ""]
    for r in results:
        lines += [f"## {r['sim']}", "", f"Mod {r['mod_version']}, game Python {r['python']}. "
                  f"**Overall: {'PASS' if r['passed'] else 'FAIL'}**", "",
                  "| Checkpoint | Result | Problems | Probe observations |", "|---|---|---|---|"]
        for c in r["checks"]:
            lines.append(f"| {c['label']} | {c['result']} | {'<br>'.join(c['core']) or '-'} | {'<br>'.join(c['probe']) or '-'} |")
        if r["notes"]:
            lines += ["", "Notes:"] + [f"- {n}" for n in r["notes"]]
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user-dir", type=Path, default=None, help="Documents/Electronic Arts/The Sims 4")
    ap.add_argument("--save", type=Path, default=None, help="save file to check (default: newest in saves/)")
    ap.add_argument("--no-save", action="store_true", help="skip the on-disk save check")
    args = ap.parse_args()

    user_dir = args.user_dir or user_data_dir()
    vdir = user_dir / "facescan" / "validation"
    records = sorted(p for p in vdir.glob("*.json") if p.name != "report.json") if vdir.is_dir() else []
    if not records:
        print(f"No validation records in {vdir}. Run facescan.validate_begin in the game first.", file=sys.stderr)
        return 2

    save_path, saved = None, None
    if not args.no_save:
        save_path = args.save or latest_save(user_dir / "saves")
        if save_path:
            saved = {s.sim_id: s for s in load_sims(str(save_path))}

    results = [analyse_record(json.loads(p.read_text()), saved) for p in records]
    (vdir / "report.json").write_text(json.dumps(results, indent=2))
    md = render_markdown(results, save_path)
    (vdir / "report.md").write_text(md)
    print(md)
    print(f"Report written to {vdir / 'report.md'}")
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
