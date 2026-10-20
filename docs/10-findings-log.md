# 10. Findings log

## Round 4 (2026-10-20): E1/E2 readiness review

Fixed or added:

| Item | Why it matters |
|---|---|
| **Bug: DBPF index position read as 64-bit** (s4pi reads 32-bit at header offset 64) | Any non-zero header bytes at offset 68+ in a real package would have broken E1. Now matches s4pi, with regression tests |
| DBPF entries now always read the compression word (as s4pi does) | Doesn't depend on the size field's high bit |
| Mod v0.3: load heartbeat, persistent log with tracebacks, live API probe | A mod that doesn't load, or a game API that differs from what we assume, is now visible in the results zip |
| `facescan.step` guided test; `facescan.undo` | One repeated command instead of five labelled ones; the test is fully reversible |
| Two install methods chosen automatically (packaged `.ts4script` with Python 3.7, or loose `Scripts` folder without it) | Python 3.7 is no longer required for a first attempt; the other method is a fallback |
| Diagnostics collector with automatic triage | Game version, packs, mod settings, install and load state, exceptions, plain-language fixes |
| Results zips include console transcripts, stderr and the user's yes/no observations | Troubleshooting without the user reading code |
| Windows PowerShell 5.1 compatibility: ASCII-only scripts, stderr capture without aborting, UTF-8 Python output | `.bat` files launch 5.1, not PowerShell 7 |
| End-to-end test of the real PowerShell scripts (PowerShell 7 on Linux, simulated install) | The scripts run together with the tools, not just parse |
| Modularity test: analyzer, Sims side and mod never import each other | Keeps the photo analyzer and the solver independently testable |

Still unverified: everything inside the real game; Windows PowerShell 5.1 itself (tested on PowerShell 7);
real game package and save formats (E1 and E1b check those).

Next after E2 passes: **E3**, computing exact geometry changes per preset and modifier from the game files
(doc 09).

## Round 3 (2026-10-19): facial analyzer on three six-view sheets

Full write-up: [11-facial-analysis.md](11-facial-analysis.md). Evaluation plan: [12-analyzer-evaluation.md](12-analyzer-evaluation.md).

| Finding | Status | Architecture impact |
|---|---|---|
| MediaPipe cannot measure true profiles (yaw saturates at about 55–60°; no face in 2/3 right profiles) | CONFIRMED on test data | Profiles are measured from the **silhouette outline**. Real photos need a plain background or person segmentation |
| Frontalizing 3/4 views biases horizontal ratios by 10–45% (vertical ratios within about 3%) | CONFIRMED on test data | 3/4 views are used only as vertical cross-checks; dense 3D fitting (FLAME 2023 Open, doc 04) remains the way to use them fully |
| The supplied sheets contain non-independent views: right profile = mirrored left (all 3), close-up derived from the front view | CONFIRMED (detected automatically) | Reliability counts *independent* evidence; a sheet alone caps frontal measurements at "medium". Original photos are needed for "high" |
| A single lateral mole appears in both profiles of subject A | Observed | Concrete evidence that AI sheets invent geometry; doc 12 measures this bias against real photos |
| Freckles need a colour criterion (b* up and L* down), not darkness alone | CONFIRMED | Appearance features are colour-space based |
| The three faces are distinguishable by 3–8 measurements per pair (d′ > 2); replicate matching 3/3 | Illustrative only (n = 3, non-independent replicates) | Solver features keep subject-specific deviations; population norms are still needed for z-scoring |

The analyzer is separate from E1/E2 and the Sims solver. Its `solver_features` output is designed for the
deviation-transfer step but is **not yet connected**. That step needs human population norms and the
game calibration (Phase 2).

## Round 2 (2026-10-19): integration tooling, offline verification

What was verified, and how:

| Finding | Evidence | Status |
|---|---|---|
| The face-blob codec preserves all five lists (including `aged_face_modifiers` / `aged_body_modifiers`), list order, duplicates, absent `key`/`amount`, packed sculpts, and unknown fields at both levels | 200 randomized messages compared byte for byte with Google's protobuf runtime, plus targeted tests | CONFIRMED offline. **E1b confirms it on your real saves** |
| Save files expose each Sim's face blob **and a second "genetic" copy** (`GeneticData.sculpts_and_mods_attr`) | SimRipper protobuf definitions; our reader | CONFIRMED (format) |
| Teen, young adult, adult and elder tuning all use the same `yfhead*` modifier names (122–127 face entries each, with different Scale values per age) | EA tuning shipped with SimRipper | CONFIRMED (2023 data) |
| The mod's logic runs on the game's interpreter version | Mod tests run under CPython 3.7.17 + protobuf 3.20; `build.py` emits 3.7 bytecode (magic `420d0d0a`) | CONFIRMED offline. The game's actual version is shown by `facescan.info` |
| SimModifiers carry a `(bone hash, multiplier)` list whose meaning is unknown | Format layout | OPEN: affects twin accuracy (E3) |
| CAS hotspots reference exactly four SMODs per slider and view, but the direction order is unknown | Format layout | OPEN: E1 catalog plus names will show it |

### Changes to the architecture

1. **A second, independent verification channel: reading the save file.** Persistence no longer
   depends on trusting the mod. `check_validation.py` reads the saved face from disk read-only. The
   same reader lets the app **import an existing Sim's face** without any mod (useful as a starting
   point and for tests).
2. **The genetic copy is a new open question.** If the game uses it to restore or regenerate faces
   (for example after aging or CAS), the bridge may also need to update it. E2 reports whether it
   differs after save. Until then the mod writes only `facial_attributes`.
3. **One modifier vocabulary for teen to elder.** The catalog and solver code are shared across those
   ages. Calibration (base mesh, Scale) is still per age and frame.
4. **The solver works directly in SMOD space.** Each signed CAS axis is two one-sided SMODs. The solver
   uses bounded non-negative amounts with mutual exclusion of opposite directions, and outputs the
   exact keys written to the blob. Regularization pulls toward the **default head**, not toward a
   population average. This is the main guard against generic "attractive" faces.
5. **Safety by design for the write path.** The mod writes only to a Sim with the last name
   `FaceScanTest`, only on explicit commands, with a backup and restore. Everything else in the repo
   is read-only. This rule stays in place until E2 passes.
6. **Hotspots (HOTC) are the authoritative slider list**, not the tuning. The tuning lists about 100
   face modifiers; the game has more. E1 now builds the full catalog from hotspots and presets, with
   automatic self-checks (cross-reference resolution rates) that expose parser errors.

### Still unproven (requires your Windows PC)

- Whether `sim_info.facial_attributes` writes take effect live and persist through CAS, save and reload (E2)
- Whether our resource parsers read current game files correctly (E1 parse-failure and cross-reference rates)
- How accurately calculated head geometry matches the rendered game (E3, after the Phase 2 morph engine)
