import numpy as np
import pytest

from ts4face.facial_blob import FacialData, Modifier
from ts4face.fnv import fnv64
from ts4face.linear_model import LinearFaceModel, ModifierBasis, apply_to_blob

AXES = ["Nose_Wide/Nose_Narrow", "Mouth_Wide/Mouth_Narrow", "Head_Long/Head_Short",
        "Chin_Forward/Chin_Backward", "Eyes_Big/Eyes_Small"]


def make_model(n=400, seed=0, limit=1.0):
    rng = np.random.default_rng(seed)
    v0 = rng.normal(size=(n, 3))
    mods = []
    for axis in AXES:
        pos, neg = ("yfhead" + s for s in axis.split("/"))
        kp, kn = fnv64(pos), fnv64(neg)
        # Opposite directions are similar but not exact negatives (as in real SMODs).
        d = rng.normal(size=(n, 3)) * (rng.random((n, 1)) > 0.7)
        mods.append(ModifierBasis(kp, pos, d, limit, opposite=kn))
        mods.append(ModifierBasis(kn, neg, -0.8 * d + 0.05 * rng.normal(size=(n, 3)), limit, opposite=kp))
    return LinearFaceModel(v0, mods)


def test_recovers_known_amounts_as_real_smod_ids():
    model = make_model()
    truth = {fnv64("yfheadNose_Wide"): 0.613, fnv64("yfheadHead_Short"): 0.25, fnv64("yfheadEyes_Big"): 0.9}
    solved = model.solve(model.evaluate(truth), l2=1e-8)
    assert set(solved) == set(truth)
    for k in truth:
        assert solved[k] == pytest.approx(truth[k], abs=1e-4)


def test_opposite_directions_never_both_set():
    model = make_model(seed=3)
    rng = np.random.default_rng(9)
    target = model.v0 + 0.3 * rng.normal(size=model.v0.shape)  # not reachable exactly
    solved = model.solve(target)
    for m in model.modifiers:
        assert not (m.key in solved and m.opposite in solved)
    assert all(0 < v <= 1.0 for v in solved.values())


def test_bounds_respected():
    model = make_model(limit=0.5)
    truth = {fnv64("yfheadMouth_Wide"): 1.0}  # beyond the CAS limit
    solved = model.solve(model.evaluate(truth), l2=0)
    assert solved[fnv64("yfheadMouth_Wide")] == pytest.approx(0.5)


def test_default_face_target_gives_no_modifiers():
    model = make_model()
    assert model.solve(model.v0.copy()) == {}


def test_apply_to_blob_replaces_managed_and_keeps_others():
    model = make_model()
    base = FacialData(sculpts=[5], face_modifiers=[Modifier(fnv64("yfheadNose_Narrow"), 0.4), Modifier(123, 0.2)],
                      aged_face_modifiers=[Modifier(9, 0.1)])
    managed = {m.key for m in model.modifiers}
    out = apply_to_blob(base, {fnv64("yfheadNose_Wide"): 0.3}, managed)
    assert out.face_dict() == pytest.approx({123: 0.2, fnv64("yfheadNose_Wide"): 0.3})
    assert out.sculpts == [5]
    assert FacialData(aged_face_modifiers=out.aged_face_modifiers).encode() == FacialData(aged_face_modifiers=base.aged_face_modifiers).encode()
