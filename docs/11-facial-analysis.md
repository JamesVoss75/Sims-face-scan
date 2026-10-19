# 11. Facial analysis: method and first results

Status: **first working version**. It was tested on three user-supplied six-view sheets: two target faces
and one control. Those sheets are probably AI-generated. The results show the analyzer works and can
tell these faces apart. They do **not** measure its accuracy on real people; doc 12 describes how we
will measure that.

This work is separate from the game-integration experiments (E1/E2). Code is in `faceanalysis/` and
`tools/analyze_faces.py`; tests are in `tests/test_faceanalysis.py`.

## 11.1 Pipeline

```
sheet image ──► split into panels (white gutters/captions; layout not assumed)
             ──► per panel: MediaPipe Face Landmarker (478 pts, head pose, blendshapes)
                            + person silhouette (plain background)
             ──► view assigned from MEASURED pose, not from the caption
                   |yaw| < 12° → front (the larger-scale one → front_closeup)
                   |yaw| < 45° → three_quarter_facing_left/right
                   otherwise / no face → profile_facing_left/right (direction from silhouette)
             ──► measurements
                   frontal ratios and angles (front, close-up)
                   frontalized 3/4 views: vertical ratios only, as cross-checks
                   profile points on the silhouette outline (90° views)
                   asymmetry, skin/eye/brow/lip colour, freckles
             ──► consistency: duplicated or mirrored views, cross-view agreement, contradictions
             ──► reliability grade per measurement → profile.json (facescan.profile/1)
```

Run it:

```
pip install -r requirements-analysis.txt
python tools/fetch_face_models.py
python tools/analyze_faces.py sheet1.png sheet2.png control.png --control control
```

## 11.2 What the analyzer measures

There are 39 measurements in total, defined in one place: `faceanalysis/measure.py::METRICS`. Each
entry records its region, unit, base reliability and cross-view tolerance. All lengths are **ratios**
(scale-free) and all angles are in degrees, so photo resolution, distance and image size cancel out.

| Region | Measurements |
|---|---|
| Head | face width/height, head width/height (silhouette), midface and lower-face ratios, head height/length and forehead height (profile), facial convexity (profile) |
| Eyes | IPD/face width, inner-corner distance/IPD, eye length/IPD, eye opening, canthal tilt, iris size |
| Brows | height above eye, tilt, arch |
| Nose | nose width/inner-corner distance, nose length, tip projection, nasofrontal and nasolabial angles (profile) |
| Mouth | width/IPD, width/nose width, upper and lower lip heights, lip ratio, philtrum, mouth position, lips vs E-line (profile) |
| Jaw/chin | jaw/cheek width, chin width, frontal jaw angle, chin projection and chin–throat angle (profile) |
| Asymmetry | per-region mirror error in IPD units; eye and mouth-corner height difference; nose and chin offset from the midline |
| Appearance | skin (CIELAB, hex, ITA° skin-type angle), eye colour, brow colour/density, lip colour, freckles (spot count and pigmented-area fraction) |

Each JSON measurement has this shape:

```json
"mouth_width_to_ipd": {"value": 0.7943, "unit": "ratio", "region": "mouth", "reliability": "medium",
  "uncertainty": 0.0159, "independent_views": 1, "per_view": {"front": 0.7917, "front_closeup": 0.7968},
  "contradiction": null, "reasons": ["only one independent view"], "description": "mouth corners (61-291) / IPD"}
```

`solver_features` lists only medium- and high-reliability measurements, each with a weight. This is the
input for the Sims mapping step (doc 05 §5.2): the mapper converts each feature to a z-score against
human population statistics, then to a target in Sims slider space. Population norms are **not yet**
included. They must come from published anthropometric tables or a statistical head model, never
from these samples.

Every profile also stores the raw MediaPipe landmarks for each view (`views[].landmarks_normalized`)
and the profile points with their confidence. Later stages (3D fitting) can reuse these without
re-running detection.

## 11.3 Reliability grading

- Every measurement starts from its **base** reliability: how well that quantity can be measured from
  photos at all (doc 04 §4.4).
- **Independent evidence.** Views that share a pose (front and close-up), and profiles that are
  mirror images of each other, count as **one** source. With a single independent source, the grade
  is capped at *medium*. A six-view sheet therefore cannot earn *high* for frontal ratios. Only
  genuinely separate photos can.
- **Disagreement.** If primary views differ by more than the measurement's tolerance, the grade drops by
  one. If they differ by more than twice the tolerance, the grade drops to *low* and a **contradiction**
  is reported; the values are not averaged away. Frontalized 3/4 views and frontal-vs-profile pairs are
  checked the same way.
- Landmarks that the image crop cuts off are *unusable*, and every measurement that depends on them is dropped.

## 11.4 Results on the three test sheets

### Views detected

All 18 panels were found and assigned correctly from pose alone.

