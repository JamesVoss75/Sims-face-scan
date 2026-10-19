"""Profile (90 degree) analysis from the head silhouette.

MediaPipe's landmarker is unreliable on true profiles: its yaw saturates near
55-60 degrees and it often finds no face at all.  The facial profile line,
however, is directly visible as the silhouette edge.  This module segments
the head from a plain background, extracts the front contour and finds the
classic soft-tissue profile points on it:

    g  glabella        n  nasion         prn pronasale (nose tip)
    sn subnasale       ls labrale sup.   sto stomion
    li labrale inf.    sm mentolabial    pg  pogonion
    me menton (approx) c  cervical point
    v  vertex (top of head)

Limits: needs a reasonably uniform background (confidence is reported) and a
silhouette not covered by hair, glasses or a beard.  All lengths are returned
in pixels; metrics are scale-free.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks


@dataclass
class Segmentation:
    mask: np.ndarray            # bool H x W, True = person
    background_lab: np.ndarray  # median Lab of the border
    background_spread: float    # MAD of border colour distance (low = uniform background)
    confidence: float           # 0..1


def segment_person(rgb: np.ndarray) -> Segmentation:
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    h, w = lab.shape[:2]
    b = max(4, int(0.03 * min(h, w)))
    # Border strips from the upper 60% only: the bottom is usually shoulders.
    border = np.concatenate([lab[:b, :].reshape(-1, 3), lab[: int(0.6 * h), :b].reshape(-1, 3),
                             lab[: int(0.6 * h), -b:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    # Background may have a smooth gradient: model it per row from the side strips.
    side = np.concatenate([lab[:, :b], lab[:, -b:]], axis=1)  # (H, 2b, 3)
    # Per-row background from side pixels that look like background (close in
    # chroma to the border median); rows where the body reaches the edge reuse
    # the nearest row above.
    chroma_ok = np.linalg.norm(side[:, :, 1:] - bg[1:], axis=2) < 6
    row_bg = np.empty((h, 3), np.float32)
    last = bg
    for y in range(h):
        sel = side[y][chroma_ok[y]]
        if sel.shape[0] >= max(3, b // 2):
            last = np.median(sel, axis=0)
        row_bg[y] = last
    dist = np.linalg.norm(lab - row_bg[:, None, :], axis=2)
    border_dist = np.linalg.norm(border - bg, axis=1)
    spread = float(np.median(np.abs(border_dist - np.median(border_dist))) * 1.4826)
    thr = max(10.0, 5.0 * spread + 4.0)
    mask = (dist > thr).astype(np.uint8)
    k = max(3, int(0.006 * min(h, w)) | 1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3 * k, 3 * k), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n <= 1:
        return Segmentation(np.zeros((h, w), bool), bg, spread, 0.0)
    biggest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    mask = labels == biggest
    # Fill holes (eyes, nostrils darker/lighter than skin are still inside).
    filled = mask.astype(np.uint8)
    cnts, _ = cv2.findContours(filled, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(filled, cnts, -1, 1, thickness=cv2.FILLED)
    conf = float(np.clip(1.0 - spread / 12.0, 0.0, 1.0))
    return Segmentation(filled.astype(bool), bg, spread, conf)


def _head_length(mask: np.ndarray) -> tuple[int, float]:
    """Top row of the head and head length L (widest skull row, iterated window)."""
    rows = np.where(mask.any(axis=1))[0]
    y_top = int(rows[0])
    width = np.zeros(mask.shape[0])
    for y in rows:
        xs = np.flatnonzero(mask[y])
        width[y] = xs[-1] - xs[0]
    L = 0.5 * mask.shape[0]
    for _ in range(5):
        y1 = min(mask.shape[0], int(y_top + 0.8 * L))
        if y1 > y_top + 2:
            L = float(width[y_top:y1].max())
    return y_top, L


def facing_direction(mask: np.ndarray) -> tuple[str, float]:
    """'left' or 'right' (where the nose points in the image) and a margin in [0, 1].

    The nose is a sharp, local outward spike on the face side of a profile
    silhouette; the back of the skull is smooth.  Compare the largest local
    outward deviation of the two side contours over the head region only.
    """
    if mask.sum() < 100:
        return "unknown", 0.0
    y_top, L = _head_length(mask)
    ys = np.arange(int(y_top + 0.35 * L), min(mask.shape[0], int(y_top + 1.05 * L)))
    ys = ys[[mask[y].any() for y in ys]]
    if ys.size < 20:
        return "unknown", 0.0
    left = np.array([np.argmax(mask[y]) for y in ys], dtype=float)
    right = np.array([mask.shape[1] - 1 - np.argmax(mask[y][::-1]) for y in ys], dtype=float)

    def spike(outward):
        smooth = gaussian_filter1d(outward, sigma=max(3.0, 0.06 * L))
        return float(np.max(outward - smooth))
    sl, sr = spike(-left), spike(right)
    if max(sl, sr) <= 0:
        return "unknown", 0.0
    return ("left" if sl > sr else "right"), abs(sl - sr) / max(sl, sr)


@dataclass
class ProfileResult:
    facing: str
    points: dict = field(default_factory=dict)   # name -> (x, y) in panel pixels
    contour: np.ndarray | None = None            # (K, 2) front contour, panel pixels
    metrics: dict = field(default_factory=dict)
    confidence: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    head_length_px: float = 0.0


def _angle(a, b, c) -> float:
    """Angle ABC in degrees."""
    v1, v2 = np.asarray(a) - np.asarray(b), np.asarray(c) - np.asarray(b)
    cosv = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9)
    return math.degrees(math.acos(float(np.clip(cosv, -1, 1))))


def _signed_dist(p, a, b) -> float:
    """Signed perpendicular distance of p from line a->b (positive = forward side, x+)."""
    a, b, p = map(np.asarray, (a, b, p))
    d = b - a
    n = np.array([d[1], -d[0]]) / (np.linalg.norm(d) + 1e-9)
    if n[0] < 0:
        n = -n
    return float(np.dot(p - a, n))


def analyze_profile(rgb: np.ndarray, facing: str | None = None) -> ProfileResult:
    seg = segment_person(rgb)
    mask = seg.mask
    if facing is None or facing == "unknown":
        facing, _ = facing_direction(mask)
    res = ProfileResult(facing=facing)
    if facing not in ("left", "right") or not mask.any():
        res.warnings.append("could not determine profile direction or segment the head")
        return res
    w = mask.shape[1]
    m = mask[:, ::-1] if facing == "left" else mask  # canonical: face points to +x

    rows = np.where(m.any(axis=1))[0]
    y_top, L = _head_length(m)
    front = np.full(m.shape[0], np.nan)
    for y in rows:
        front[y] = np.flatnonzero(m[y])[-1]
    res.head_length_px = L

    f = front.copy()
    valid = ~np.isnan(f)
    f[~valid] = np.interp(np.flatnonzero(~valid), np.flatnonzero(valid), f[valid]) if valid.any() else 0
    fs = gaussian_filter1d(f, sigma=max(1.0, 0.004 * L))

    def win(a, b):
        a, b = int(max(y_top, a)), int(min(len(fs) - 1, b))
        return a, b

    def argmax_in(a, b):
        a, b = win(a, b)
        return a + int(np.argmax(fs[a:b + 1])) if b > a else None

    def argmin_in(a, b):
        a, b = win(a, b)
        return a + int(np.argmin(fs[a:b + 1])) if b > a else None

    pts: dict[str, tuple[float, float]] = {}
    conf: dict[str, str] = {}

    def put(name, y, c="high"):
        if y is not None:
            pts[name] = (float(fs[y]), float(y))
            conf[name] = c

    put("v", y_top, "medium")
    y_prn = argmax_in(y_top + 0.55 * L, y_top + 1.05 * L)
    put("prn", y_prn)
    if y_prn is None:
        res.warnings.append("nose tip not found")
        return res

    def deepest_below_chord(ya, yb):
        """Row in (ya, yb) whose contour lies furthest behind the chord between the two rows."""
        ys = np.arange(ya + 1, yb)
        if ys.size == 0:
            return None
        chord = fs[ya] + (fs[yb] - fs[ya]) * (ys - ya) / (yb - ya)
        return int(ys[np.argmax(chord - fs[ys])])

    # Nasion: deepest concavity between the forehead and the nose tip; glabella:
    # most forward point just above it; then refine nasion against the g-prn chord.
    y_fh = int(max(y_top, y_prn - 0.5 * L))
    y_n = deepest_below_chord(y_fh, y_prn)
    y_g = argmax_in(y_n - 0.22 * L, y_n - 0.01 * L) if y_n is not None else None
    if y_g is not None:
        y_n = deepest_below_chord(y_g, y_prn) or y_n
    put("n", y_n)
    put("g", y_g)

    def most_forward_of_chord(ya, yb):
        ys = np.arange(ya + 1, yb)
        if ys.size == 0:
            return None
        chord = fs[ya] + (fs[yb] - fs[ya]) * (ys - ya) / (yb - ya)
        return int(ys[np.argmax(fs[ys] - chord)])

    # Chin underside = steepest backward run of the outline below the mouth;
    # menton = convex corner above it; cervical point = deepest neck point below.
    a0, b0 = win(y_prn + 0.25 * L, y_prn + 0.8 * L)
    grad = np.gradient(fs)
    y_under = a0 + int(np.argmin(grad[a0:b0 + 1])) if b0 > a0 else None
    if y_under is None:
        res.warnings.append("chin underside not found")
    else:
        y_me = most_forward_of_chord(*win(y_under - 0.18 * L, y_under + 0.02 * L))
        y_c = argmin_in(y_under, y_under + 0.35 * L)
        put("me", y_me, "medium")
        put("c", y_c, "medium")
        # Lips: the first two forward bumps below the nose tip (upper, lower lip).
        a1, b1 = win(y_prn + 0.03 * L, (y_me or y_under) - 0.04 * L)
        peaks, _ = find_peaks(fs[a1:b1 + 1], prominence=0.003 * L)
        peaks = list(peaks + a1)
        if len(peaks) >= 2 and peaks[1] - peaks[0] <= 0.14 * L:  # lips are close together
            y_ls, y_li = peaks[0], peaks[1]
        elif len(peaks) >= 2:
            y_ls, y_li = peaks[0], None
            res.warnings.append("lower lip not a separate contour bump; lower lip not located")
        elif len(peaks) == 1:
            y_ls, y_li = peaks[0], None
            res.warnings.append("only one lip contour bump found; lower lip not located")
        else:
            y_ls = y_li = None
            res.warnings.append("lip contour bumps not found")
        if y_ls is not None:
            put("ls", y_ls)
            put("sn", deepest_below_chord(y_prn, y_ls))
        if y_li is not None:
            put("li", y_li)
            put("sto", argmin_in(y_ls, y_li))
        if y_me is not None:
            start = y_li if y_li is not None else y_ls
            if start is not None:
                y_sm = deepest_below_chord(start, y_me)
                put("sm", y_sm, "medium")
                if y_sm is not None:
                    put("pg", most_forward_of_chord(y_sm, y_me))

    # Points where the silhouette touches the image border are cut off by the
    # crop, not real anatomy: downgrade them and say so.
    clipped = (m.shape[1] - 1 - front) <= 1.5
    for name, (x, y) in list(pts.items()):
        lo, hi = int(max(0, y - 0.03 * L)), int(min(len(clipped), y + 0.03 * L + 1))
        if np.any(clipped[lo:hi]):
            conf[name] = "unusable"
            res.warnings.append(f"{name}: face outline touches the image border here (cropped view)")

    # Map back to panel coordinates.
    def to_panel(x, y):
        return ((w - 1 - x) if facing == "left" else x, y)
    contour_ys = np.arange(y_top, int(pts.get("c", pts.get("pg", (0, y_prn + 0.7 * L)))[1]) + 1)
    res.contour = np.array([to_panel(fs[y], y) for y in contour_ys])
    res.points = {k: to_panel(*v) for k, v in pts.items()}
    res.confidence = conf
    res.metrics = profile_metrics({k: v for k, v in pts.items() if conf.get(k) != "unusable"}, L)
    if seg.confidence < 0.6:
        res.warnings.append(f"background not uniform (spread {seg.background_spread:.1f}); silhouette may be inaccurate")
    res.metrics["_segmentation_confidence"] = seg.confidence
    return res


def profile_metrics(p: dict, L: float) -> dict:
    """Scale-free profile measurements in the canonical (face points +x) frame."""
    m: dict[str, float] = {}
    need = lambda *k: all(x in p for x in k)  # noqa: E731
    if need("n", "me"):
        axis = np.array(p["me"]) - np.array(p["n"])
        fh = float(np.linalg.norm(axis))
        u = axis / fh

        def along(a, b):
            return float(np.dot(np.array(p[b]) - np.array(p[a]), u))
        m["face_height_px"] = fh
        if "sn" in p:
            m["midface_ratio"] = along("n", "sn") / fh
            m["lower_face_ratio"] = along("sn", "me") / fh
        if need("sn", "sto"):
            m["upper_lip_to_lower_face"] = along("sn", "sto") / along("sn", "me")
        if "v" in p:
            m["head_height_to_length"] = along("v", "me") / L
            m["forehead_height_ratio"] = along("v", "n") / fh
        if need("n", "prn", "sn"):
            nasal_len = float(np.linalg.norm(np.array(p["prn"]) - np.array(p["n"])))
            m["nasal_length_ratio"] = nasal_len / fh
            m["nasal_tip_projection"] = _signed_dist(p["prn"], p["n"], p["sn"]) / nasal_len
        if need("pg",):
            m["chin_projection"] = _signed_dist(p["pg"], p["n"], p["me"]) / fh
    if need("g", "n", "prn"):
        m["nasofrontal_angle_deg"] = _angle(p["g"], p["n"], p["prn"])
    if need("prn", "sn", "ls"):
        m["nasolabial_angle_deg"] = _angle(p["prn"], p["sn"], p["ls"])
    if need("g", "sn", "pg"):
        m["facial_convexity_deg"] = 180.0 - _angle(p["g"], p["sn"], p["pg"])
    if need("prn", "pg", "n", "me"):
        fh = m.get("face_height_px", 1.0)
        for k, name in (("ls", "upper_lip_to_eline"), ("li", "lower_lip_to_eline")):
            if k in p:
                m[name] = _signed_dist(p[k], p["prn"], p["pg"]) / fh
    if need("pg", "me", "c"):
        m["chin_throat_angle_deg"] = _angle(p["pg"], p["me"], p["c"])
    return m
