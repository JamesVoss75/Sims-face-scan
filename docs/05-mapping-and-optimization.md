# 5. From a human face to Sims settings, and refining it

## 5.1 Problem statement

Find **x** = (one sculpt per region, signed amount per axis) that maximizes likeness, using the
Sims Face Model `V(x) = V0 + Σ sculpt Δ + Σ_k f_k(x_k)` (doc 03) and the measured person (doc 04).
Two traps to avoid:

1. **Matching raw geometry produces an ugly, wrong-looking Sim.** Sims have large eyes, small noses and
   smooth jaws by design. If we force a Sim head onto human proportions, the solver will spend its
   whole budget shrinking the eyes and still look nothing like the person. Likeness depends on how a
   face *differs from average* (this is how caricature works).
2. **Recognition scores do not measure likeness on stylized faces.** A face-ID network can rate a Sim
   as "similar" for reasons people do not notice. We use it at most as a weak, separately validated signal.

## 5.2 The method: relative (deviation) transfer

For each measurement *m* from doc 04 §4.4:

```
z_m(person) = (m_person − μ_human) / σ_human        # μ, σ from the FLAME shape prior and anthropometric tables,
                                                    # per sex and age band
target_m    = μ_sims + g_m · z_m · σ_sims           # μ_sims = value on the default Sim head of this age/frame
                                                    # σ_sims = spread of m over the slider range used by CAS randomize
                                                    #          (LimitRandomize) or real Gallery Sims
                                                    # g_m    = gain; 1.0 = same "percentile",
                                                    #          >1 = exaggerate distinctive features
```

This maps "the person's nose is in the 90th percentile for width" to "the Sim's nose is in the 90th
percentile of Sim nose widths". The face keeps the Sims style and keeps its distinctive features.
A global **distinctiveness** control (g = 1.0–1.5) lets the user exaggerate features. Caricature
research suggests mild exaggeration improves recognition. This is a hypothesis we will test
(E6), not a given.

Dense version (after landmarks): apply the same idea to the 3D shape. Express the person as the FLAME
deviation `ΔS = S_person − S_mean` and carry it to the Sims mesh through a one-time
**dense correspondence** between the FLAME mean head and each Sims base head (non-rigid ICP that
starts from the ~100 landmark pairs). Normalize per region (eyes, nose, mouth, jaw, and so on) by
the ratio of the human and Sims spreads. This gives a **target Sims mesh** `T`.

## 5.3 Solver

Objective (per age/frame):

```
L(x) =  Σ_regions w_r · ‖ P_r (V(x) − T) ‖²             # dense, region-weighted, after similarity alignment
      + λ_m Σ_m w_m (m(V(x)) − target_m)² / s_m²         # explicit measurements (ratios, angles, profile)
      + λ_p ‖ profile(V(x)) − profile_target ‖²           # profile curve from the 90° views
      + λ_1 ‖x‖₁ + λ_2 ‖x‖²                               # few, small sliders; stays editable in CAS
subject to −lim_k⁻ ≤ x_k ≤ lim_k⁺   (LimitDirectManip by default; allow full range [0,1] as an option)
```

The weights `w_m` combine per-feature reliability (doc 04 §4.4) and how much each feature matters
perceptually. Eyes, brows, nose and mouth weigh most. Ears and cranium weigh least.

Algorithm:

1. **Linear solve.** With the linear basis, the dense and measurement terms are
   bounded least squares. Use `scipy.optimize.lsq_linear` (BVLS/TRF). This takes milliseconds.
   Map each signed variable to its +/− modifier.
2. **Sculpt and preset search.** Sculpts are discrete, one per region, with dozens of options per
   region. Regions are nearly independent, so use **coordinate descent over regions**: for each
   candidate sculpt in a region, re-solve step 1 and keep the best. This is about a few hundred linear
   solves, under a second. Seed it with the closest CAS face preset, found by nearest neighbour in
   descriptor space.
3. **Nonlinear polish.** Run L-BFGS-B or Gauss-Newton on the full forward model (BOND nonlinearity,
   clamping), starting from step 2. This takes seconds.
4. **Diversity.** Return the top 3 solutions with different sculpt choices, so the user can pick.
   Likeness is partly subjective.

Methods we compared:

| Method | Inner-loop cost | Comments |
|---|---|---|
| Linear BVLS on asset Jacobians | ms | Main workhorse |
| L-BFGS-B / Gauss-Newton on full twin | s | Polish |
| CMA-ES / Bayesian optimization on the twin | minutes | Only if the objective is non-smooth (for example, silhouette IoU) |
| Screenshot-in-the-loop optimization through the game | ~3–10 s per evaluation; hours per face | **Not recommended** as the optimizer; use it only for validation |
| LLM/vision API per adjustment | slow, costly, not reproducible | **Not needed**. Everything above runs locally |

## 5.4 Screenshot refinement (Task 6): purpose and limits

Since the twin is evaluated directly, the "screenshot → compare → adjust" loop has two jobs:

1. **Validate** that the twin equals the engine (E3) and detect drift after patches.
2. **Close the residual gap** if E3 shows systematic differences (for example, dampening). Fit a small
   correction model (per-axis gain) from captures, instead of optimizing every face through the game.

Camera consistency: CAS has fixed camera presets for its views (the HOTC view angles are front,
3/4 and profile). Whether these give pixel-repeatable framing across sessions, resolutions and
Sims of different sizes is **EXPERIMENTAL** (E3). Mitigation: align each capture to the twin render by
fitting a similarity transform to the silhouette before comparing, so exact camera repeatability is
not needed. Capture methods: Windows Graphics Capture of the game window (automatic), or the game's
own screenshot key, which saves to `Documents/…/Screenshots`.

## 5.5 Evaluating likeness

- **Objective proxies (automatic):** dense error after alignment, measurement z-score error, and
  profile curve error, each reported per region ("nose: good; jaw: weak, low photo confidence").
- **Human evaluation (the real metric):** a lineup test. Raters who know the person pick them out of 4–6
  Sims generated from different people. Track the hit rate over a test set of consenting people of
  varied sex, age and ethnicity. This is the MVP's success criterion (doc 08).
- **Face-ID embeddings** (if used): only after measuring that they correlate with the lineup results.
