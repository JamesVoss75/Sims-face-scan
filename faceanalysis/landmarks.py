"""MediaPipe Face Landmarker wrapper (478 landmarks, blendshapes, head pose).

The model file is not part of the repository.  Download it with
``python tools/fetch_face_models.py`` (Apache-2.0, Google).  It is looked up
at $FACESCAN_MODEL_DIR/face_landmarker.task, then models/face_landmarker.task.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

MODEL_NAME = "face_landmarker.task"
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
             "face_landmarker/float16/1/face_landmarker.task")
MODEL_SHA256 = "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"

# Landmark indices of the MediaPipe 478-point mesh used by the analyzer.
# Verified visually on a frontal image (see docs/11-facial-analysis.md).
# "R"/"L" are the subject's right/left (image left/right in a frontal photo).
IDX = {
    "nasion": 168, "pronasale": 1, "subnasale": 2, "labrale_sup": 0, "stomion_up": 13,
    "stomion_lo": 14, "labrale_inf": 17, "menton": 152,
    "R_ex": 33, "R_en": 133, "L_en": 362, "L_ex": 263,
    "R_lid_up": 159, "R_lid_lo": 145, "L_lid_up": 386, "L_lid_lo": 374,
    "R_iris": 468, "L_iris": 473,
    "R_zy": 234, "L_zy": 454, "R_go": 172, "L_go": 397,
    "R_ch": 61, "L_ch": 291, "R_al": 64, "L_al": 294,
    "R_chin": 176, "L_chin": 400,
    "R_cheek": 50, "L_cheek": 280, "forehead": 151,
}
R_IRIS_RING = (469, 470, 471, 472)
L_IRIS_RING = (474, 475, 476, 477)
R_BROW_LOWER = (46, 53, 52, 65, 55)       # outer -> inner
L_BROW_LOWER = (276, 283, 282, 295, 285)
R_BROW_UPPER = (70, 63, 105, 66, 107)
L_BROW_UPPER = (300, 293, 334, 296, 336)
MIDLINE = (10, 151, 9, 8, 168, 6, 197, 195, 5, 4, 1, 2, 0, 13, 14, 17, 18, 200, 199, 175, 152)
# Bilateral pairs (subject right, subject left) for symmetry analysis, by region.
SYMMETRY_PAIRS = {
    "eyes": [(33, 263), (133, 362), (159, 386), (145, 374), (468, 473)],
    "brows": [(46, 276), (52, 282), (55, 285), (70, 300), (105, 334)],
    "nose": [(64, 294), (98, 327), (129, 358), (48, 278)],
    "mouth": [(61, 291), (40, 270), (91, 321), (37, 267)],
    "jaw_cheeks": [(234, 454), (172, 397), (176, 400), (58, 288), (50, 280), (116, 345)],
}


def find_model(path: str | None = None) -> Path:
    candidates = [Path(path)] if path else []
    if os.environ.get("FACESCAN_MODEL_DIR"):
        candidates.append(Path(os.environ["FACESCAN_MODEL_DIR"]) / MODEL_NAME)
    candidates.append(Path(__file__).resolve().parents[1] / "models" / MODEL_NAME)
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError(f"{MODEL_NAME} not found; run: python tools/fetch_face_models.py")


@dataclass
class FaceObservation:
    points: np.ndarray            # (478, 3): x, y in pixels; z in pixel-like units (relative depth)
    yaw: float                    # degrees; negative = face turned towards image left
    pitch: float
    roll: float
    blendshapes: dict = field(default_factory=dict)
    image_size: tuple[int, int] = (0, 0)  # (width, height)

    def p(self, name_or_index) -> np.ndarray:
        i = IDX[name_or_index] if isinstance(name_or_index, str) else name_or_index
        return self.points[i, :2]


def pose_from_matrix(m: np.ndarray) -> tuple[float, float, float]:
    r = np.asarray(m)[:3, :3]
    r = r / np.linalg.norm(r, axis=0, keepdims=True)
    yaw = math.degrees(math.atan2(-r[2, 0], math.hypot(r[2, 1], r[2, 2])))
    pitch = math.degrees(math.atan2(r[2, 1], r[2, 2]))
    roll = math.degrees(math.atan2(r[1, 0], r[0, 0]))
    return yaw, pitch, roll


class LandmarkDetector:
    """Use as a context manager; one instance can process many images."""

    def __init__(self, model_path: str | None = None, min_confidence: float = 0.2):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision
        self._mp = mp
        opts = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(find_model(model_path))),
            output_face_blendshapes=True, output_facial_transformation_matrixes=True, num_faces=1,
            min_face_detection_confidence=min_confidence, min_face_presence_confidence=min_confidence)
        self._landmarker = vision.FaceLandmarker.create_from_options(opts)

    def detect(self, rgb: np.ndarray) -> FaceObservation | None:
        h, w = rgb.shape[:2]
        img = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
        res = self._landmarker.detect(img)
        if not res.face_landmarks:
            return None
        pts = np.array([(p.x * w, p.y * h, p.z * w) for p in res.face_landmarks[0]], dtype=np.float64)
        yaw, pitch, roll = pose_from_matrix(np.array(res.facial_transformation_matrixes[0]))
        bs = {b.category_name: float(b.score) for b in res.face_blendshapes[0]} if res.face_blendshapes else {}
        return FaceObservation(pts, yaw, pitch, roll, bs, (w, h))

    def close(self):
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
