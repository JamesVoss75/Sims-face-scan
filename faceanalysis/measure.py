"""Scale-free facial measurements from landmarks.

Every measurement is a ratio or an angle, so photo resolution, distance and
focal length cancel to first order.  The catalogue below documents each one
(region, method, base reliability, cross-view tolerance); nothing here is
tuned to particular faces.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .landmarks import (IDX, L_BROW_LOWER, L_IRIS_RING, MIDLINE, R_BROW_LOWER, R_IRIS_RING,
                        SYMMETRY_PAIRS, FaceObservation)


@dataclass(frozen=True)
class MetricDef:
    region: str
    unit: str        # "ratio" or "deg"
    base: str        # inherent reliability: high / medium / low
    tolerance: float  # acceptable cross-view disagreement (relative for ratios, absolute degrees for angles)
    source: str      # frontal / profile / silhouette
    description: str


METRICS: dict[str, MetricDef] = {
    # Head and face proportions
    "head_width_to_height": MetricDef("head", "ratio", "medium", 0.04, "silhouette", "cranial width at mid-forehead / vertex-menton height (front silhouette; needs a bald or tight-haired head)"),
    "face_width_to_height": MetricDef("head", "ratio", "high", 0.04, "frontal", "bizygomatic width (234-454) / nasion-menton height"),
    "jaw_to_face_width": MetricDef("jaw", "ratio", "medium", 0.05, "frontal", "bigonial width (172-397) / bizygomatic width"),
    "chin_width_to_mouth": MetricDef("chin", "ratio", "medium", 0.06, "frontal", "lower jaw width at 176-400 / mouth width"),
    "jaw_angle_deg": MetricDef("jaw", "deg", "low", 5.0, "frontal", "frontal angle at gonion between cheek (234/454) and menton directions, mean of both sides"),
    "midface_ratio": MetricDef("head", "ratio", "high", 0.04, "frontal", "nasion-subnasale / nasion-menton (vertical, along the facial midline)"),
    "lower_face_ratio": MetricDef("head", "ratio", "high", 0.04, "frontal", "subnasale-menton / nasion-menton"),
    # Eyes
    "ipd_to_face_width": MetricDef("eyes", "ratio", "high", 0.03, "frontal", "interpupillary distance / bizygomatic width"),
    "intercanthal_to_ipd": MetricDef("eyes", "ratio", "high", 0.04, "frontal", "inner-corner distance (133-362) / IPD"),
    "eye_width_to_ipd": MetricDef("eyes", "ratio", "high", 0.04, "frontal", "palpebral fissure length (corner to corner), mean of both eyes / IPD"),
    "eye_height_to_width": MetricDef("eyes", "ratio", "medium", 0.10, "frontal", "lid opening (159-145, 386-374) / fissure length; expression-dependent"),
    "canthal_tilt_deg": MetricDef("eyes", "deg", "high", 3.0, "frontal", "angle inner->outer corner above horizontal (positive = outer corner higher), mean of both eyes"),
    "iris_to_eye_width": MetricDef("eyes", "ratio", "medium", 0.06, "frontal", "iris diameter / fissure length"),
    # Brows
    "brow_height_to_ipd": MetricDef("brows", "ratio", "medium", 0.08, "frontal", "upper lid to lower brow edge (mid-brow) / IPD; grooming- and expression-dependent"),
    "brow_tilt_deg": MetricDef("brows", "deg", "medium", 4.0, "frontal", "angle inner->outer end of the lower brow edge (positive = outer end higher)"),
    "brow_arch": MetricDef("brows", "ratio", "medium", 0.25, "frontal", "height of the brow peak above the inner-outer chord / brow length"),
    # Nose
    "alar_to_intercanthal": MetricDef("nose", "ratio", "high", 0.05, "frontal", "nose width at the alae (64-294) / inner-corner distance"),
    "nose_length_to_face_height": MetricDef("nose", "ratio", "high", 0.04, "frontal", "nasion-subnasale / nasion-menton (same as midface_ratio in frontal view)"),
    # Mouth
    "mouth_width_to_ipd": MetricDef("mouth", "ratio", "high", 0.04, "frontal", "mouth corners (61-291) / IPD"),
    "mouth_to_alar_width": MetricDef("mouth", "ratio", "high", 0.05, "frontal", "mouth width / nose width"),
    "upper_lip_height": MetricDef("mouth", "ratio", "medium", 0.10, "frontal", "upper vermilion (0-13) / nasion-menton"),
    "lower_lip_height": MetricDef("mouth", "ratio", "medium", 0.10, "frontal", "lower vermilion (14-17) / nasion-menton"),
    "lip_ratio": MetricDef("mouth", "ratio", "medium", 0.12, "frontal", "upper / lower vermilion height"),
    "philtrum_to_face_height": MetricDef("mouth", "ratio", "medium", 0.08, "frontal", "subnasale-labrale superius / nasion-menton"),
    "stomion_position": MetricDef("mouth", "ratio", "high", 0.05, "frontal", "subnasale-stomion / subnasale-menton"),
    # Profile (silhouette of 90 degree views)
    "p_midface_ratio": MetricDef("head", "ratio", "high", 0.04, "profile", "profile nasion-subnasale / nasion-menton"),
    "p_lower_face_ratio": MetricDef("head", "ratio", "high", 0.04, "profile", "profile subnasale-menton / nasion-menton"),
    "p_head_height_to_length": MetricDef("head", "ratio", "medium", 0.04, "profile", "vertex-menton / head length (glabella-opisthocranion proxy)"),
    "p_forehead_height_ratio": MetricDef("head", "ratio", "medium", 0.06, "profile", "vertex-nasion / nasion-menton"),
    "p_nasal_length_ratio": MetricDef("nose", "ratio", "high", 0.05, "profile", "nasion-pronasale / nasion-menton"),
    "p_nasal_tip_projection": MetricDef("nose", "ratio", "high", 0.08, "profile", "pronasale distance from the nasion-subnasale line / nasal length"),
    "p_nasofrontal_angle_deg": MetricDef("nose", "deg", "high", 4.0, "profile", "angle glabella-nasion-pronasale"),
    "p_nasolabial_angle_deg": MetricDef("nose", "deg", "medium", 6.0, "profile", "angle pronasale-subnasale-labrale superius (columella approximated by the tip direction)"),
    "p_facial_convexity_deg": MetricDef("head", "deg", "high", 3.0, "profile", "180 - angle glabella-subnasale-pogonion (larger = more convex profile)"),
    "p_chin_projection": MetricDef("chin", "ratio", "medium", 0.15, "profile", "pogonion distance from the nasion-menton line / nasion-menton"),
    "p_upper_lip_to_eline": MetricDef("mouth", "ratio", "medium", 0.25, "profile", "labrale superius to Ricketts E-line (prn-pg) / nasion-menton; negative = behind"),
    "p_lower_lip_to_eline": MetricDef("mouth", "ratio", "medium", 0.25, "profile", "labrale inferius to E-line / nasion-menton"),
    "p_upper_lip_to_lower_face": MetricDef("mouth", "ratio", "medium", 0.08, "profile", "subnasale-stomion / subnasale-menton"),
    "p_chin_throat_angle_deg": MetricDef("jaw", "deg", "low", 8.0, "profile", "angle pogonion-menton-cervical point (soft tissue, posture dependent)"),
}

# Measurements that exist both frontally and in profile: cross-modal consistency checks.
CROSS_VIEW_PAIRS = [("midface_ratio", "p_midface_ratio"), ("lower_face_ratio", "p_lower_face_ratio"),
                    ("stomion_position", "p_upper_lip_to_lower_face")]


def _rotate_upright(pts: np.ndarray) -> np.ndarray:
    """Rotate 2D landmarks so the pupils are level (removes in-plane roll)."""
    r, l = pts[IDX["R_iris"], :2], pts[IDX["L_iris"], :2]
    ang = math.atan2(l[1] - r[1], l[0] - r[0])
    c, s = math.cos(-ang), math.sin(-ang)
    centre = (r + l) / 2
    out = pts.copy()
    xy = pts[:, :2] - centre
    out[:, 0] = c * xy[:, 0] - s * xy[:, 1] + centre[0]
    out[:, 1] = s * xy[:, 0] + c * xy[:, 1] + centre[1]
    return out


def frontal_metrics(obs_points: np.ndarray) -> dict[str, float]:
    p = _rotate_upright(np.asarray(obs_points, dtype=float))

    def P(k):
        return p[IDX[k] if isinstance(k, str) else k, :2]

    def d(a, b):
        return float(np.linalg.norm(P(a) - P(b)))

    def vert(a, b):
        return float(P(b)[1] - P(a)[1])

    def tilt(inner, outer, side):
        v = P(outer) - P(inner)
        if side == "R":           # subject right = image left: outer is at smaller x
            v = -v
        return math.degrees(math.atan2(-v[1], v[0]))  # image y grows downward

    ipd = d("R_iris", "L_iris")
    fh = vert("nasion", "menton")
    bizyg = d("R_zy", "L_zy")
    mouth = d("R_ch", "L_ch")
    alar = d("R_al", "L_al")
    icd = d("R_en", "L_en")
    eye_w = (d("R_ex", "R_en") + d("L_ex", "L_en")) / 2
    m: dict[str, float] = {
        "face_width_to_height": bizyg / fh,
        "jaw_to_face_width": d("R_go", "L_go") / bizyg,
        "chin_width_to_mouth": d("R_chin", "L_chin") / mouth,
        "midface_ratio": vert("nasion", "subnasale") / fh,
        "lower_face_ratio": vert("subnasale", "menton") / fh,
        "ipd_to_face_width": ipd / bizyg,
        "intercanthal_to_ipd": icd / ipd,
        "eye_width_to_ipd": eye_w / ipd,
        "eye_height_to_width": ((d("R_lid_up", "R_lid_lo") / d("R_ex", "R_en"))
                                + (d("L_lid_up", "L_lid_lo") / d("L_ex", "L_en"))) / 2,
        "canthal_tilt_deg": (tilt("R_en", "R_ex", "R") + tilt("L_en", "L_ex", "L")) / 2,
        "alar_to_intercanthal": alar / icd,
        "nose_length_to_face_height": vert("nasion", "subnasale") / fh,
        "mouth_width_to_ipd": mouth / ipd,
        "mouth_to_alar_width": mouth / alar,
        "upper_lip_height": vert("labrale_sup", "stomion_up") / fh,
        "lower_lip_height": vert("stomion_lo", "labrale_inf") / fh,
        "philtrum_to_face_height": vert("subnasale", "labrale_sup") / fh,
        "stomion_position": vert("subnasale", "stomion_up") / vert("subnasale", "menton"),
    }
    m["lip_ratio"] = m["upper_lip_height"] / max(m["lower_lip_height"], 1e-6)

    # Iris diameter from the iris ring landmarks (horizontal pair 0/2 of each ring).
    def iris_d(ring):
        return float(np.linalg.norm(P(ring[0]) - P(ring[2])))
    m["iris_to_eye_width"] = ((iris_d(R_IRIS_RING) / d("R_ex", "R_en")) + (iris_d(L_IRIS_RING) / d("L_ex", "L_en"))) / 2

    # Brows: lower edge polyline, ordered outer -> inner.
    def brow(lower, lid, side):
        pts = np.array([P(i) for i in lower])
        outer, inner = pts[0], pts[-1]
        length = float(np.linalg.norm(outer - inner))
        chord = inner - outer
        normal = np.array([chord[1], -chord[0]]) / (length + 1e-9)
        if normal[1] > 0:
            normal = -normal  # point upwards in the image
        arch = float(np.max((pts - outer) @ normal)) / length
        mid = pts[len(pts) // 2]
        height = float(P(lid)[1] - mid[1]) / ipd
        v = outer - inner
        if side == "R":
            v = -v
        tilt_deg = math.degrees(math.atan2(-v[1], v[0]))
        return height, arch, tilt_deg
    hr, ar, tr = brow(R_BROW_LOWER, "R_lid_up", "R")
    hl, al, tl = brow(L_BROW_LOWER, "L_lid_up", "L")
    m["brow_height_to_ipd"] = (hr + hl) / 2
    m["brow_arch"] = (ar + al) / 2
    m["brow_tilt_deg"] = (tr + tl) / 2

    def angle_at(a, b, c):
        v1, v2 = P(a) - P(b), P(c) - P(b)
        return math.degrees(math.acos(np.clip(v1 @ v2 / (np.linalg.norm(v1) * np.linalg.norm(v2)), -1, 1)))
    m["jaw_angle_deg"] = (angle_at("R_zy", "R_go", "menton") + angle_at("L_zy", "L_go", "menton")) / 2
    return m


def silhouette_metrics(mask: np.ndarray, menton_y: float, nasion_y: float) -> dict[str, float]:
    """Head width/height from the frontal silhouette (only meaningful without bulky hair)."""
    rows = np.where(mask.any(axis=1))[0]
    if rows.size == 0:
        return {}
    vertex = rows[0]
    y = int(round((vertex + nasion_y) / 2))
    xs = np.flatnonzero(mask[y])
    if xs.size == 0 or menton_y <= vertex:
        return {}
    return {"head_width_to_height": float(xs[-1] - xs[0]) / float(menton_y - vertex)}


def asymmetry(obs_points: np.ndarray) -> dict:
    """Bilateral asymmetry in a frontal view, in units of IPD.

    Fits the facial midline to the midline landmarks, mirrors the subject's left
    landmarks across it and measures how far they land from their right
    counterparts.  Values below ~0.02 IPD are within landmark noise.
    """
    p = _rotate_upright(np.asarray(obs_points, dtype=float))[:, :2]
    ipd = float(np.linalg.norm(p[IDX["R_iris"]] - p[IDX["L_iris"]]))
    mid = p[list(MIDLINE)]
    # Midline x = a*y + b
    A = np.vstack([mid[:, 1], np.ones(len(mid))]).T
    a, b = np.linalg.lstsq(A, mid[:, 0], rcond=None)[0]
    n = np.array([1.0, -a]) / math.hypot(1.0, a)

    def reflect(q):
        dist = (q[0] - a * q[1] - b) / math.hypot(1.0, a)  # signed distance from x - a*y - b = 0
        return q - 2 * dist * n

    regions = {}
    for region, pairs in SYMMETRY_PAIRS.items():
        errs = [float(np.linalg.norm(reflect(p[l]) - p[r])) / ipd for r, l in pairs]
        regions[region] = round(float(np.mean(errs)), 4)
    out = {
        "regions_ipd": regions,
        "overall_ipd": round(float(np.mean(list(regions.values()))), 4),
        "eye_height_diff_ipd": round(float(p[IDX["L_iris"], 1] - p[IDX["R_iris"], 1]) / ipd, 4),
        "mouth_corner_height_diff_ipd": round(float(p[IDX["L_ch"], 1] - p[IDX["R_ch"], 1]) / ipd, 4),
        "nose_tip_offset_ipd": round(float((p[IDX["pronasale"], 0] - (a * p[IDX["pronasale"], 1] + b))) / ipd, 4),
        "chin_offset_ipd": round(float((p[IDX["menton"], 0] - (a * p[IDX["menton"], 1] + b))) / ipd, 4),
        "note": "positive offsets = towards image right (subject's left); differences < 0.02 IPD are within noise",
    }
    return out


def procrustes_align(src: np.ndarray, dst: np.ndarray) -> np.ndarray:
    """Similarity-align 3D landmark set src onto dst (Umeyama); returns transformed src."""
    mu_s, mu_d = src.mean(0), dst.mean(0)
    s0, d0 = src - mu_s, dst - mu_d
    cov = d0.T @ s0 / len(src)
    U, S, Vt = np.linalg.svd(cov)
    D = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        D[2, 2] = -1
    R = U @ D @ Vt
    scale = np.trace(np.diag(S) @ D) / (s0 ** 2).sum(1).mean()
    return (scale * (R @ s0.T)).T + mu_d


def frontalized_metrics(obs: FaceObservation, reference: FaceObservation) -> dict[str, float]:
    """Frontal metrics of a turned view after rigidly aligning its 3D landmarks to a frontal view.

    MediaPipe's depth for hidden parts is a learned prior, so these values are
    used to check consistency, not as primary measurements.
    """
    aligned = procrustes_align(obs.points, reference.points)
    return frontal_metrics(aligned)
