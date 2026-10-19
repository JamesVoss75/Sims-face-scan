"""Turn a six-view sheet (or a set of photos) into a structured facial profile.

Pipeline per input: split into panels -> MediaPipe landmarks + head pose ->
assign each panel a view from the *measured* pose (labels on the sheet are not
trusted) -> frontal, frontalised-3/4 and silhouette-profile measurements ->
cross-view consistency and reliability -> appearance -> JSON profile
(schema "facescan.profile/1", see docs/11-facial-analysis.md).
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from . import __version__
from .appearance import describe
from .consistency import combine, mirror_similarity, resample_similarity
from .landmarks import IDX, FaceObservation, LandmarkDetector
from .measure import (CROSS_VIEW_PAIRS, METRICS, asymmetry, frontal_metrics, frontalized_metrics,
                      silhouette_metrics)
from .profile import ProfileResult, Segmentation, analyze_profile, facing_direction, segment_person
from .sheet import Panel, split_sheet

SCHEMA = "facescan.profile/1"
FRONT_MAX_YAW = 12.0
TURNED_MAX_YAW = 45.0  # MediaPipe yaw; it saturates around 55-60 deg on true profiles

# Frontal metrics that survive rigid frontalisation of a turned view.  Horizontal
# ratios that involve the far side of the face (eye spacing, iris size, face
# width) are biased after frontalisation because MediaPipe's depth for occluded
# parts is a learned prior; they are not used as checks.  Re-validate on the
# real-photo evaluation set (docs/12-analyzer-evaluation.md).
TURNED_VIEW_OK = {"midface_ratio", "lower_face_ratio", "nose_length_to_face_height", "stomion_position",
                  "upper_lip_height", "lower_lip_height", "philtrum_to_face_height", "lip_ratio",
                  "jaw_to_face_width", "mouth_to_alar_width", "brow_arch", "eye_height_to_width"}
MIRROR_IOU, MIRROR_NCC = 0.97, 0.85


@dataclass
class ViewRecord:
    panel: Panel
    label: str = "unknown"
    obs: FaceObservation | None = None
    seg: Segmentation | None = None
    profile: ProfileResult | None = None
    notes: list = field(default_factory=list)


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not math.isfinite(float(o)) else round(float(o), 5)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def label_views(views: list[ViewRecord]) -> None:
    for v in views:
        if v.obs is not None and abs(v.obs.yaw) < FRONT_MAX_YAW:
            v.label = "front"
        elif v.obs is not None and abs(v.obs.yaw) < TURNED_MAX_YAW:
            v.label = "three_quarter_facing_" + ("left" if v.obs.yaw < 0 else "right")
        else:
            if v.obs is not None:
                facing = "left" if v.obs.yaw < 0 else "right"
                sil, margin = facing_direction(v.seg.mask)
                if sil in ("left", "right") and sil != facing:
                    v.notes.append(f"MediaPipe yaw says facing {facing}, silhouette says {sil}; using silhouette")
                    facing = sil
            else:
                facing, margin = facing_direction(v.seg.mask)
                v.notes.append("no face found by MediaPipe (normal for true profiles); direction from silhouette")
            v.label = "profile_facing_" + facing if facing in ("left", "right") else "unknown"
    fronts = [v for v in views if v.label == "front"]
    if len(fronts) > 1:
        def scale(v):
            return np.linalg.norm(v.obs.p("R_iris") - v.obs.p("L_iris")) / v.panel.image.shape[1]
        fronts.sort(key=scale)
        for k, v in enumerate(fronts[1:], 1):
            v.label = "front_closeup" if k == len(fronts) - 1 else f"front_{k + 1}"
    # Disambiguate duplicates of other labels.
    seen: dict[str, int] = {}
    for v in views:
        seen[v.label] = seen.get(v.label, 0) + 1
        if seen[v.label] > 1:
            v.label = f"{v.label}_{seen[v.label]}"


def analyze_image(rgb: np.ndarray, detector: LandmarkDetector, subject: str, source: str = "") -> tuple[dict, list[ViewRecord]]:
    panels = split_sheet(rgb)
    views = [ViewRecord(p) for p in panels]
    for v in views:
        v.obs = detector.detect(v.panel.image)
        v.seg = segment_person(v.panel.image)
    label_views(views)
    by = {v.label: v for v in views}
    checks: list[dict] = []

    def check(kind, severity, message, **data):
        checks.append({"check": kind, "severity": severity, "message": message, **data})

    # ---------- frontal views
    frontal_views = [v for v in views if v.label.startswith("front")]
    ref = by.get("front") or (frontal_views[0] if frontal_views else None)
    per_metric: dict[str, dict[str, float]] = {k: {} for k in METRICS}
    for v in frontal_views:
        m = frontal_metrics(v.obs.points)
        if v.seg.confidence >= 0.6 and v.seg.mask[:3].sum() == 0:  # head not cut at the panel top
            m.update(silhouette_metrics(v.seg.mask, v.obs.p("menton")[1], v.obs.p("nasion")[1]))
        for k, x in m.items():
            per_metric[k][v.label] = x
    turned = [v for v in views if v.label.startswith("three_quarter")]
    if ref is not None:
        for v in turned:
            for k, x in frontalized_metrics(v.obs, ref.obs).items():
                if k in TURNED_VIEW_OK:
                    per_metric[k][v.label] = x

    # ---------- profiles
    profiles = [v for v in views if v.label.startswith("profile")]
    for v in profiles:
        facing = "left" if "facing_left" in v.label else "right"
        v.profile = analyze_profile(v.panel.image, facing)
        for k, x in v.profile.metrics.items():
            if not k.startswith("_") and ("p_" + k) in METRICS:
                per_metric["p_" + k][v.label] = x
        for w in v.profile.warnings:
            check("profile_landmarks", "warning", f"{v.label}: {w}")

    # ---------- independence of views
    groups: list[set[str]] = []
    fl = {v.label for v in frontal_views}
    if fl:
        groups.append(fl)  # same pose = one source of geometric evidence
    pl, pr = by.get("profile_facing_left"), by.get("profile_facing_right")
    if pl and pr:
        ms = mirror_similarity(pl.panel.image, pl.seg.mask, pr.panel.image, pr.seg.mask)
        dup = ms["iou"] >= MIRROR_IOU or ms["ncc"] >= MIRROR_NCC
        sev = "warning" if dup else "info"
        msg = ("left and right profiles are near mirror images "
               f"(silhouette IoU {ms['iou']}, texture NCC {ms['ncc']}); treated as ONE source of evidence"
               if dup else f"profiles differ as independent photos would (IoU {ms['iou']}, NCC {ms['ncc']})")
        if ms["ncc"] >= MIRROR_NCC:
            msg += "; the texture itself is mirrored (synthetic view)"
        check("profile_mirror", sev, msg, **ms)
        if dup:
            groups.append({pl.label, pr.label})
    tl, tr = by.get("three_quarter_facing_left"), by.get("three_quarter_facing_right")
    if tl and tr:
        ms = mirror_similarity(tl.panel.image, tl.seg.mask, tr.panel.image, tr.seg.mask)
        check("three_quarter_mirror", "warning" if ms["ncc"] >= MIRROR_NCC else "info",
              f"3/4 views mirror similarity IoU {ms['iou']}, NCC {ms['ncc']}", **ms)
        yl, yr = abs(tl.obs.yaw), abs(tr.obs.yaw)
        if abs(yl - yr) > 6:
            check("three_quarter_pose", "warning", f"3/4 views are turned by different amounts ({yl:.1f} vs {yr:.1f} deg)")
        check("three_quarter_yaw", "info", f"measured 3/4 yaw {yl:.1f} / {yr:.1f} deg (MediaPipe; a nominal 45 deg view "
              "often measures 25-35 deg because the estimator under-reports large yaw)")
    if ref is not None and by.get("front_closeup") is not None:
        c = by["front_closeup"]
        sim = resample_similarity(ref.panel.image, ref.obs.points, c.panel.image, c.obs.points)
        check("closeup_vs_front", "info", f"close-up shares fine detail with the front view (NCC {sim:.2f}); "
              "same pose, so it is counted as the same evidence as the front view", ncc=round(sim, 3))
    for v in views:
        # Blendshapes are only meaningful for frontal and 3/4 views; neutral faces
        # routinely score 0.1-0.3 on blinks, so only strong activations count.
        if v.obs is not None and not v.label.startswith("profile"):
            bs = v.obs.blendshapes
            expr = {k: round(bs.get(k, 0.0), 2) for k in ("mouthSmileLeft", "mouthSmileRight", "jawOpen",
                                                          "eyeBlinkLeft", "eyeBlinkRight", "eyeWideLeft", "eyeWideRight")}
            strong = {k: x for k, x in expr.items() if x > 0.5}
            if strong:
                check("expression", "warning", f"{v.label}: non-neutral expression {strong}")
        uses_silhouette = v.label == "front" or v.label.startswith("profile")
        if uses_silhouette and v.seg.confidence < 0.6:
            check("background", "warning", f"{v.label}: background not uniform; silhouette measurements unreliable")
        for n in v.notes:
            check("view", "info", f"{v.label}: {n}")

    # ---------- combine metrics
    primary_front = {v.label for v in frontal_views}
    primary_prof = {v.label for v in profiles}
    measurements = {}
    for k, d in METRICS.items():
        if not per_metric[k]:
            continue
        primary = primary_prof if d.source == "profile" else primary_front
        measurements[k] = combine(k, per_metric[k], groups, primary, {v.label for v in turned})
        measurements[k]["description"] = d.description
        if measurements[k]["contradiction"]:
            check("contradiction", "warning", f"{k}: {measurements[k]['contradiction']}", per_view=measurements[k]["per_view"])
    for f_name, p_name in CROSS_VIEW_PAIRS:
        if f_name in measurements and p_name in measurements and measurements[p_name]["value"] is not None:
            a, b = measurements[f_name]["value"], measurements[p_name]["value"]
            rel = abs(a - b) / max(1e-9, (a + b) / 2)
            tol = 2 * METRICS[f_name].tolerance
            check("frontal_vs_profile", "warning" if rel > tol else "info",
                  f"{f_name} frontal {a:.3f} vs profile {b:.3f} (diff {100 * rel:.1f}%, tolerance {100 * tol:.0f}%)",
                  relative_difference=round(rel, 4))

    # ---------- appearance and asymmetry (frontal)
    appearance = {}
    for v in frontal_views:
        appearance[v.label] = describe(v.panel.image, v.obs.points)
    labels = list(appearance)
    if len(labels) >= 2:
        a, b = appearance[labels[0]], appearance[labels[1]]
        for part in ("skin", "eyes", "brows", "lips"):
            if a.get(part, {}).get("lab") and b.get(part, {}).get("lab"):
                de = float(np.linalg.norm(np.array(a[part]["lab"]) - np.array(b[part]["lab"])))
                check("appearance_agreement", "warning" if de > 6 else "info",
                      f"{part} colour {labels[0]} vs {labels[1]}: delta E {de:.1f}", delta_e=round(de, 2))
    asym = asymmetry(ref.obs.points) if ref is not None else {}
    if ref is not None and abs(ref.obs.yaw) > 4:
        asym["caution"] = f"front view yaw {ref.obs.yaw:.1f} deg inflates measured asymmetry"

    view_out = []
    for v in views:
        rec = {"panel": v.panel.index, "bbox": list(v.panel.bbox), "view": v.label,
               "detector": "mediapipe" if v.obs is not None else "silhouette",
               "segmentation_confidence": v.seg.confidence, "notes": v.notes}
        if v.obs is not None:
            w, h = v.obs.image_size
            rec["landmarks_normalized"] = np.round(v.obs.points / np.array([w, h, w]), 4).tolist()
            rec.update({"yaw_deg": v.obs.yaw, "pitch_deg": v.obs.pitch, "roll_deg": v.obs.roll,
                        "ipd_px": float(np.linalg.norm(v.obs.p("R_iris") - v.obs.p("L_iris")))})
        if v.profile is not None:
            rec["profile_points"] = {k: list(p) for k, p in v.profile.points.items()}
            rec["profile_point_confidence"] = v.profile.confidence
        view_out.append(rec)

    weights = {"high": 1.0, "medium": 0.5}
    solver = {k: {"value": m["value"], "uncertainty": m["uncertainty"], "weight": weights[m["reliability"]]}
              for k, m in measurements.items() if m["reliability"] in weights and m["value"] is not None}
    profile = {
        "schema": SCHEMA, "subject": subject,
        "source": {"file": Path(source).name if source else "", "sha256": hashlib.sha256(rgb.tobytes()).hexdigest()[:16],
                   "size": [int(rgb.shape[1]), int(rgb.shape[0])], "panels": len(panels)},
        "analyzer": {"version": __version__, "landmarks": "MediaPipe Face Landmarker (478)"},
        "views": view_out, "measurements": measurements, "asymmetry": asym,
        "appearance": appearance, "consistency": checks,
        "solver_features": solver,
        "notes": ["All lengths are ratios or angles; no absolute size is estimated.",
                  "views[].landmarks_normalized: MediaPipe 478 points as (x/width, y/height, z/width) of the panel.",
                  "solver_features holds only measurements graded medium or high, for the Sims mapping step."],
    }
    return _clean(profile), views


def analyze_file(path: str | Path, detector: LandmarkDetector, subject: str | None = None):
    rgb = np.asarray(Image.open(path).convert("RGB"))
    return analyze_image(rgb, detector, subject or Path(path).stem, str(path))
