"""Split a multi-view reference sheet into its photo panels.

Panels are found from the near-white gutters and caption bands between them,
so no fixed layout is assumed.  Captions are not read: each panel's view is
later determined from the measured head pose, because a sheet's labels may be
wrong.  An image without detectable gutters is treated as a single photo.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Panel:
    index: int
    bbox: tuple[int, int, int, int]  # x0, y0, x1, y1 in sheet pixels
    image: np.ndarray                # H x W x 3 uint8 RGB


def _runs(flags: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    """Runs of False (content) between True (gutter) entries."""
    runs, start = [], None
    for i, g in enumerate(flags):
        if not g and start is None:
            start = i
        elif g and start is not None:
            if i - start >= min_len:
                runs.append((start, i))
            start = None
    if start is not None and len(flags) - start >= min_len:
        runs.append((start, len(flags)))
    return runs


def split_sheet(rgb: np.ndarray, white_level: int = 235, gutter_fraction: float = 0.8,
                min_panel_fraction: float = 0.12) -> list[Panel]:
    """Return panels in reading order (row by row, left to right)."""
    h, w = rgb.shape[:2]
    near_white = (rgb.min(axis=2) >= white_level) & ((rgb.max(axis=2).astype(int) - rgb.min(axis=2)) < 25)
    row_gutter = near_white.mean(axis=1) > gutter_fraction
    panels: list[Panel] = []
    for y0, y1 in _runs(row_gutter, int(min_panel_fraction * h)):
        col_gutter = near_white[y0:y1].mean(axis=0) > gutter_fraction
        for x0, x1 in _runs(col_gutter, int(min_panel_fraction * w)):
            panels.append(Panel(len(panels), (x0, y0, x1, y1), np.ascontiguousarray(rgb[y0:y1, x0:x1])))
    if len(panels) < 2:
        return [Panel(0, (0, 0, w, h), np.ascontiguousarray(rgb))]
    return panels
