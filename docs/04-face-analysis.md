# 4. Analyzing the real face from photographs

## 4.1 Recommended stack (all local)

| Stage | Tool | Licence | Why |
|---|---|---|---|
| Face detection and 2D/3D landmarks | **MediaPipe Face Landmarker** | Apache-2.0 | 478 landmarks with relative depth, 52 blendshapes (useful to detect expression), and a head-pose matrix. Fast on CPU; Python wheels. |
| Per-view geometry | **OpenCV** (`solvePnP`, undistortion, contour tools) | Apache-2.0 | Pose and focal estimation, image normalization |
| Multi-view 3D shape | Fit **FLAME 2023 Open** shape parameters to the landmarks from all views (shared identity; per-view pose, expression and focal length) using the official MediaPipe→FLAME landmark embedding (105 points) | FLAME 2023 Open: CC-BY-4.0 (the older FLAME models are non-commercial) | A statistical shape prior stops one bad view from distorting the head. It gives a dense neutral 3D face and population statistics (PCA variances) for free. |
| Profile curve | Segmentation (MediaPipe selfie/face segmentation, or a classical edge contour) of the 90° views | Apache-2.0 | The silhouette from forehead to chin is the most reliable source of depth information: nose projection, chin projection, brow ridge, forehead slope. |
| Optional, research comparison only | Pixel3DMM, MICA, DECA/EMOCA, SMIRK | Non-commercial licences | These may give better single-image shape. Use them only to benchmark our pipeline, never ship them, unless the project stays non-commercial and their licences are accepted. |

Things we will not use as the main signal: face-recognition embeddings (ArcFace/InsightFace; the
model weights are non-commercial too) and dlib-68 (the model was trained on iBUG data with restricted terms).

## 4.2 Pipeline

1. **Intake and quality gate.** For each photo: face found? Yaw/pitch/roll estimated from the pose
   matrix. Expression neutral (blendshape scores for jaw open, smile and squint below thresholds)?
   Obstructions (glasses, hair over forehead, beard on jaw)? Resolution across the face at least
   ~250 px? Strong lens distortion? Each view gets a **confidence weight**. Views that fail are
   reported to the user with the reason.
2. **View labelling.** Assign each photo to front, ±45° or ±90° from the measured yaw, not from its
   position on the reference sheet.
3. **Joint fit.** Minimize the reprojection error of the 105 embedded landmarks across all views
   over (FLAME shape β [shared], per-view expression ψ, pose, focal length). Add these terms:
   - a profile-silhouette term for the 90° views (distance between the projected FLAME contour and
     the image contour)
   - a shape prior ‖β/σ‖² (to prevent overfitting)
   - per-view robust weights (Huber), so one bad view cannot dominate.
   Output: a neutral FLAME mesh, per-measurement uncertainty from the residuals and from
   agreement between views, and a per-view residual report.
4. **Measurements.** Compute the feature set in §4.4 on the neutral mesh. 3D measurements are more
   robust than measuring each photo separately.
5. **Privacy.** Keep only the fitted parameters, landmarks and measurements. Delete the photos from
   the working directory after the session unless the user chooses "keep".

## 4.3 Normalizing across photos

- **Scale:** we never need absolute size. Every measurement is a ratio to a stable reference:
  interpupillary distance (IPD), bizygomatic width, or nasion-to-menton height. Sims have
  stylized proportions anyway (§5.2).
- **Pose:** handled by fitting in 3D. Measurements come from the frontalized mesh, not from raw 2D distances.
- **Focal length / perspective:** close-up phone selfies (~30 cm) enlarge the nose and narrow the
  face by roughly 10–30% compared with a portrait taken at ≥1.5 m. The fit estimates focal length per
  view. The multi-view constraint makes this observable, because a 90° profile fixes depth. With
  a single selfie, the app should warn that nose and face width are unreliable.
- **Lighting:** affects segmentation and shading-based features (cheekbones), not landmarks. We do
  not use shading as a primary signal.
- **Resolution:** handled by the quality gate and confidence weights.

## 4.4 What can be measured, and how reliably

| Feature | Measurement | Best views | Reliability |
|---|---|---|---|
| Face length/width | nasion–menton height ÷ bizygomatic width; also the forehead-to-chin ratio | front | **High** |
| Eye spacing | intercanthal width ÷ IPD; IPD ÷ face width | front | **High** |
| Eye size/shape | palpebral fissure length and height; canthal tilt angle | front, close-up | **High** for length and tilt. **Medium** for opening (expression-dependent) |
| Eyebrow position/shape | brow-to-eye height; arch peak position; tilt | front | **Medium** (grooming and expression) |
| Nose width | alar width ÷ intercanthal width | front | **High** |
| Nose length | nasion–subnasale ÷ face height | front, profile | **High** |
| Nose projection / bridge profile | tip projection from the alar crease; dorsal hump; nasofrontal angle | **profile** | **High with a true profile**. Low without one |
| Nostril shape | nostril visibility, alar flare | 3/4, front | **Low–medium** |
| Mouth width / position | cheilion width ÷ IPD; stomion height | front | **High** |
| Lip fullness | upper/lower vermilion height ratio and absolute | front, profile | **Medium–high** |
| Jaw width/angle | bigonial ÷ bizygomatic width; gonial angle | front, profile | **Medium** (beards, fat, hair). Gonial angle needs a profile |
| Chin shape/projection | chin width; projection relative to lips (profile) | front, profile | **Medium–high** |
| Cheekbone prominence | zygion width; malar projection | 3/4, profile | **Low–medium** (mostly soft tissue and lighting) |
| Forehead shape | slope (profile); height (if not hidden by hair) | profile | **Medium**; often hidden |
| Overall head shape (cranium) | — | — | **Low**: hair hides it |
| Ears | — | profile | **Low**; usually hidden. Low priority for likeness |
| Asymmetry | left/right landmark deviation after mirroring | front | Measurable (**medium**), but **cannot be reproduced** with EA's symmetric modifiers (doc 01 §1.7). Report only |

## 4.5 Synthesized six-view sheets

An image AI that makes a reference sheet from a few photos invents geometry for views it never saw.
These invented views are usually the profiles, which are exactly the views that carry depth information.
Handling:

1. If the original photos are provided, fit **originals only** first. Then fit the sheet views and
   compare per-measurement predictions. If a sheet view disagrees with the originals by more than
   the measurement uncertainty, it is down-weighted and flagged ("the generated left profile shows a
   15% longer nose than your photos").
2. Without originals, treat sheet views as medium confidence. Check left/right profile consistency
   (an invented view often does not mirror its partner) and check consistency between the 45° and
   90° views.
3. The app UI should recommend at least one real frontal photo and one real profile photo. That pair
   is better than a full synthetic sheet.

## 4.6 Landmarks on Sims renders

Running MediaPipe on rendered Sims faces (for screenshot validation) is **EXPERIMENTAL**. Stylized
eyes and smooth skin may cause errors. We do not depend on it. Validation compares in-game captures
with **our own render of the twin mesh**, which has exact landmarks, using silhouettes and image
alignment. Detected landmarks are only a secondary check.
