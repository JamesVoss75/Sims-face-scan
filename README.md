# Sims Face Scan

Turn photographs of a real person into a Sims 4 face built only from the game's own CAS sculpts and
facial modifiers. No custom meshes and no photo textures.

**Status: research complete. Phase 1 proof-of-concept code is written. Nothing has been run in the game yet.**

## Recommended approach

1. **Write the face directly. Don't drive the mouse.** A Sim's face is a small protobuf blob: one
   sculpt per region plus a sparse list of (modifier ID, amount 0–1). Everything CAS dragging does
   becomes entries in that list. A tiny companion script mod sets `sim_info.facial_attributes` in
   live mode. The user then opens CAS on that Sim for preview, hair and clothes, and uses "Save to
   Library" to get a shareable Sim.
2. **Calibrate from the game assets.** Screenshots aren't needed for this step. Every modifier's
   deformation is stored as explicit vertex, deformer-map and bone data (BGEO/DMAP/BOND), and
   SimRipper already evaluates it. We build an exact local "digital twin" of the head that the
   optimizer can evaluate in milliseconds. In-game screenshots are used only to check the twin
   against the engine.
3. **Match how the face differs from average, not its raw geometry.** Photos are converted
   (MediaPipe + multi-view FLAME 2023 Open fit + profile silhouette) into a neutral 3D face and
   measurements. Each feature's percentile among humans is mapped to the same percentile among Sims.
   A bounded least-squares solve plus a discrete sculpt search then finds the settings. Distinctive
   features are kept and the Sims art style is preserved.

## Documents

| | |
|---|---|
| [docs/01-sims4-face-system.md](docs/01-sims4-face-system.md) | How the game stores and deforms faces (with evidence labels) |
| [docs/02-automation-approaches.md](docs/02-automation-approaches.md) | Script mod vs tray/save writing vs CAS GUI automation |
| [docs/03-calibration.md](docs/03-calibration.md) | Asset-based slider calibration database |
| [docs/04-face-analysis.md](docs/04-face-analysis.md) | Photo analysis, normalization, what is measurable |
| [docs/05-mapping-and-optimization.md](docs/05-mapping-and-optimization.md) | Face → Sims settings; refinement; likeness evaluation |
| [docs/06-architecture.md](docs/06-architecture.md) | Components, communication, workflow, licensing |
| [docs/07-feasibility-and-risks.md](docs/07-feasibility-and-risks.md) | Direct answers, hard limits, risk register |
| [docs/08-roadmap-and-mvp.md](docs/08-roadmap-and-mvp.md) | MVP, phased roadmap, experiments E1–E6 |
| [docs/references.md](docs/references.md) | Projects, links, licences |

## Code so far

| Path | What it is | Verified |
|---|---|---|
| `ts4face/dbpf.py` | Read-only `.package` reader (zlib, RefPack) | Unit tests; read SimRipper's real EA tuning package |
| `ts4face/facial_blob.py` | `BlobSimFacialCustomizationData` codec (pure Python) | Byte-identical with the protobuf runtime |
| `ts4face/fnv.py` | Resource ID hashing | Matches 947/957 known EA modifier IDs |
| `ts4face/catalog.py` | Tuning XML → modifiers → signed slider axes | Unit tests; heuristic pairing |
| `tools/inventory_game_files.py` | **Experiment E1**: inventory of face data in your install (read-only) | Smoke-tested on a package copy |
| `mod/` | **Experiment E2**: in-game bridge mod plus test protocol | **Not run in the game** |

```
pip install -r requirements-dev.txt
python -m pytest
```
