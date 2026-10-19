"""Annotated diagnostic images: landmarks and the measurements computed from them."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .landmarks import IDX, L_BROW_LOWER, R_BROW_LOWER

COLOURS = {
    "ipd": (0, 200, 255), "intercanthal": (40, 90, 255), "eye": (0, 200, 90), "bizygomatic": (255, 210, 0),
    "bigonial": (255, 130, 0), "mouth": (230, 0, 200), "alar": (255, 40, 40), "chin": (150, 90, 40),
    "vertical": (255, 255, 255), "brow": (120, 255, 120), "profile": (255, 40, 40), "eline": (0, 220, 255),
    "angle": (255, 220, 0), "landmark": (180, 180, 180), "bad": (255, 0, 0),
}


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _line(d, a, b, colour, w=2):
    d.line([tuple(map(float, a)), tuple(map(float, b))], fill=colour, width=w)


def _dot(d, p, colour, r=3):
    x, y = map(float, p)
    d.ellipse([x - r, y - r, x + r, y + r], fill=colour)


def _label(d, p, text, colour, font):
    x, y = map(float, p)
    d.text((x + 1, y + 1), text, fill=(0, 0, 0), font=font)
    d.text((x, y), text, fill=colour, font=font)


def annotate_frontal(rgb: np.ndarray, pts: np.ndarray, metrics: dict, scale: float = 2.0) -> Image.Image:
    im = Image.fromarray(rgb).resize((int(rgb.shape[1] * scale), int(rgb.shape[0] * scale)), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    f = _font(int(11 * scale / 1.5))
    P = lambda k: pts[IDX[k] if isinstance(k, str) else k, :2] * scale  # noqa: E731
    for q in pts[:468, :2] * scale:
        _dot(d, q, COLOURS["landmark"], r=1)
    _line(d, P("R_zy"), P("L_zy"), COLOURS["bizygomatic"])
    _line(d, P("R_go"), P("L_go"), COLOURS["bigonial"])
    _line(d, P("R_chin"), P("L_chin"), COLOURS["chin"])
    _line(d, P("R_iris"), P("L_iris"), COLOURS["ipd"])
    _line(d, P("R_en"), P("L_en"), COLOURS["intercanthal"])
    _line(d, P("R_ex"), P("R_en"), COLOURS["eye"], 3)
    _line(d, P("L_en"), P("L_ex"), COLOURS["eye"], 3)
    _line(d, P("R_al"), P("L_al"), COLOURS["alar"])
    _line(d, P("R_ch"), P("L_ch"), COLOURS["mouth"])
    for brow in (R_BROW_LOWER, L_BROW_LOWER):
        d.line([tuple(P(i)) for i in brow], fill=COLOURS["brow"], width=2)
    # Vertical axis with tick labels.
    xs = max(P("L_zy")[0], P("R_zy")[0]) + 12 * scale  # axis beside the face
    for k, name in (("nasion", "n"), ("subnasale", "sn"), ("stomion_up", "sto"), ("menton", "me")):
        y = P(k)[1]
        _line(d, (P(k)[0], y), (xs, y), COLOURS["vertical"], 1)
        _label(d, (xs + 4, y - 7), name, COLOURS["vertical"], f)
    _line(d, (xs, P("nasion")[1]), (xs, P("menton")[1]), COLOURS["vertical"], 2)
    for k in ("nasion", "subnasale", "stomion_up", "menton", "R_go", "L_go", "R_zy", "L_zy"):
        _dot(d, P(k), (255, 255, 255), r=3)
    legend = [("IPD", "ipd"), ("intercanthal", "intercanthal"), ("eye width", "eye"), ("cheek width", "bizygomatic"),
              ("jaw width", "bigonial"), ("chin width", "chin"), ("nose width", "alar"), ("mouth width", "mouth"),
              ("brow edge", "brow")]
    y = 6
    for text, key in legend:
        d.rectangle([6, y + 3, 18, y + 11], fill=COLOURS[key])
        _label(d, (22, y), text, (255, 255, 255), f)
        y += int(14 * scale / 1.5)
    if metrics:
        lines = [f"{k}: {v:.3f}" for k, v in metrics.items()]
        y = im.height - 6 - len(lines) * int(13 * scale / 1.5)
        for t in lines:
            _label(d, (6, y), t, (255, 255, 255), f)
            y += int(13 * scale / 1.5)
    return im


def annotate_turned(rgb: np.ndarray, pts: np.ndarray, text: str, scale: float = 2.0) -> Image.Image:
    im = Image.fromarray(rgb).resize((int(rgb.shape[1] * scale), int(rgb.shape[0] * scale)), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    f = _font(int(11 * scale / 1.5))
    for q in pts[:468, :2] * scale:
        _dot(d, q, COLOURS["landmark"], r=1)
    for k in ("nasion", "subnasale", "stomion_up", "menton", "R_ch", "L_ch", "R_al", "L_al"):
        _dot(d, pts[IDX[k], :2] * scale, (255, 255, 255), r=3)
    _label(d, (6, 6), text, (255, 255, 255), f)
    return im


def annotate_profile(rgb: np.ndarray, result, scale: float = 2.0) -> Image.Image:
    im = Image.fromarray(rgb).resize((int(rgb.shape[1] * scale), int(rgb.shape[0] * scale)), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    f = _font(int(11 * scale / 1.5))
    if result.contour is not None and len(result.contour) > 1:
        d.line([tuple(p * scale) for p in result.contour], fill=COLOURS["profile"], width=2)
    P = {k: np.array(v) * scale for k, v in result.points.items()}
    if "n" in P and "me" in P:
        _line(d, P["n"], P["me"], COLOURS["vertical"], 1)
    if "prn" in P and "pg" in P:
        a, b = P["prn"], P["pg"]
        ext = (b - a) * 0.25
        _line(d, a - ext, b + ext, COLOURS["eline"], 1)
    for a, b, c in (("g", "n", "prn"), ("prn", "sn", "ls")):
        if a in P and b in P and c in P:
            _line(d, P[b], P[a], COLOURS["angle"], 1)
            _line(d, P[b], P[c], COLOURS["angle"], 1)
    for k, p in P.items():
        bad = result.confidence.get(k) == "unusable"
        colour = COLOURS["bad"] if bad else (255, 255, 255)
        if bad:
            x, y = p
            d.line([x - 5, y - 5, x + 5, y + 5], fill=colour, width=2)
            d.line([x - 5, y + 5, x + 5, y - 5], fill=colour, width=2)
        else:
            _dot(d, p, colour, r=3)
        dx = 8 if result.facing == "right" else -8 - 7 * len(k)
        _label(d, (p[0] + dx, p[1] - 7), k, colour, f)
    lines = [f"{k}: {v:.3f}" for k, v in result.metrics.items() if not k.startswith("_") and not k.endswith("_px")]
    x0 = 6 if result.facing == "right" else im.width // 2
    y = im.height - 6 - len(lines) * int(13 * scale / 1.5)
    for t in lines:
        _label(d, (x0, y), t, (255, 255, 255), f)
        y += int(13 * scale / 1.5)
    for k, w in enumerate(result.warnings[:4]):
        _label(d, (6, 6 + k * int(13 * scale / 1.5)), w[:70], (255, 120, 120), f)
    return im


def contact_sheet(tiles: list[tuple[str, Image.Image]], cols: int = 3, width: int = 520, title: str = "") -> Image.Image:
    f = _font(16)
    scaled = [(t, im.resize((width, int(im.height * width / im.width)), Image.LANCZOS)) for t, im in tiles]
    rows = (len(scaled) + cols - 1) // cols
    row_h = [max(im.height for _, im in scaled[r * cols:(r + 1) * cols]) + 26 for r in range(rows)]
    head = 34 if title else 0
    sheet = Image.new("RGB", (cols * width + (cols + 1) * 6, head + sum(row_h) + 6), (30, 30, 30))
    d = ImageDraw.Draw(sheet)
    if title:
        d.text((8, 8), title, fill=(255, 255, 255), font=_font(20))
    y = head
    for r in range(rows):
        for c in range(cols):
            k = r * cols + c
            if k >= len(scaled):
                break
            text, im = scaled[k]
            x = 6 + c * (width + 6)
            d.text((x, y + 4), text, fill=(255, 255, 255), font=f)
            sheet.paste(im, (x, y + 24))
        y += row_h[r]
    return sheet
