# Sample facial-analysis output

Output of `tools/analyze_faces.py` on the three six-view test sheets supplied for development:
`subject_a`, `subject_b` and `control` (the blank reference template). See docs/11-facial-analysis.md.

- `*.profile.json`: full facial profiles (schema `facescan.profile/1`), including the raw landmarks
- `comparison.md` / `comparison.json`: measurement table, distinctive features, pairwise d′, replicate matching
- `comparison.png`: proportions chart (% difference from the control)

The source sheets and the annotated diagnostic images contain face photographs and are deliberately
**not** in the repository. To regenerate them locally:

    python tools/analyze_faces.py subject_a.png subject_b.png control.png --control control

This writes the results to `results/face_analysis/` (git-ignored).

These numbers describe three probably AI-generated sheets. They illustrate the method and are not accuracy
results (see docs/12-analyzer-evaluation.md).
