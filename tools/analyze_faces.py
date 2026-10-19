"""Analyse six-view sheets or photos and compare the subjects.

    python tools/fetch_face_models.py                      # once
    python tools/analyze_faces.py a.png b.png control.png --control control --out results/face_analysis

For each input it writes <out>/<subject>/profile.json (schema facescan.profile/1)
and <out>/<subject>/diagnostics.png (annotated views).  With two or more inputs
it also writes comparison.md / comparison.json / comparison.png.
Outputs contain face images: keep them out of version control (results/ is
git-ignored).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from faceanalysis.analyze import _clean, analyze_file  # noqa: E402
from faceanalysis.compare import distinctive, pairwise, replicate_matching  # noqa: E402
from faceanalysis.draw import annotate_frontal, annotate_profile, annotate_turned, contact_sheet  # noqa: E402
from faceanalysis.landmarks import LandmarkDetector  # noqa: E402
from faceanalysis.measure import METRICS  # noqa: E402

SHOW_FRONTAL = ["face_width_to_height", "ipd_to_face_width", "intercanthal_to_ipd", "alar_to_intercanthal",
                "mouth_width_to_ipd", "jaw_to_face_width", "midface_ratio", "lower_face_ratio"]


def diagnostics(profile: dict, views) -> "Image":
    tiles = []
    for v in views:
        rec = next(r for r in profile["views"] if r["panel"] == v.panel.index)
        yaw = f"yaw {rec['yaw_deg']:+.1f}" if rec.get("yaw_deg") is not None else "no MediaPipe face"
        title = f"panel {v.panel.index}: {v.label} ({yaw})"
        if v.label.startswith("front") and v.obs is not None:
            ms = {k: profile["measurements"][k]["per_view"].get(v.label) for k in SHOW_FRONTAL
                  if k in profile["measurements"]}
            tiles.append((title, annotate_frontal(v.panel.image, v.obs.points, {k: x for k, x in ms.items() if x is not None})))
        elif v.label.startswith("three_quarter") and v.obs is not None:
            tiles.append((title, annotate_turned(v.panel.image, v.obs.points,
                                                 "frontalised; used only to check vertical ratios")))
        elif v.profile is not None:
            tiles.append((title, annotate_profile(v.panel.image, v.profile)))
    return contact_sheet(tiles, title=f"{profile['subject']}: facial analysis diagnostics")


def chart(profiles: list[dict], control: str | None, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    ref = next((p for p in profiles if p["subject"] == control), None)
    keys = [k for k in METRICS if all(k in p["measurements"] and p["measurements"][k]["value"] is not None
                                      and p["measurements"][k]["reliability"] in ("high", "medium") for p in profiles)]
    keys = [k for k in keys if METRICS[k].unit == "ratio"]
    fig, ax = plt.subplots(figsize=(9, 0.32 * len(keys) + 1.6))
    colours = ["#2a9d8f", "#e76f51", "#264653", "#e9c46a", "#8d99ae"]
    for i, p in enumerate(profiles):
        xs, es = [], []
        for k in keys:
            m = p["measurements"][k]
            base = ref["measurements"][k]["value"] if ref else 1.0
            xs.append(100 * (m["value"] - base) / base if ref else m["value"])
            es.append(100 * m["uncertainty"] / base if ref else m["uncertainty"])
        ys = [j + (i - (len(profiles) - 1) / 2) * 0.22 for j in range(len(keys))]
        ax.errorbar(xs, ys, xerr=es, fmt="o", color=colours[i % len(colours)], label=p["subject"], capsize=2, ms=4)
    ax.set_yticks(range(len(keys)))
    ax.set_yticklabels(keys, fontsize=8)
    ax.axvline(0, color="#999", lw=0.8)
    ax.set_xlabel(f"% difference from {control}" if ref else "value")
    ax.invert_yaxis()
    ax.legend(fontsize=8, loc="lower right")
    ax.set_title("Facial proportions (bars = measurement uncertainty)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def report(profiles, pw, dist, rep_front, rep_prof, control) -> str:
    L = ["# Facial analysis comparison", ""]
    L.append(f"Subjects: {', '.join(p['subject'] for p in profiles)}" + (f" (control: {control})" if control else ""))
    L += ["", "## Measurements", "", "Value ± uncertainty, with reliability (H/M/L). `!` marks a cross-view contradiction.", ""]
    L.append("| Measurement | " + " | ".join(p["subject"] for p in profiles) + " |")
    L.append("|---|" + "---|" * len(profiles))
    for k in METRICS:
        cells = []
        for p in profiles:
            m = p["measurements"].get(k)
            if not m or m["value"] is None:
                cells.append("–")
                continue
            flag = " !" if m["contradiction"] else ""
            cells.append(f"{m['value']:.3f} ± {m['uncertainty']:.3f} ({m['reliability'][0].upper()}){flag}")
        L.append(f"| {k} | " + " | ".join(cells) + " |")
    L += ["", "## What makes each face different", ""]
    for subj, rows in dist.items():
        L.append(f"**{subj}**" + (f" vs {control}" if control and subj != control else " vs the mean of the others") + ":")
        if not rows:
            L.append("- no measurement differs by more than 2× its uncertainty")
        for r in rows:
            pct = (f" ({r['percent']:+.1f}%)" if r["percent"] is not None
                   else f" ({r['difference']:+.2f}°)" if r["unit"] == "deg" else f" (Δ {r['difference']:+.3f})")
            L.append(f"- {r['meaning']}: {r['metric']} {r['value']:.3f} vs {r['reference']:.3f}{pct}, z = {r['z']:+.1f}")
        L.append("")
    L += ["## Pairwise distinguishability", "", "d′ = difference / combined uncertainty. d′ > 2: distinguishable; d′ > 4: clearly distinct.", "",
          "| Pair | measurements compared | d′>2 | d′>4 | mean d′ | top differences |", "|---|---|---|---|---|---|"]
    for pair, r in pw.items():
        top = ", ".join(f"{t['metric']} ({t['d_prime']})" for t in r["top"][:4])
        L.append(f"| {pair} | {r['compared']} | {r['distinct_d_gt_2']} | {r['distinct_d_gt_4']} | {r['mean_d_prime']} | {top} |")
    for title, rep in (("frontal: front panel vs close-up panel", rep_front), ("profile: left vs right profile", rep_prof)):
        L += ["", f"## Replicate matching ({title})", ""]
        if "distance_matrix_noise_units" not in rep:
            L.append(rep.get("note", "n/a"))
            continue
        L.append(f"{len(rep['features'])} measurements. Distance in noise units; rows = {rep['views_a']}, columns = {rep['views_b']}.")
        L += ["", "| | " + " | ".join(rep["subjects"]) + " |", "|---|" + "---|" * len(rep["subjects"])]
        for s, row in zip(rep["subjects"], rep["distance_matrix_noise_units"]):
            L.append(f"| {s} | " + " | ".join(f"{x:.2f}" for x in row) + " |")
        L.append(f"\nCorrect matches: {sum(rep['correct'])}/{len(rep['correct'])}; margin ratios {rep['margin_ratio']}.")
        if "profile" in title:
            L.append("Note: every sheet's profiles were flagged as mirror copies, so this match is expected and is "
                     "not evidence of real-world repeatability.")
        else:
            L.append("Note: the two panels share one pose and appear to be renders of the same image, so this tests "
                     "detection repeatability only.")
    L += ["", "## Consistency warnings", ""]
    for p in profiles:
        warns = [c for c in p["consistency"] if c["severity"] == "warning"]
        L.append(f"**{p['subject']}** ({len(warns)} warnings)")
        L += [f"- [{c['check']}] {c['message']}" for c in warns]
        L.append("")
    L += ["## Caveats", "",
          "- Three subjects only illustrate the method; they do not measure accuracy. See docs/12-analyzer-evaluation.md.",
          "- Front and close-up panels share a pose (and here appear to be re-renders of one image), so their agreement shows "
          "detection repeatability, not anatomical truth.",
          "- AI-generated views can be internally consistent and still wrong."]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=Path("results/face_analysis"))
    ap.add_argument("--control", default=None, help="subject name (file stem) to use as the reference")
    ap.add_argument("--model", default=None, help="path to face_landmarker.task")
    ap.add_argument("--no-images", action="store_true", help="skip annotated images")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    profiles = []
    with LandmarkDetector(args.model) as det:
        for path in args.inputs:
            prof, views = analyze_file(path, det)
            d = args.out / prof["subject"]
            d.mkdir(exist_ok=True)
            (d / "profile.json").write_text(json.dumps(prof, indent=1))
            if not args.no_images:
                diagnostics(prof, views).save(d / "diagnostics.png")
            n_warn = sum(c["severity"] == "warning" for c in prof["consistency"])
            print(f"{prof['subject']}: {len(prof['measurements'])} measurements, {len(prof['solver_features'])} solver features, "
                  f"{n_warn} warnings -> {d}")
            profiles.append(prof)
    if len(profiles) >= 2:
        pw = pairwise(profiles)
        dist = distinctive(profiles, reference=args.control)
        rep_f = replicate_matching(profiles, ["front"], ["front_closeup"])
        rep_p = replicate_matching(profiles, ["profile_facing_left"], ["profile_facing_right"])
        (args.out / "comparison.json").write_text(json.dumps(_clean(
            {"pairwise": pw, "distinctive": dist, "replicate_front": rep_f, "replicate_profile": rep_p}), indent=1))
        (args.out / "comparison.md").write_text(report(profiles, pw, dist, rep_f, rep_p, args.control))
        if not args.no_images:
            chart(profiles, args.control, args.out / "comparison.png")
        print(f"comparison -> {args.out / 'comparison.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
