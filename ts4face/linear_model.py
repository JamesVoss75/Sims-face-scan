"""Linearised Sims face model and the bounded solver that turns a target shape
into concrete SimModifier IDs and amounts.

The calibration step (docs/09-calibration-and-fidelity.md) produces, per age
and frame, the base head vertices V0 and one displacement field per SMOD
(evaluated from BGEO/DMAP/BOND at amount 1, including the tuning Scale).
Every SMOD is one-sided with amount in [0, limit], so each signed CAS axis is
two non-negative variables.  Within the linear regime the head is

    V(a) = V0 + sum_j a_j * D_j          a_j in [0, limit_j]

and fitting a target is bounded linear least squares.  The regulariser pulls
towards the *default* head (a = 0), never towards an "attractive" average, so
the solver only moves sliders the target actually calls for.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import lsq_linear

from .facial_blob import FacialData


@dataclass
class ModifierBasis:
    key: int                  # SMOD instance ID written to the facial blob
    name: str
    displacement: np.ndarray  # (N, 3) vertex displacement at amount 1
    limit: float = 1.0        # upper bound on the stored amount
    opposite: int | None = None  # key of the opposite direction, if paired


class LinearFaceModel:
    def __init__(self, base_vertices: np.ndarray, modifiers: list[ModifierBasis]):
        self.v0 = np.asarray(base_vertices, dtype=np.float64)
        self.modifiers = modifiers
        self.index = {m.key: i for i, m in enumerate(modifiers)}
        n = self.v0.shape[0]
        for m in modifiers:
            if m.displacement.shape != (n, 3):
                raise ValueError(f"{m.name}: displacement shape {m.displacement.shape} != {(n, 3)}")
        # Columns = modifiers, rows = flattened vertex coordinates.
        self.D = np.stack([m.displacement.reshape(-1) for m in modifiers], axis=1) if modifiers else np.zeros((3 * n, 0))

    def evaluate(self, amounts: dict[int, float]) -> np.ndarray:
        a = np.zeros(len(self.modifiers))
        for k, v in amounts.items():
            a[self.index[k]] = v
        return self.v0 + (self.D @ a).reshape(-1, 3)

    def solve(self, target: np.ndarray, vertex_weights: np.ndarray | None = None,
              l2: float = 1e-4, min_amount: float = 1e-3) -> dict[int, float]:
        """Bounded least squares fit of V(a) to target.

        vertex_weights (N,) emphasises regions (e.g. eyes/nose > ears).
        l2 is a ridge term towards the default head.  Opposite directions of
        one axis are made mutually exclusive: if both end up non-zero, the
        weaker one is fixed at 0 and the problem is re-solved.
        """
        target = np.asarray(target, dtype=np.float64)
        w = np.ones(self.v0.shape[0]) if vertex_weights is None else np.asarray(vertex_weights, dtype=np.float64)
        sw = np.repeat(np.sqrt(w), 3)
        A = self.D * sw[:, None]
        b = (target - self.v0).reshape(-1) * sw
        k = len(self.modifiers)
        if l2 > 0:
            A = np.vstack([A, np.sqrt(l2) * np.eye(k)])
            b = np.concatenate([b, np.zeros(k)])
        upper = np.array([m.limit for m in self.modifiers], dtype=np.float64)
        fixed = np.zeros(k, dtype=bool)
        for _ in range(k + 1):
            ub = np.where(fixed, 1e-12, upper)
            res = lsq_linear(A, b, bounds=(np.zeros(k), ub), method="bvls")
            a = np.where(fixed, 0.0, res.x)
            conflict = False
            for i, m in enumerate(self.modifiers):
                j = self.index.get(m.opposite) if m.opposite is not None else None
                if j is not None and i < j and a[i] > min_amount and a[j] > min_amount:
                    fixed[i if a[i] < a[j] else j] = True
                    conflict = True
            if not conflict:
                break
        return {m.key: float(a[i]) for i, m in enumerate(self.modifiers) if a[i] > min_amount}

    def residual(self, amounts: dict[int, float], target: np.ndarray) -> float:
        """RMS vertex distance between V(amounts) and target."""
        return float(np.sqrt(np.mean(np.sum((self.evaluate(amounts) - target) ** 2, axis=1))))


def apply_to_blob(base: FacialData, amounts: dict[int, float], managed_keys: set[int]) -> FacialData:
    """Write solved amounts into a copy of a Sim's facial data.

    Every key in managed_keys is cleared first (so a direction the solver
    turned off is really removed); modifiers outside the model are kept.
    """
    out = FacialData.decode(base.encode())
    out.face_modifiers = [m for m in out.face_modifiers if m.key not in managed_keys]
    for key, amount in sorted(amounts.items()):
        out.set_face(key, round(float(amount), 6))
    return out
