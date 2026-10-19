# 3. Slider calibration: building the "Sims Face Model"

## 3.1 Main point: calibrate from the game assets, verify with screenshots

The user's brief suggests calibrating by changing one value and taking a screenshot. That works, but
it is slow, noisy (lighting, camera, anti-aliasing) and only measures 2D. Because each modifier's
deformation is stored as explicit BGEO/DMAP/BOND data (doc 01, §1.4), we can **compute** the exact
3D displacement of every head vertex for every modifier. This takes milliseconds per modifier and
needs no game running. Screenshots are still useful, but only to check that our computation matches
the engine (E3) and to detect drift after a game patch.

## 3.2 What the database contains (per age × frame)

```
SimsFaceModel(age, frame):
  base_mesh        V0 ∈ R^{N×3}, faces, UV1, bone weights, rig            (GEOM + RIG)
  axes[]           one per signed slider: (pos SMOD, neg SMOD | None),
                   scale, limit_direct_manip, min_value, region, hotspot/view/direction (from HOTC)
  basis[axis]      ΔV_axis^+ , ΔV_axis^-  ∈ R^{N×3}   displacement at amount 1
                   + nonlinearity probe: ΔV at amounts {0.25, 0.5, 0.75, 1.0}
  sculpts[region]  list of (sculpt id, ΔV_sculpt, thumbnail id)
  presets[]        CPRE: (region, sculpts, modifier weights, archetype, display index)
  landmarks        vertex/barycentric indices of ~100 semantic landmarks on the base mesh
  interactions     measured ‖ΔV(a+b) − ΔV(a) − ΔV(b)‖ for slider pairs sharing bones
  provenance       game version, package hashes, tool version
```

Derived descriptors for each axis (used for explanations and debugging; the optimizer does not need them):

- the anatomical feature it affects: the landmarks with the largest displacement, with direction
- the region mask: vertices with ‖ΔV‖ above a threshold
- its effect on each measurement in doc 04 (for example, "Nose[Wide/Narrow] +1 → alar width +18%")

## 3.3 Calibration pipeline

1. **Extract (read-only).** Use `ts4face.dbpf` to read the user's installed game packages (base, EP and
   GP deltas; later packages override earlier ones). Collect GEOM (head per age/frame), RIG, SMOD,
   BGEO, DMAP, BOND, Sculpt, CPRE, HOTC and the CAS modifier tuning XML. `tools/inventory_game_files.py`
   is the first slice of this (experiment E1).
2. **Evaluate the forward model.** Implement the morph math (DMAP, BGEO, bone deltas) independently
   in a vectorized NumPy module. SimRipper serves only as a black-box reference to compare against (see THIRD_PARTY_NOTICES.md). For each axis direction, compute ΔV at several amounts. Fit a
   linear term plus a small quadratic term per vertex if the probe shows curvature.
3. **Interaction scan.** Only modifiers that touch the same bones or DMAP region can interact.
   For those pairs, measure the deviation from additivity at (0.5, 0.5) and (1, 1). Expected:
   DMAP and BGEO are exactly additive, and BOND pairs deviate slightly.
4. **Sculpt deltas.** For each sculpt, compute ΔV at weight 1 on the base mesh. Then test whether
   modifier bases change when a sculpt is active (dampening). If they do, store a basis for each
   sculpt where needed.
5. **Landmarks.** Annotate once per base mesh, in a small tool: about 100 points that match the
   human-face landmark set (MediaPipe/FLAME correspondence; doc 05). The head topology is fixed per
   age/frame, so the annotation is reused for every face.
6. **Engine verification (E3).** For about 20 test faces (single sliders at ±1, random combinations,
   presets): apply them in the game through the bridge mod, capture front and profile screenshots
   at fixed CAS views, render our mesh with a matched camera, and compare silhouettes and landmark
   positions. Accept the model if the median landmark error is under about 1% of face height.
7. **Version stamp.** Store the game version and package hashes. On startup, re-run the
   extraction if they changed. Re-run E3 automatically when the game updates.

## 3.4 Fallback if the asset route fails

If the forward model cannot be made to match the engine (E3 fails), use screenshot calibration.
Through the bridge mod, apply each axis at amounts −1, −0.5, 0.5, 1 to a reference Sim. Capture fixed
front, 3/4 and profile views, and detect landmarks on the Sim render. This gives a 2D Jacobian per axis:
about 70 axes × 4 amounts × 3 views ≈ 840 captures, roughly 1–2 hours unattended. That is still
practical, but it is less accurate, and it depends on how well a landmark detector works on Sims
faces (doc 04, §4.6).

## 3.5 Legal and redistribution

Calibration data is derived from EA assets. **We do not ship it.** The app builds it on the user's
machine from their own installation, as SimRipper and MorphMaker do. EA's modding guidelines allow
free mods. Sims 4 Studio, SimRipper and MorphMaker all read game packages the same way.
