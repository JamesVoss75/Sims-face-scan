"""Colour and texture descriptors: skin tone, eye colour, brow and lip colour, freckles.

Colours are robust medians in CIELAB over landmark-defined patches.  They
depend on lighting and white balance, so they are reported with that caveat
and are meant for picking the nearest existing CAS skin tone / eye colour, not
as absolute truth.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

from .landmarks import IDX, L_BROW_LOWER, L_BROW_UPPER, L_IRIS_RING, R_BROW_LOWER, R_BROW_UPPER, R_IRIS_RING


def _lab(rgb: np.ndarray) -> np.ndarray:
    """CIELAB with L in 0..100 and a, b signed (float)."""
    lab = cv2.cvtColor(rgb.astype(np.float32) / 255.0, cv2.COLOR_RGB2LAB)
    return lab


def _hex(lab_px: np.ndarray) -> str:
    rgb = cv2.cvtColor(lab_px.reshape(1, 1, 3).astype(np.float32), cv2.COLOR_LAB2RGB).reshape(3)
    r, g, b = (np.clip(rgb, 0, 1) * 255).round().astype(int)
    return f"#{r:02X}{g:02X}{b:02X}"


def _summary(samples: np.ndarray) -> dict | None:
    if samples.shape[0] < 10:
        return None
    med = np.median(samples, axis=0)
    L, a, b = (float(x) for x in med)
    return {"lab": [round(L, 1), round(a, 1), round(b, 1)], "hex": _hex(med),
            "chroma": round(math.hypot(a, b), 1), "hue_deg": round(math.degrees(math.atan2(b, a)) % 360, 1),
            "n_pixels": int(samples.shape[0])}


def _disc(shape, centre, radius) -> np.ndarray:
    yy, xx = np.mgrid[: shape[0], : shape[1]]
    return (xx - centre[0]) ** 2 + (yy - centre[1]) ** 2 <= radius ** 2


def skin(rgb: np.ndarray, pts: np.ndarray) -> dict:
    lab = _lab(rgb)
    ipd = float(np.linalg.norm(pts[IDX["R_iris"], :2] - pts[IDX["L_iris"], :2]))
    mask = np.zeros(rgb.shape[:2], bool)
    for k, r in (("R_cheek", 0.16), ("L_cheek", 0.16), ("forehead", 0.14)):
        mask |= _disc(rgb.shape, pts[IDX[k], :2], r * ipd)
    s = lab[mask]
    # Drop specular highlights and dark spots (freckles, moles) for the base tone.
    lo, hi = np.percentile(s[:, 0], [15, 90])
    s = s[(s[:, 0] >= lo) & (s[:, 0] <= hi)]
    out = _summary(s) or {}
    if out:
        L, _, b = out["lab"]
        ita = math.degrees(math.atan2(L - 50.0, b))  # Individual Typology Angle (Chardon et al.)
        out["ita_deg"] = round(ita, 1)
        out["ita_category"] = ("very light" if ita > 55 else "light" if ita > 41 else "intermediate" if ita > 28
                               else "tan" if ita > 10 else "brown" if ita > -30 else "dark")
    return out


def eye_colour(rgb: np.ndarray, pts: np.ndarray) -> dict:
    lab = _lab(rgb)
    samples = []
    for centre_idx, ring in ((IDX["R_iris"], R_IRIS_RING), (IDX["L_iris"], L_IRIS_RING)):
        c = pts[centre_idx, :2]
        r = float(np.mean([np.linalg.norm(pts[i, :2] - c) for i in ring]))
        if r < 3:
            continue
        ann = _disc(rgb.shape, c, 0.9 * r) & ~_disc(rgb.shape, c, 0.45 * r)
        # Exclude eyelid occlusion (keep the band between the lids) and highlights.
        s = lab[ann]
        if s.size == 0:
            continue
        lo, hi = np.percentile(s[:, 0], [10, 85])
        samples.append(s[(s[:, 0] >= lo) & (s[:, 0] <= hi)])
    if not samples:
        return {}
    out = _summary(np.concatenate(samples)) or {}
    if out:
        L, a, b = out["lab"]
        hue, chroma = out["hue_deg"], out["chroma"]
        if chroma < 8 and L > 45:
            cat = "grey"
        elif b < 0 or (hue > 200 and hue < 300):
            cat = "blue" if L > 35 else "dark blue"
        elif chroma < 12 and L > 40:
            cat = "grey-green" if a < 0 else "grey"
        elif a < 2 and b > 8:
            cat = "green/hazel"
        elif L < 30:
            cat = "dark brown"
        else:
            cat = "brown" if a > 4 else "hazel"
        out["category"] = cat
    return out


def brow_colour(rgb: np.ndarray, pts: np.ndarray, skin_L: float | None) -> dict:
    lab = _lab(rgb)
    mask = np.zeros(rgb.shape[:2], np.uint8)
    for upper, lower in ((R_BROW_UPPER, R_BROW_LOWER), (L_BROW_UPPER, L_BROW_LOWER)):
        poly = np.array([pts[i, :2] for i in upper] + [pts[i, :2] for i in lower], np.int32)
        cv2.fillPoly(mask, [poly], 1)
    s = lab[mask.astype(bool)]
    if skin_L is not None and s.size:
        s = s[s[:, 0] < skin_L - 6]  # hair pixels are darker than skin
    out = _summary(s) or {}
    if out:
        out["density"] = round(float(s.shape[0]) / max(1, int(mask.sum())), 2)
        hue, L = out["hue_deg"], out["lab"][0]
        # Descriptive only (nearest CAS swatch uses Lab distance): strongly coloured warm hair = red/auburn.
        out["category"] = ("red/auburn" if out["chroma"] > 27 and hue < 60 else "blonde" if L > 60
                           else "light brown" if L > 45 else "brown" if L > 28 else "dark brown/black")
    return out


def lip_colour(rgb: np.ndarray, pts: np.ndarray) -> dict:
    lab = _lab(rgb)
    ipd = float(np.linalg.norm(pts[IDX["R_iris"], :2] - pts[IDX["L_iris"], :2]))
    up = (pts[IDX["labrale_sup"], :2] + pts[IDX["stomion_up"], :2]) / 2
    lo = (pts[IDX["stomion_lo"], :2] + pts[IDX["labrale_inf"], :2]) / 2
    mask = _disc(rgb.shape, up, 0.04 * ipd) | _disc(rgb.shape, lo, 0.05 * ipd)
    return _summary(lab[mask]) or {}


def freckles(rgb: np.ndarray, pts: np.ndarray) -> dict:
    """Pigmented spots on the cheeks: darker AND more yellow-brown than the local skin.

    Melanin spots raise b* while lowering L*; pores, shading and noise mostly
    only lower L*.  Reports a spot count, density per IPD^2 and the pigmented
    area fraction (more stable than counts).  Resolution- and lighting-
    dependent; needs an IPD of roughly 100 px or more.
    """
    lab = _lab(rgb)
    ipd = float(np.linalg.norm(pts[IDX["R_iris"], :2] - pts[IDX["L_iris"], :2]))
    region = np.zeros(rgb.shape[:2], bool)
    for k in ("R_cheek", "L_cheek"):
        region |= _disc(rgb.shape, pts[IDX[k], :2], 0.28 * ipd)
    if region.sum() < 50:
        return {}
    fine, coarse = max(0.6, 0.004 * ipd), 0.06 * ipd
    resid = [cv2.GaussianBlur(lab[:, :, c], (0, 0), fine) - cv2.GaussianBlur(lab[:, :, c], (0, 0), coarse)
             for c in (0, 2)]
    mad_b = float(np.median(np.abs(resid[1][region]))) * 1.4826
    spot = (resid[1] > max(2.5, 3.0 * mad_b)) & (resid[0] < -1.0) & region
    n, _, stats, _ = cv2.connectedComponentsWithStats(spot.astype(np.uint8))
    min_a, max_a = max(2, (0.006 * ipd) ** 2), (0.06 * ipd) ** 2
    spots = int(sum(1 for i in range(1, n) if min_a <= stats[i, cv2.CC_STAT_AREA] <= max_a))
    area_ipd2 = float(region.sum()) / ipd ** 2
    return {"spots": spots, "density_per_ipd2": round(spots / area_ipd2, 1),
            "pigmented_fraction": round(float(spot.sum()) / float(region.sum()), 4),
            "ipd_px": round(ipd, 1), "resolution_ok": ipd >= 100}


def describe(rgb: np.ndarray, pts: np.ndarray) -> dict:
    s = skin(rgb, pts)
    return {"skin": s, "eyes": eye_colour(rgb, pts),
            "brows": brow_colour(rgb, pts, s.get("lab", [None])[0] if s else None),
            "lips": lip_colour(rgb, pts), "freckles": freckles(rgb, pts),
            "caveat": "colours depend on lighting and white balance of the source image"}
