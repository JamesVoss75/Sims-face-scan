# 7. Feasibility, limitations and risks

## 7.1 Direct answers

| Question | Answer | Status |
|---|---|---|
| Can we identify every relevant facial modifier? | Yes, by enumerating SMOD, HOTC, CPRE and Sculpt resources in the installed packages. Names come from tuning, hashes and community lists. | LIKELY (E1) |
| Can those values be written directly? | Yes, as the `facial_attributes` blob from a script mod. Published mod code does it. | LIKELY (E2) |
| Can we modify a Sim while CAS is open? | Probably not, and we do not need to: apply in live mode, then open CAS. | EXPERIMENTAL |
| Is direct CAS automation necessary? | No. It is a strictly weaker front end to the same values. | CONFIRMED by data model (HOTC → SMOD) |
| Can presets be searched automatically? | Yes. CPRE resources hold sculpts and modifier weights, so they can be compared numerically. | LIKELY (E1) |
| How much control does the engine provide? | About 64 face axes (YA tuning) plus more untuned SMODs, one sculpt per region for 7 regions, all symmetric | CONFIRMED (counts from 2023 tuning; recount for the current patch) |
| Can we calculate geometry changes accurately? | Yes, from BGEO/DMAP/BOND data (SimRipper does it). Match with the engine still to be measured. | LIKELY (E3) |
| Will modifier combinations interact unpredictably? | DMAP/BGEO add linearly. BOND composes nonlinearly but mildly. Possible sculpt dampening. All can be measured and modeled. | LIKELY |
| Most reliable comparison of a real face to a stylized Sim? | In a shared geometric space: deviation-from-mean measurements plus dense 3D shape plus profile curve. Not pixels and not face-ID. Validate with human lineup tests. | Design decision; E6 validates |
| What needs experimentation? | E2 (live apply), E3 (twin fidelity, dampening, camera), E5 (photo → 3D accuracy), E6 (gain/likeness) | — |
| What breaks on EA updates? | See §7.3 | — |

## 7.2 Hard limits (be honest with users)

- **No asymmetry.** EA face modifiers are symmetric (LIKELY). A crooked nose or uneven eyes cannot
  be reproduced.
- **Cranium and hairline** are mostly invisible in photos and only loosely controllable in the game.
- **Skin texture details** (wrinkles, moles, freckles) can only come from existing CAS
  skin details and overlays, never from photo textures (project rules).
- **Stylization ceiling.** Some faces sit outside the Sims shape space, for example extremely
  narrow eyes or very deep-set eyes. The result will be the nearest Sims face.
- **Hair and facial hair** affect recognizability a lot. A face-only MVP will look less like the
  person than one with matching hair. Hair matching is a later phase (CAS-part selection).

## 7.3 Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Script-mod API change (`facial_attributes`, `PersistenceBlobs_pb2`, Python version) | Low (stable since 2014; Python changed once, in 2018) | High | Tiny mod surface (one attribute); version check at startup; manual-report fallback |
| R2 | Live-mode write does not refresh the Sim visually | Medium | Medium | Look for a refresh call in the decompiled `sim_info` code; otherwise trigger travel, an outfit change, or open CAS |
| R3 | Twin ≠ engine (dampening, `MinValue`, unknown order of operations) | Medium | High | E3. Per-axis correction fitted from captures; screenshot calibration fallback (doc 03 §3.4) |
| R4 | Photo → 3D shape inaccurate (depth, focal length) | Medium | High | Require a true profile; multi-view joint fit; quality gate; report confidence |
| R5 | Deviation transfer does not look like the person | Medium | High | E6 lineup tests; tune gains per region; top-3 candidates; manual emphasis controls |
| R6 | Game patch adds or removes sculpts/modifiers | High (each pack) | Low | Rebuild the DB automatically on version change; keyed by IDs, not positions |
| R7 | Save corruption | Low (we never write saves or tray) | High | Bridge only changes one Sim in memory; backup and undo; the user saves |
| R8 | Licensing (GPL from ports; non-commercial face models) | Certain if ignored | Medium | Decide now (doc 06 §6.4); use FLAME 2023 Open only |
| R9 | Privacy (biometric data) | — | High | Local processing; no photo retention by default; no network calls |
| R10 | Other mods (MCCC, CC sliders) change the facial blob | Medium | Low | Preserve unknown modifier keys; warn about CC sliders; MVP uses EA modifiers only |
