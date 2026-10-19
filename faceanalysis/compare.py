"""Quantitative comparison of facial profiles.

Answers three questions for a set of subjects:
  1. Which measurements differ between subjects by more than the measurement
     noise (pairwise d' = |a - b| / sqrt(ua^2 + ub^2))?
  2. What makes each face distinctive relative to the others / a control?
  3. Replicate matching: if each subject is measured twice from different
     panels, does each measurement set match its own subject best?
Small samples (e.g. three sheets) only illustrate the method; real accuracy
needs the protocol in docs/12-analyzer-evaluation.md.
"""
from __future__ import annotations

import itertools
import math

import numpy as np

from .measure import METRICS

USABLE = {"high", "medium"}

PLAIN = {
    "face_width_to_height": ("wider face", "narrower/longer face"),
    "jaw_to_face_width": ("wider jaw relative to cheekbones", "more tapered jaw"),
    "chin_width_to_mouth": ("broader chin", "narrower chin"),
    "midface_ratio": ("longer midface/nose", "shorter midface/nose"),
    "lower_face_ratio": ("longer lower face", "shorter lower face"),
    "ipd_to_face_width": ("eyes set wide for face width", "eyes set close for face width"),
    "intercanthal_to_ipd": ("wider-set inner eye corners", "closer inner eye corners"),
    "eye_width_to_ipd": ("longer eye openings", "shorter eye openings"),
    "eye_height_to_width": ("rounder/more open eyes", "narrower eye opening"),
    "canthal_tilt_deg": ("upturned outer eye corners", "downturned outer eye corners"),
    "iris_to_eye_width": ("larger iris relative to eye", "smaller iris relative to eye"),
    "brow_height_to_ipd": ("brows set higher above the eyes", "brows set lower/closer to eyes"),
    "brow_tilt_deg": ("brows rise outward", "brows fall outward"),
    "brow_arch": ("more arched brows", "flatter brows"),
    "alar_to_intercanthal": ("wider nose", "narrower nose"),
    "nose_length_to_face_height": ("longer nose", "shorter nose"),
    "mouth_width_to_ipd": ("wider mouth", "narrower mouth"),
    "mouth_to_alar_width": ("mouth wide relative to nose", "mouth narrow relative to nose"),
    "upper_lip_height": ("fuller upper lip", "thinner upper lip"),
    "lower_lip_height": ("fuller lower lip", "thinner lower lip"),
    "lip_ratio": ("upper lip large relative to lower", "upper lip small relative to lower"),
    "philtrum_to_face_height": ("longer philtrum", "shorter philtrum"),
    "stomion_position": ("mouth set lower", "mouth set higher"),
    "head_width_to_height": ("broader skull", "narrower/taller skull"),
    "p_nasal_tip_projection": ("more projecting nose tip", "less projecting nose tip"),
    "p_nasofrontal_angle_deg": ("shallower nasion (flatter bridge start)", "deeper nasion"),
    "p_facial_convexity_deg": ("more convex profile", "flatter profile"),
    "p_chin_projection": ("more projecting chin", "more receding chin"),
    "p_head_height_to_length": ("taller head for its length", "longer head for its height"),
    "p_forehead_height_ratio": ("taller forehead/cranium", "shorter forehead/cranium"),
    "p_upper_lip_to_eline": ("upper lip further forward (relative to nose-chin line)", "upper lip set further back behind the nose-chin line"),
    "p_lower_lip_to_eline": ("lower lip further forward (relative to nose-chin line)", "lower lip set further back behind the nose-chin line"),
    "p_nasal_length_ratio": ("longer nose in profile", "shorter nose in profile"),
    "p_nasolabial_angle_deg": ("more upturned nose tip", "more downturned nose tip"),
    "p_midface_ratio": ("longer midface (profile)", "shorter midface (profile)"),
    "p_lower_face_ratio": ("longer lower face (profile)", "shorter lower face (profile)"),
    "p_upper_lip_to_lower_face": ("mouth set lower (profile)", "mouth set higher (profile)"),
    "p_chin_throat_angle_deg": ("more obtuse chin-throat angle", "sharper chin-throat angle"),
    "jaw_angle_deg": ("softer (more obtuse) jaw angle", "sharper jaw angle"),
}


def _val(p, k):
    m = p["measurements"].get(k)
    if not m or m["value"] is None or m["reliability"] not in USABLE:
        return None
    return m["value"], max(m["uncertainty"], 1e-6)