| | front | 3/4 left / right (MediaPipe yaw) | profiles | close-up |
|---|---|---|---|---|
| subject_a | yaw +1.2° | −24.6° / +26.9° | left −57.7°; right: no MediaPipe face → silhouette | +0.7° |
| subject_b | +0.2° | −25.9° / +29.2° | −51.7° / +60.9° | +0.8° |
| control | −0.4° | −25.4° / +28.1° | left −57.1°; right: silhouette | −0.3° |

### How the faces differ

These are all differences larger than twice the combined uncertainty. The full table is in
`examples/face_analysis_sample/comparison.md`.

| | Distinctive features (vs control) |
|---|---|
| **subject_a** | brows set much higher above the eyes (+38%, z = +5.5); wider mouth (+11%, z = +3.7); eyes slightly closer for face width (−4.5%); thinner upper lip (−13.5%); longer midface/nose (+6%). Appearance: blue-grey eyes, red/auburn brows, **pigmented-area fraction 2.6%** (freckles; the others 0.1–1%), skin ITA 49° ("light"). Narrower chin relative to mouth (−7%). |
| **subject_b** | upper lip set further behind the nose–chin line (z = −4.8); thinner upper (−24%) and lower (−21%) lips; flatter profile (convexity 4.5° vs 11.4°); mouth set higher (−9%); head longer for its height (−8%); shorter cranium. Dark brown eyes, light-brown brows. |
| **control** (vs mean of A and B) | brows lowest (−19%); fullest lips; most convex profile; eyes set widest for face width (+5%); narrowest mouth. Lightest skin (ITA 56°). |

Pairwise, 3–8 of 29–33 measurements separate each pair with d′ > 2, and one with d′ > 4. The mean d′
is about 1.1–1.2. In other words, the three faces have broadly similar proportions (young adult
women, the same style of render) and differ in a handful of specific features. That is exactly
the information the Sims mapping needs to preserve.

**Replicate matching.** Measurements from the front panel match the close-up of the same subject
for all three (margins 2.2–3.6× the nearest wrong match). Left-profile measurements match the
right profile of the same subject 3/3. Both results are **optimistic**. The close-up appears to
be a re-render of the front image, and the profiles are mirror copies, so this tests detection
repeatability, not real-world accuracy.

### Problems found in the sheets (the analyzer flagged these itself)

| Finding | Evidence | Consequence |
|---|---|---|
| **Right profile = mirrored left profile**, in all three sheets | silhouette IoU 0.975–0.991; texture NCC 0.91 (control) and 0.73 (A). Subject A's single lateral nose mole appears in **both** profiles | The two profiles are treated as one source of evidence |
| **Close-up is derived from the front view** | fine-detail correlation 0.42–0.50 after alignment, against about 0.1 between unrelated views | Counted as the same evidence |
| **"45°" views measure about 25–29°** | MediaPipe yaw; the same estimator reads true profiles as only 52–61° | The labels are not trusted; 3/4 views are used only for checks |
| **Subject A's nose tip is cut off by the panel edge in both profiles** | the outline touches the border | Nose projection and nasal angles for A are *unusable*, not guessed |
| **Frontal vs profile midface disagree for subject A** (0.455 vs 0.407, 11%) | cross-view check | Flagged. Part of the gap is how the nasion is defined: MediaPipe 168 sits at the eye crease, the profile nasion is the deepest bridge point. Part may be the synthetic profile |
| Lower lip not separable in most profiles | lips closed at about 10 px per lip at this resolution | Lower-lip-to-E-line left unmeasured |

### Method findings (they apply to any input)

1. **MediaPipe fails on true profiles.** Its yaw saturates at about 55–60°, and it found no face in 2 of
   3 right profiles. The silhouette method handles profiles instead, so it needs a plain
   background. Busy backgrounds will need a segmentation model; this is noted for the next iteration.
2. **Frontalizing a 3/4 view distorts horizontal ratios.** After rotating MediaPipe's 3D landmarks to
   frontal, iris size was 20–45% off and eye spacing 10–20% off, with the same bias in all three
   subjects. Vertical ratios agree within about 3%. The analyzer therefore uses turned views only to
   check vertical ratios (`TURNED_VIEW_OK`). This rule must be re-validated on real photos.
3. **Freckle detection needs colour, not darkness alone.** The first, darkness-only detector found
   more "freckles" on the unfreckled control than on subject A. Requiring a spot to be both darker
   and more yellow-brown (b*) than the surrounding skin fixed it, and front and close-up now agree.
4. **Colours are stable across views:** skin, eye, brow and lip colours agree within ΔE 0.3–3.2.

## 11.5 Limitations

- Expects plain backgrounds for silhouettes (it reports a background-uniformity confidence).
  Real photos with clutter need person segmentation.
- Hair, glasses and beards hide the cranium, brows, forehead and jaw line. These subjects are bald,
  which is the easiest case.
- No absolute size; no depth beyond what profiles show. A 3D model fit (doc 04) comes later and
  will reuse the saved landmarks.
- The colour categories (eye, brow) are descriptive heuristics. The Sims step will match CAS swatches
  by Lab distance, not by these labels.
- The thresholds for mirror detection and duplicate detection, and the frontalization rule, were chosen
  on general grounds. They need calibration on real independent photos (doc 12).
