"""Cross-view checks: duplicated/mirrored views, measurement agreement, reliability.

Reference sheets (especially AI-generated ones) often contain views that are
not independent evidence: a profile that is the mirror image of the other
profile, or a close-up that is a resampled crop of the front view.  Those must
not be counted as confirmation.  Independent views that disagree beyond a
measurement's tolerance are reported as contradictions instead of averaged away.
"""
from __future__ import annotations

import cv2
import numpy as np

from .measure import METRICS

GRADES = ["unusable", "low", "medium", "high"]


def _norm_crop(gray: np.ndarray, mask: np.ndarray, size=(128, 160)) -> tuple[np.ndarray, np.ndarray]:
    ys, xs = np.where(mask)
    if ys.size == 0:
        return np.zeros(size[::-1], np.float32), np.zeros(size[::-1], bool)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    g = cv2.resize(gray[y0:y1, x0:x1].astype(np.float32), size, interpolation=cv2.INTER_AREA)
    m = cv2.resize(mask[y0:y1, x0:x1].astype(np.uint8), size, interpolation=cv2.INTER_NEAREST).astype(bool)
    return g, m


def mirror_similarity(img_a: np.ndarray, mask_a: np.ndarray, img_b: np.ndarray, mask_b: np.ndarray) -> dict:
    """Similarity between view A and the horizontally flipped view B.

    Returns silhouette IoU and normalised cross-correlation of the grey images
    inside the shared silhouette.  Two genuinely independent photos of a
    person's left and right side differ in asymmetry, lighting and pose; near
    pixel-identical results (ncc > ~0.97 with IoU > ~0.97) mean B was made by
    mirroring A.
    """
    ga, ma = _norm_crop(cv2.cvtColor(img_a, cv2.COLOR_RGB2GRAY), mask_a)
    gb, mb = _norm_crop(cv2.cvtColor(img_b, cv2.COLOR_RGB2GRAY)[:, ::-1], mask_b[:, ::-1])
    both = ma & mb
    iou = float(both.sum()) / max(1, int((ma | mb).sum()))
    if both.sum() < 50:
        return {"iou": round(iou, 3), "ncc": 0.0}
    # Correlate fine structure, not overall shading: subtract a blurred version.
    fa = ga - cv2.GaussianBlur(ga, (0, 0), 3)
    fb = gb - cv2.GaussianBlur(gb, (0, 0), 3)
    a, b = fa[both], fb[both]
    a, b = a - a.mean(), b - b.mean()
    ncc = float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))
    return {"iou": round(iou, 3), "ncc": round(ncc, 3)}


def resample_similarity(img_a: np.ndarray, pts_a: np.ndarray, img_b: np.ndarray, pts_b: np.ndarray) -> float:
    """NCC of fine detail after warping B onto A with a landmark similarity transform.

    High values (> ~0.9) mean B is a resampled copy of A (e.g. a close-up cut
    from the front photo) rather than a separate photograph.
    """
    M, _ = cv2.estimateAffinePartial2D(pts_b[:468, :2].astype(np.float32), pts_a[:468, :2].astype(np.float32))
    if M is None:
        return 0.0
    ga = cv2.cvtColor(img_a, cv2.COLOR_RGB2GRAY).astype(np.float32)
    gb = cv2.warpAffine(cv2.cvtColor(img_b, cv2.COLOR_RGB2GRAY).astype(np.float32), M, (img_a.shape[1], img_a.shape[0]))
    hull = cv2.convexHull(pts_a[:468, :2].astype(np.int32))
    mask = np.zeros(ga.shape, np.uint8)
    cv2.fillConvexPoly(mask, hull, 1)
    mask = mask.astype(bool) & (gb > 0)
    fa = ga - cv2.GaussianBlur(ga, (0, 0), 2)
    fb = gb - cv2.GaussianBlur(gb, (0, 0), 2)
    a, b = fa[mask], fb[mask]
    if a.size < 100:
        return 0.0
    a, b = a - a.mean(), b - b.mean()
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def spread(values: list[float], unit: str) -> float:
    """Disagreement between views: relative range for ratios, absolute range for angles."""
    if len(values) < 2:
        return 0.0
    rng = max(values) - min(values)
    if unit == "deg":
        return float(rng)
    return float(rng / max(1e-9, abs(np.mean(values))))


def combine(name: str, per_view: dict[str, float], independent_groups: list[set[str]],
            primary_views: set[str], check_views: set[str]) -> dict:
    """Combine one measurement across views and grade its reliability.

    per_view: view label -> value.  primary_views contribute to the value;
    check_views (e.g. frontalised 3/4 views) only test agreement.
    independent_groups: sets of view labels that are copies of each other
    (counted once).
    """
    d = METRICS[name]
    prim = {v: x for v, x in per_view.items() if v in primary_views}
    if not prim:
        return {"value": None, "reliability": "unusable", "reasons": ["no usable view"], "per_view": per_view}
    value = float(np.median(list(prim.values())))

    def n_independent(views):
        seen = set()
        count = 0
        for v in views:
            group = next((g for g in independent_groups if v in g), {v})
            key = frozenset(group)
            if key not in seen:
                seen.add(key)
                count += 1
        return count
    n_ind = n_independent(prim)
    reasons = []
    grade = GRADES.index(d.base)
    sp_prim = spread(list(prim.values()), d.unit)
    checks = {v: x for v, x in per_view.items() if v in check_views}
    sp_all = spread(list(prim.values()) + list(checks.values()), d.unit)
    if n_ind < 2:
        grade = min(grade, GRADES.index("medium"))
        reasons.append("only one independent view")
    contradiction = None
    if sp_prim > 2 * d.tolerance:
        grade = min(grade, GRADES.index("low"))
        contradiction = "primary views disagree"
    elif sp_prim > d.tolerance:
        grade = max(1, grade - 1)
        reasons.append(f"primary views differ by {sp_prim:.3g} (tolerance {d.tolerance})")
    if checks and sp_all > 2 * d.tolerance and contradiction is None:
        grade = max(1, grade - 1)
        contradiction = "turned views disagree with frontal value"
    if contradiction:
        reasons.append(contradiction)
    noise_floor = d.tolerance / 2 * (abs(value) if d.unit == "ratio" else 1.0)
    sd = float(np.std(list(prim.values()))) if len(prim) > 1 else 0.0
    return {"value": round(value, 4), "unit": d.unit, "region": d.region,
            "reliability": GRADES[grade], "uncertainty": round(max(sd, noise_floor), 4),
            "independent_views": n_ind, "spread_primary": round(sp_prim, 4),
            "spread_all": round(sp_all, 4), "per_view": {k: round(v, 4) for k, v in per_view.items()},
            "contradiction": contradiction, "reasons": reasons}