def pairwise(profiles: list[dict]) -> dict:
    out = {}
    for a, b in itertools.combinations(profiles, 2):
        rows = []
        for k in METRICS:
            va, vb = _val(a, k), _val(b, k)
            if va is None or vb is None:
                continue
            dprime = abs(va[0] - vb[0]) / math.hypot(va[1], vb[1])
            rows.append({"metric": k, "a": va[0], "b": vb[0], "d_prime": round(dprime, 2)})
        rows.sort(key=lambda r: -r["d_prime"])
        out[f"{a['subject']} vs {b['subject']}"] = {
            "compared": len(rows), "distinct_d_gt_2": sum(r["d_prime"] > 2 for r in rows),
            "distinct_d_gt_4": sum(r["d_prime"] > 4 for r in rows), "top": rows[:10],
            "mean_d_prime": round(float(np.mean([r["d_prime"] for r in rows])), 2) if rows else 0.0}
    return out


def distinctive(profiles: list[dict], reference: str | None = None, top: int = 8) -> dict:
    out = {}
    for p in profiles:
        if reference is not None and p["subject"] != reference:
            others = [q for q in profiles if q["subject"] == reference]
        else:  # no reference, or the reference itself: compare with the mean of the others
            others = [q for q in profiles if q is not p]
        if not others:
            continue
        rows = []
        for k in METRICS:
            v = _val(p, k)
            ov = [_val(q, k) for q in others]
            if v is None or any(o is None for o in ov):
                continue
            ref = float(np.mean([o[0] for o in ov]))
            unc = math.hypot(v[1], float(np.mean([o[1] for o in ov])))
            z = (v[0] - ref) / unc
            words = PLAIN.get(k, (f"higher {k}", f"lower {k}"))[0 if z > 0 else 1]
            # Percentages only for strictly positive quantities (not signed distances).
            rel = (v[0] - ref) / ref * 100 if METRICS[k].unit == "ratio" and ref > 0 and v[0] > 0 else None
            rows.append({"metric": k, "value": v[0], "reference": round(ref, 4), "z": round(z, 2),
                         "percent": None if rel is None else round(rel, 1),
                         "difference": v[0] - ref, "unit": METRICS[k].unit, "meaning": words})
        rows.sort(key=lambda r: -abs(r["z"]))
        out[p["subject"]] = [r for r in rows if abs(r["z"]) >= 2][:top]
    return out


def replicate_matching(profiles: list[dict], set_a: list[str], set_b: list[str]) -> dict:
    """Match measurement vectors from view set A to those from view set B across subjects.

    Each feature is scaled by its noise floor (median uncertainty), so the
    distance is in units of measurement noise.
    """
    feats = []
    for k in METRICS:
        ok = True
        for p in profiles:
            pv = p["measurements"].get(k, {}).get("per_view", {})
            if not any(v in pv for v in set_a) or not any(v in pv for v in set_b):
                ok = False
        if ok:
            feats.append(k)
    if not feats or len(profiles) < 2:
        return {"features": feats, "note": "not enough shared measurements"}
    noise = np.array([np.median([p["measurements"][k]["uncertainty"] for p in profiles]) for k in feats]) + 1e-9

    def vec(p, views):
        pv = [p["measurements"][k]["per_view"] for k in feats]
        return np.array([np.mean([d[v] for v in views if v in d]) for d in pv]) / noise
    A = np.array([vec(p, set_a) for p in profiles])
    B = np.array([vec(p, set_b) for p in profiles])
    D = np.sqrt(((A[:, None, :] - B[None, :, :]) ** 2).mean(axis=2))
    names = [p["subject"] for p in profiles]
    correct = [int(np.argmin(D[i])) == i for i in range(len(names))]
    margins = []
    for i in range(len(names)):
        others = [D[i, j] for j in range(len(names)) if j != i]
        margins.append(round(float(min(others) / max(D[i, i], 1e-9)), 2))
    return {"features": feats, "views_a": set_a, "views_b": set_b, "subjects": names,
            "distance_matrix_noise_units": np.round(D, 2).tolist(), "correct": correct,
            "accuracy": sum(correct) / len(correct), "margin_ratio": margins,
            "note": "rows = set A, columns = set B; margin = nearest wrong distance / own distance (>1 = correct)"}
