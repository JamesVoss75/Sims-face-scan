# 8. MVP, roadmap and first experiments

## 8.1 Changes to the proposed phase order

The proposed order holds, with three changes:

1. **"Automatic application" (old Phase 5) moves into Phase 1.** The bridge mod *is* the proof that
   values can be modified, and it is small.
2. **Calibration (Phase 2) means building the asset-based twin**, not screenshot sweeps. Screenshots
   become a validation step (E3), so old Phase 6 shrinks to a drift and validation tool.
3. **Photo analysis (Phase 3) can run in parallel with Phase 2.** Neither depends on the other until
   Phase 4.

## 8.2 Roadmap

| Phase | Goal | Deliverables | Exit criterion |
|---|---|---|---|
| **1. Game-side proof** | Prove read/write of faces and list all controls | E1 inventory, E2 bridge protocol, HOTC/CPRE/Sculpt parsers, complete axis catalog per age/frame | A JSON-specified face applied to a live Sim, persisted after save and reload; all YA face hotspots mapped to SMODs |
| **2. Sims Face Model** | Asset-based calibration | GEOM/RIG/BGEO/DMAP/BOND parsers; NumPy morph engine; basis DB; landmark annotation tool; twin renderer; E3 report | Median twin-vs-game landmark error < 1% of face height on 20 test faces |
| **3. Face analysis** | Photos → neutral 3D face plus measurements with confidence | Quality gate, view labelling, multi-view FLAME 2023 Open fit, profile extraction, sheet-vs-original consistency check | Measurement repeatability across different photo sets of the same person (E5) |
| **4. Mapping and optimization** | Person → sculpts plus modifiers | Deviation transfer, dense correspondence, BVLS + sculpt search + polish, top-3 output | Lineup test (E6) clearly above chance |
| **5. App integration** | One-click apply | Inbox polling in the mod, acks, undo, age/frame checks | Apply from the app with no console typing |
| **6. Validation tooling** | Detect patch drift; optional correction | Automated capture at CAS views, silhouette alignment, per-axis gain correction | Automatic E3 re-run after a game update |
| **7. Windows app** | Usable by non-modders | PySide6 UI, installer, first-run setup, manual-report fallback, skin tone/eye color/brow/hair suggestions | Someone with no modding experience generates a Sim unaided |

## 8.3 Minimum viable product

- **Scope:** Young Adult, feminine and masculine frames, humans only, face shape only (sculpts and
  EA face modifiers). Input: one frontal photo and one profile photo (plus optional extra views).
- **Pipeline:** command line first. Run `facescan generate photos/ --frame feminine` to get `face.json`
  and a twin preview PNG. Then use `facescan.apply face.json` in the game.
- **Not in MVP:** hair, skin tone, eye color, other ages, refinement UI, installer.
- **Success:** on 10 consenting test subjects, people who know a subject pick their Sim out of a lineup
  of 5 at well above the 20% chance rate (target ≥ 60%). Also, all faces apply without errors and
  persist after reload.

## 8.4 Experiments, in order

| ID | Experiment | Needs | Risk to game/saves |
|---|---|---|---|
| **E1** | `python tools/inventory_game_files.py "<Sims 4 install>" --out inventory`: count SMOD/Sculpt/CPRE/HOTC/BGEO/DMAP/BOND/GEOM and extract all CAS modifier tuning | Game install (read-only) | None (read-only) |
| **E2** | Bridge mod protocol in `mod/README.md` (dump → set → apply → CAS → save/reload) | Python 3.7, throwaway save | Low (throwaway save, backups) |
| **E3** | Twin fidelity: render 20 dumped faces with our morph engine; compare with in-game captures | Phase 2 engine | None |
| E4 | Interaction and dampening scan on the twin; spot-check in the game | Phase 2 | None |
| E5 | Photo repeatability: 3+ photo sets of the same person → measurement variance | Phase 3 | None |
| E6 | Likeness lineup, including the effect of gain (1.0 vs 1.3) | Phase 4 | None |

**The first experiment to run is E1 then E2.** E1 is completely read-only. E2 answers the most
important open question for the whole architecture: does writing `facial_attributes` from a script
show up in the game, survive CAS, and persist? Both can be done in one evening on the game PC.

## 8.5 What I need from you

1. Run E1 on your Windows machine and send `inventory/summary.json`. The tuning XMLs can stay
   local.
2. Install Python 3.7, run E2 in a **new throwaway save**, and send the `out/*.json` files, console
   messages and any `lastException` files.
3. Decide the licence (doc 06 §6.4; I recommend GPL-3.0).
4. Optional: tell me the game version and installed packs (Game Options → About), and whether you use
   other script mods (MCCC and so on).
