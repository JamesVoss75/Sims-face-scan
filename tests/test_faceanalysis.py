"""Facial-analysis unit tests on synthetic data (no MediaPipe model, no photos).

They check geometry and invariances (scale, rotation, mirroring), not accuracy
on real faces; see docs/12-analyzer-evaluation.md for that.
"""
import math

import cv2
import numpy as np
import pytest

from faceanalysis.appearance import freckles, skin
from faceanalysis.compare import distinctive, pairwise, replicate_matching
from faceanalysis.consistency import combine, mirror_similarity
from faceanalysis.landmarks import IDX, L_BROW_LOWER, L_IRIS_RING, R_BROW_LOWER, R_IRIS_RING, pose_from_matrix
from faceanalysis.measure import asymmetry, frontal_metrics, procrustes_align
from faceanalysis.profile import analyze_profile, facing_direction
from faceanalysis.sheet import split_sheet

SKIN = (222, 170, 150)
BG = (190, 192, 196)


# ---------------------------------------------------------------- sheet splitting
def make_sheet(rows=2, cols=3, pw=200, ph=260, gutter=8, caption=40):
    h = rows * (ph + caption) + gutter
    w = cols * (pw + gutter) + gutter
    img = np.full((h, w, 3), 250, np.uint8)
    boxes = []
    for r in range(rows):
        for c in range(cols):
            x0, y0 = gutter + c * (pw + gutter), gutter + r * (ph + caption)
            img[y0:y0 + ph, x0:x0 + pw] = BG
            cv2.putText(img, "Label", (x0 + 60, y0 + ph + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 2)
            boxes.append((x0, y0, x0 + pw, y0 + ph))
    return img, boxes


def test_split_sheet_finds_grid_panels():
    img, boxes = make_sheet()
    panels = split_sheet(img)
    assert [p.bbox for p in panels] == boxes


def test_single_photo_is_one_panel():
    img = np.full((300, 200, 3), 120, np.uint8)
    assert len(split_sheet(img)) == 1


# ---------------------------------------------------------------- profile silhouettes
FACE = [  # canonical profile facing +x: (x, y) of the front outline, top to bottom
    (330, 150), (342, 215), (346, 232), (334, 262), (390, 335), (378, 350), (346, 360), (356, 378),
    (349, 392), (354, 404), (342, 425), (352, 452), (345, 470), (318, 485), (250, 500), (240, 560),
]


def make_profile(facing="right", scale=1.0):
    h, w = int(700 * scale), int(460 * scale)
    img = np.full((h, w, 3), BG, np.uint8)
    s = lambda pts: (np.array(pts, float) * scale).astype(np.int32)  # noqa: E731
    cv2.ellipse(img, tuple(s([(200, 230)])[0]), (int(150 * scale), int(185 * scale)), 0, 0, 360, SKIN, -1)
    body = FACE + [(240, 700), (60, 700), (110, 420)]
    cv2.fillPoly(img, [s(body)], SKIN)
    return img[:, ::-1].copy() if facing == "left" else img


@pytest.mark.parametrize("facing", ["left", "right"])
def test_profile_direction_and_nose_tip(facing):
    img = make_profile(facing)
    mask = np.any(img != BG, axis=2)
    assert facing_direction(mask)[0] == facing
    r = analyze_profile(img)
    assert r.facing == facing
    x, y = r.points["prn"]
    expect_x = 390 if facing == "right" else img.shape[1] - 1 - 390
    assert abs(y - 335) <= 4 and abs(x - expect_x) <= 4
    for k in ("n", "sn", "pg", "me"):
        assert k in r.points
    assert r.points["n"][1] < r.points["prn"][1] < r.points["sn"][1] < r.points["pg"][1] < r.points["me"][1] + 1


def test_profile_metrics_invariant_to_mirror_and_scale():
    a = analyze_profile(make_profile("right")).metrics
    b = analyze_profile(make_profile("left")).metrics
    c = analyze_profile(make_profile("right", scale=1.7)).metrics
    for k in ("nasal_tip_projection", "midface_ratio", "nasofrontal_angle_deg", "facial_convexity_deg"):
        assert a[k] == pytest.approx(b[k], rel=0.03, abs=0.5)
        assert a[k] == pytest.approx(c[k], rel=0.05, abs=1.0)


def test_cropped_profile_is_flagged():
    img = make_profile("right")[:, :385]  # nose tip cut by the border
    r = analyze_profile(img)
    assert any("touches the image border" in w for w in r.warnings)
    assert "nasal_tip_projection" not in r.metrics


# ---------------------------------------------------------------- frontal landmarks
def synthetic_face(mouth_half=40.0):
    p = np.zeros((478, 3))
    def put(k, x, y):
        p[IDX[k] if isinstance(k, str) else k, :2] = (x, y)
    put("R_iris", 100, 100); put("L_iris", 200, 100)
    put("R_ex", 75, 100); put("R_en", 125, 100); put("L_en", 175, 100); put("L_ex", 225, 100)
    put("R_lid_up", 100, 92); put("R_lid_lo", 100, 108); put("L_lid_up", 200, 92); put("L_lid_lo", 200, 108)
    put("nasion", 150, 100); put("subnasale", 150, 190); put("labrale_sup", 150, 220)
    put("stomion_up", 150, 230); put("stomion_lo", 150, 232); put("labrale_inf", 150, 248); put("menton", 150, 300)
    put("pronasale", 150, 180)
    put("R_zy", 50, 150); put("L_zy", 250, 150); put("R_go", 70, 240); put("L_go", 230, 240)
    put("R_ch", 150 - mouth_half, 230); put("L_ch", 150 + mouth_half, 230)
    put("R_al", 125, 185); put("L_al", 175, 185); put("R_chin", 115, 280); put("L_chin", 185, 280)
    for ring, cx in ((R_IRIS_RING, 100), (L_IRIS_RING, 200)):
        for j, (dx, dy) in enumerate(((12, 0), (0, -12), (-12, 0), (0, 12))):
            p[ring[j], :2] = (cx + dx, 100 + dy)
    for brow, sign in ((R_BROW_LOWER, -1), (L_BROW_LOWER, 1)):
        for j in range(5):   # outer -> inner
            x = 150 + sign * (90 - 15 * j)
            p[brow[j], :2] = (x, 75 - 5 * math.sin(math.pi * j / 4))
    # Midline + symmetric pairs for asymmetry
    from faceanalysis.landmarks import MIDLINE, SYMMETRY_PAIRS
    for i, k in enumerate(MIDLINE):
        if not p[k].any():
            p[k, :2] = (150, 60 + 12 * i)
    rng = np.random.default_rng(0)
    for pairs in SYMMETRY_PAIRS.values():
        for r, l in pairs:
            if not p[r].any():
                x, y = rng.uniform(60, 140), rng.uniform(80, 280)
                p[r, :2] = (x, y)
                p[l, :2] = (300 - x, y)
    return p


def transform(p, angle_deg, scale, shift):
    a = math.radians(angle_deg)
    R = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
    q = p.copy()
    q[:, :2] = (p[:, :2] @ R.T) * scale + shift
    return q


def test_frontal_metrics_values():
    m = frontal_metrics(synthetic_face())
    assert m["face_width_to_height"] == pytest.approx(1.0)
    assert m["intercanthal_to_ipd"] == pytest.approx(0.5)
    assert m["mouth_width_to_ipd"] == pytest.approx(0.8)
    assert m["midface_ratio"] == pytest.approx(0.45)
    assert m["canthal_tilt_deg"] == pytest.approx(0.0, abs=1e-6)
    assert m["iris_to_eye_width"] == pytest.approx(24 / 50)


def test_frontal_metrics_invariant_to_rotation_and_scale():
    base = frontal_metrics(synthetic_face())
    moved = frontal_metrics(transform(synthetic_face(), 17, 2.7, (40, -15)))
    for k, v in base.items():
        assert moved[k] == pytest.approx(v, rel=1e-6, abs=1e-6), k


def test_metrics_respond_to_feature_change():
    assert frontal_metrics(synthetic_face(mouth_half=50))["mouth_width_to_ipd"] == pytest.approx(1.0)


def test_asymmetry_zero_for_symmetric_and_positive_when_shifted():
    p = synthetic_face()
    assert asymmetry(p)["overall_ipd"] < 1e-6
    q = p.copy()
    q[IDX["L_ch"], 1] += 10
    a = asymmetry(q)
    assert a["regions_ipd"]["mouth"] > 0.01 and a["mouth_corner_height_diff_ipd"] == pytest.approx(0.1)


def test_procrustes_recovers_rigid_motion():
    rng = np.random.default_rng(1)
    src = rng.normal(size=(100, 3))
    a = math.radians(30)
    R = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    dst = 2.5 * src @ R.T + 4
    assert procrustes_align(src, dst) == pytest.approx(dst, abs=1e-9)


def test_pose_from_matrix_yaw_sign():
    a = math.radians(-30)
    R = np.array([[math.cos(a), 0, math.sin(a)], [0, 1, 0], [-math.sin(a), 0, math.cos(a)]])
    M = np.eye(4); M[:3, :3] = R
    yaw, pitch, roll = pose_from_matrix(M)
    assert yaw == pytest.approx(-30, abs=1e-6) and abs(pitch) < 1e-6 and abs(roll) < 1e-6


# ---------------------------------------------------------------- consistency
def test_combine_grades():
    same_pose = [{"front", "front_closeup"}]
    r = combine("mouth_width_to_ipd", {"front": 0.80, "front_closeup": 0.81}, same_pose, {"front", "front_closeup"}, set())
    assert r["reliability"] == "medium" and "only one independent view" in r["reasons"]
    r = combine("mouth_width_to_ipd", {"a": 0.80, "b": 0.805}, [], {"a", "b"}, set())
    assert r["reliability"] == "high" and r["independent_views"] == 2
    r = combine("mouth_width_to_ipd", {"a": 0.70, "b": 0.85}, [], {"a", "b"}, set())
    assert r["reliability"] == "low" and r["contradiction"] == "primary views disagree"


def test_mirror_similarity_detects_flipped_copy():
    img = make_profile("right")
    rng = np.random.default_rng(2)
    noisy = np.clip(img.astype(int) + rng.integers(-40, 40, img.shape), 0, 255).astype(np.uint8)
    mask = np.any(img != BG, axis=2)
    flipped = noisy[:, ::-1].copy()
    same = mirror_similarity(noisy, mask, flipped, mask[:, ::-1])
    assert same["iou"] > 0.99 and same["ncc"] > 0.95
    other = np.clip(img.astype(int) + rng.integers(-40, 40, img.shape), 0, 255).astype(np.uint8)
    indep = mirror_similarity(noisy, mask, other[:, ::-1].copy(), mask[:, ::-1])
    assert indep["ncc"] < 0.3


# ---------------------------------------------------------------- appearance
def face_image(spots=0, seed=0):
    img = np.full((400, 300, 3), SKIN, np.uint8)
    rng = np.random.default_rng(seed)
    img = np.clip(img.astype(int) + rng.integers(-3, 4, img.shape), 0, 255).astype(np.uint8)
    p = synthetic_face()
    for k, xy in (("R_cheek", (95, 160)), ("L_cheek", (205, 160)), ("forehead", (150, 50))):
        p[IDX[k], :2] = xy
    for _ in range(spots):
        c = (int(rng.uniform(75, 115)), int(rng.uniform(140, 180)))
        cv2.circle(img, c, 2, (180, 110, 70), -1)
    return img, p


def test_skin_colour_and_freckles():
    img, p = face_image()
    s = skin(img, p)
    expect = cv2.cvtColor(np.array([[SKIN]], np.float32) / 255, cv2.COLOR_RGB2LAB)[0, 0]
    assert s["lab"][0] == pytest.approx(float(expect[0]), abs=1.5)
    assert freckles(img, p)["spots"] == 0
    img2, p2 = face_image(spots=15)
    f = freckles(img2, p2)
    assert 8 <= f["spots"] <= 15 and f["pigmented_fraction"] > 0.005


# ---------------------------------------------------------------- comparison
def fake_profile(name, offset):
    ms = {}
    for k, base in (("mouth_width_to_ipd", 0.75), ("intercanthal_to_ipd", 0.54), ("midface_ratio", 0.44)):
        v = base + offset * (1 if k != "midface_ratio" else -0.5)
        ms[k] = {"value": v, "uncertainty": 0.01, "reliability": "medium",
                 "per_view": {"front": v + 0.003, "front_closeup": v - 0.003}}
    return {"subject": name, "measurements": ms}


def test_compare_functions():
    ps = [fake_profile("a", 0.0), fake_profile("b", 0.05), fake_profile("c", -0.05)]
    rep = replicate_matching(ps, ["front"], ["front_closeup"])
    assert rep["accuracy"] == 1.0
    pw = pairwise(ps)
    assert pw["a vs b"]["distinct_d_gt_2"] == 2  # midface differs by 0.025: d' = 1.77 < 2
    d = distinctive(ps, reference="a")
    assert d["b"][0]["metric"] in ("mouth_width_to_ipd", "intercanthal_to_ipd")
