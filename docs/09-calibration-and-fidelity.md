# 9. Calibrating sliders from the game files, and measuring how well that matches the game

This document refines doc 03 into a buildable plan. It records what exists in the repo, what is
next, and how we will measure the accuracy of the "digital twin" against the real renderer (E3).

## 9.1 Pipeline and status

```
installed .package files
   │  ts4face.dbpf            DBPF reader (zlib, RefPack)                      done, tested
   ▼
resource parsers
   │  ts4face.resources       SMOD, Sculpt, BOND, HOTC, CPRE                   done, synthetic tests; E1 validates on real data
   │  (next) GEOM, RIG, BGEO, DMAP, CASP(head)                                 needs real files: after E1
   ▼
slider catalog (E1 output)
   │  tools/inventory_game_files.py: catalog.json                              done
   │  per age/frame: SMODs + names, scales, limits, presets, hotspots → axes
   ▼
morph engine (next)
   │  base head mesh + sculpt + Σ amount·Scale·(BGEO | DMAP | BOND)            Phase 2
   ▼
basis builder (next)
   │  per SMOD: D_j = V(amount=1) − V0; probes at 0.25/0.5/0.75 for nonlinearity
   ▼
ts4face.linear_model.LinearFaceModel                                           done, tested
   │  bounded least squares → {SMOD ID: amount} → facial blob
   ▼
bridge mod applies the blob in game (E2)
```

## 9.2 Morph engine details and open questions

1. **Head mesh.** Find the default head CAS part (body type Head) for each age and frame, and its GEOM
   with the highest LOD. It has UV1 (deformer-map space), bone weights and the rig.
2. **Sculpts first, then modifiers.** For each, the weight is `amount × Scale(age, SMOD)` from
   the tuning, then:
   - **BGEO**: vertex-indexed deltas; linear.
   - **DMAP**: sample the shape map at the vertex's UV1 and add `weight × delta`. Normals come from the
     normal map. The map covers a sub-rectangle of the UV space. Mirroring applies on X.
   - **BOND**: per-bone offset, scale and quaternion, scaled by weight. Vertices follow through
     skinning. The engine's exact blending (composition order, quaternion weighting) is
     **unknown**. SimRipper's approach (scale the quaternion components by the weight) is one
     hypothesis. E3 tests it.
   - SMOD `bone_entries` (bone hash, multiplier): meaning unknown. Candidates are per-bone
     multipliers applied to the BOND. E3 can tell them apart.
3. **Dampening** (`Client_CASModifierDampening`): some modifiers may be reduced when certain
   sculpts are active. SimRipper leaves this out. We will parse it and test it.
4. **`MinValue`, `LimitDirectManip`**: we treat them as bounds for the solver. E2's probes show
   whether CAS enforces them when it re-saves a Sim.

Linearity: BGEO and DMAP are linear in amount by construction. BOND is not linear (rotation and scale
compose), so for each SMOD the basis builder measures `‖V(a)−V0 − a·D‖` at a = 0.25…1. If an axis is
nonlinear, the optimizer polishes with the full engine (doc 05 §5.3 step 3).

## 9.3 E3: how accurate is the twin?

**Question.** For a given facial blob, how far is our computed head from the head the game renders?

**Method: differential captures** (the camera cancels out):

1. Use one disposable FaceScanTest Sim, with the camera at fixed CAS presets (front and profile face
   views). Never move the camera between captures in the same set.
2. Capture a **baseline**. Then, for each test blob, apply it with the bridge mod in live mode,
   open CAS, capture the same views, leave CAS, and apply the next blob.
3. Test set (about 25 blobs): 12 single SMODs at their CAS limit (2 per major region), 5 random
   multi-slider faces, 5 face presets, and 3 sculpts.
4. **Twin side:** render the twin mesh for each blob. Estimate the camera once per view from the
   baseline by aligning the twin silhouette and inner contours to the baseline capture (similarity transform
   plus focal length). Then reuse that camera unchanged for every blob.
5. **Metrics,** per blob and per view, as a percentage of face height (nasion to menton):
   - silhouette contour distance (mean and 95th percentile Chamfer)
   - displacement agreement: for the area that changed, compare the measured image-space change
     (game capture minus baseline) with the predicted change (twin render minus twin baseline). Report the
     **gain** `g = ⟨measured, predicted⟩ / ‖predicted‖²` and the direction cosine.
   - landmarks: about 30 projected twin landmarks against the same landmarks clicked or detected on captures
6. **Acceptance:** median contour error < 1% of face height, single-SMOD gain within 0.9–1.1, and
   direction cosine > 0.9. If gains are consistent but ≠ 1, store a per-SMOD correction factor. If
   directions are wrong, the morph engine has a bug, and we fix it before going further.

**Capture automation (later tool):** Windows Graphics Capture of the game window, with fixed window
size and the UI hidden. Until then, the game's own screenshot key works.

## 9.4 Why this matters for likeness

Real Sims 4 IDs and values come from this chain. The optimizer outputs **SimModifier instance IDs,
sculpt IDs and amounts**, never advice like "make the nose wider". The quality of a likeness is
limited by how well the twin predicts the game, and E3 measures exactly that. Combined with doc 05's
deviation transfer and a regularizer that pulls toward the **default head**, not toward a
"beautiful average", distinctive features survive as long as the twin is accurate.
