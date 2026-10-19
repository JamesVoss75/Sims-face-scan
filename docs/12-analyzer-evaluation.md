# 12. Evaluating the facial analyzer with real, independent photographs

AI-generated reference sheets can be internally consistent and still anatomically wrong. Their views
are often copies of each other (mirrored profiles, re-rendered close-ups), so agreement between views
looks like accuracy without being accuracy. Doc 11 showed this happening. This protocol measures the
analyzer only against evidence the generator could not have shaped.

## 12.1 Principles

1. **Ground truth never comes from the same image source as the input.** We judge an analysis of
   photos against independent photos, physical measurement or 3D capture of the same person. We never
   judge it against another view from the same sheet.
2. **Hold-out discipline.** Split participants into a *development* set and a *test* set before
   looking at results. Tune thresholds (mirror detection, tolerances, `TURNED_VIEW_OK`) on development
   only. Report test results once, and fix acceptance criteria before the test run.
3. **The unit of analysis is the person, not the image.** Repeated photos of one person do not count
   as independent samples for accuracy statistics.
4. **Consent and privacy.** Participants give written consent for face photos and derived
   measurements. All processing runs locally. Raw photos stay out of the repository; the project
   stores only pseudonymous IDs and measurements.

## 12.2 Data to collect per participant

Target: **at least 20 adults** for a first estimate, varied in sex, age, ethnicity and face shape.
Aim for 40+ before making accuracy claims.

| Set | How | Purpose |
|---|---|---|
| **S1: session 1 photo set** | Phone camera at ≥1.5 m on a tripod at eye height, plain wall, even light, neutral expression, hair off the face. Front, 45° left/right, 90° left/right (turntable marks on the floor) | Main input |
| **S2: session 2 photo set** | Same protocol, a different day, different phone or person operating it | Test–retest repeatability (independent capture) |
| **S3: casual photos** | 5–10 ordinary photos (selfies, snapshots) | Robustness to real-world input |
| **G1: caliper measurements** | Measured by hand with a sliding/spreading caliper: IPD (pupillometer or ruler), inner-corner distance, nose width, mouth width, bizygomatic and bigonial width, nasion–menton, subnasale–menton, nose projection. Measure twice, by two people if possible | Physical ground truth for ratios |
| **G2: 3D scan (optional)** | Phone TrueDepth / LiDAR face scan, or photogrammetry from 30+ photos | Dense ground truth, profile curves and angles |
| **AI: generated sheet** | Create a six-view sheet from S3 with the image AI the user would use | Measures the bias and noise that AI sheets add |

A **public multi-view dataset** with 3D ground truth can extend this, provided its licence allows our
use. Examples are FaceScape, Headspace and the NoW benchmark (several are research-only). Check the
licence before use, and keep it separate from the participant study.

## 12.3 Experiments and metrics

| ID | Question | Comparison | Metric |
|---|---|---|---|
| **A1** | Are measurements **repeatable** across independent captures? | S1 vs S2, per measurement | ICC(2,1) across participants; within-subject SD; smallest detectable change |
| **A2** | Are measurements **accurate**? | S1 vs G1 (ratios computed from caliper values); profile metrics vs G2 | Bland–Altman bias and 95% limits of agreement; MAE as % of the population SD |
| **A3** | Does the analyzer **distinguish people**? | S2 profile of each person against the S1 profiles of everyone | Rank-1 identification and AUC, distances in units of noise (the method from doc 11). Report *between-person SD / within-person SD* per measurement |
| **A4** | What do **AI sheets** do to measurements? | AI sheet vs S1 for the same person | Bias and spread per measurement. How often consistency checks fire. Whether flagged contradictions coincide with large errors |
| **A5** | Are the **reliability grades** honest? | Error (A2) grouped by assigned grade | Error must increase from high → medium → low. Uncertainty calibration: the share of errors within ±1 and ±2 uncertainties (target about 68% and 95%) |
| **A6** | **Robustness** to casual photos | S3 vs S1 | Same as A1, plus the rate of detected quality problems |
| **A7** | Are the **checks** right? | Known positives: synthetically mirrored/duplicated views. Known negatives: S1/S2 pairs | False-positive and false-negative rates of mirror, duplicate and contradiction detection; this calibrates thresholds on the development set |

## 12.4 Acceptance criteria (proposed, to fix before the test run)

- A1: ICC ≥ 0.75 for every measurement used by the solver with weight 1.0; others get weight ≤ 0.5
  or are dropped.
- A2: |bias| < 0.25 population SD and limits of agreement within ±0.75 SD for high-weight measurements.
- A3: rank-1 identification ≥ 90% among 20 people using measurements alone. This is a sanity floor:
  recognizable Sims need the features that separate people.
- A5: errors are monotonic in the grade; 60–75% of errors fall within ±1 uncertainty.
- A4: the documented AI-sheet bias per measurement is used to down-weight sheet-derived features
  unless original photos agree.

## 12.5 Tooling to add

- `tools/eval_analyzer.py`: reads a participants manifest (pseudonymous IDs, file lists per set,
  caliper CSV), runs the analyzer, and writes A1–A7 tables and plots.
- Manual landmark annotation for a subset (two annotators) to measure landmark error directly.
  This separates detector error from measurement-definition error, such as MediaPipe 168 vs the
  profile nasion.
- A synthetic stress test: mirror, crop, rescale, recompress and relight real photos to
  check that every flag fires when it should.

## 12.6 What not to do

- Don't report "accuracy" from agreement between views of one generated sheet.
- Don't tune thresholds on the people used for the final numbers.
- Don't train a face-recognition model on these samples. The analyzer measures geometry; recognition
  embeddings are not used for likeness (doc 05 §5.1).
