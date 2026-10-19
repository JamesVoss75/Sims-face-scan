# 2. How to get a computed face into the game

## 2.1 Options evaluated

| | A. Script-mod bridge | B. Tray/save file writing | C. CAS GUI automation | D. Hybrid (recommended) |
|---|---|---|---|---|
| Mechanism | A companion `.ts4script` sets `sim_info.facial_attributes` (plus sculpts) in live mode | An external app writes protobuf into `.trayitem/.householdbinary` or `.save` | Mouse drags, screenshots and computer vision against CAS hotspots | A + the game's own CAS and "Save to Library" + optional screenshots for validation |
| Control | Full blob, exact floats | Full blob | Limited to what dragging allows (`LimitDirectManip`), and drag-to-amount mapping is nonlinear | Full |
| Accuracy | Exact | Exact | Low to medium: each value is reached by pixel deltas | Exact |
| Speed | Under 1 s per apply | Requires a game reload | Minutes to hours (about 60–100 drags per face) | Under 1 s |
| Evidence | LIKELY (published mod code does this) | EXPERIMENTAL (no verified writer) | EXPERIMENTAL | LIKELY |
| Breaks on update when… | EA renames or removes `facial_attributes` or the protobuf module, or changes the Python version (rare; last major change was 2018) | Tray schema changes; corruption risk | Any UI, camera or layout change | Same as A |
| Save safety | Changes one Sim; the user saves normally | Can corrupt files | Safe | Safe |
| User setup | Enable script mods once | None | Fixed resolution, no moving the window, game in focus | Enable script mods once |

## 2.2 Recommendation: D, centered on A

1. **The desktop app computes the face offline** and writes a request JSON to
   `Documents/Electronic Arts/The Sims 4/facescan/in/`.
2. **The bridge mod** applies it to the selected Sim in live mode. In E2 it runs from a cheat
   command; later it will poll the inbox (see below). The mod keeps a backup of the old blob for
   undo and writes back a result JSON.
3. The user opens CAS on that Sim with the game's own "Modify in CAS" to preview it, add hair and
   clothing, and tweak.
4. **"Save to Library"** produces a normal, shareable tray Sim. The game writes the tray files, so
   we never have to.

Why not B: tray and save writing gives no extra capability over A, and it carries corruption risk and
an undocumented format. It also cannot preview without reloading. We keep a **read-only** save/tray
parser (SimRipper does this) for importing an existing Sim's face as a starting point or for
validation.

Why not C as primary: the drag tools are a lossy, slow, view-dependent front end to the same
modifier list we can write directly. C is only a fallback if EA ever blocks script mods. Even then,
a better fallback is an exact **manual report**: "Nose preset #N, then these sliders". CAS has no
numeric slider entry, though, so manual reproduction will only be approximate. We should say this
to users plainly.

## 2.3 Communication between the app and the mod

- **File inbox/outbox in the user's Sims 4 folder.** The mod reads requests from
  `facescan/in/<request_id>.json` and writes results and acks to `facescan/out/`. This needs no
  network permissions, works with any Python stdlib subset, and is easy to debug. Two ways to trigger it:
  - Phase 1: the user types a cheat command (`facescan.apply face.json`).
  - Later: the mod polls the inbox every ~1 s through a game alarm (`alarms.add_alarm`, a common pattern
    in mods; **LIKELY**), so the app's "Apply" button works hands-free.
- Sockets: whether the game's embedded Python has a working `socket` module is **unverified**. We
  do not depend on it.
- Request schema (v1):
  ```json
  {"version": 1, "request_id": "…", "target": "active_sim" | {"sim_id": 123},
   "age": "YOUNGADULT", "frame": "feminine",
   "sculpts": ["0x…"], "face_modifiers": [{"key": "0x…", "amount": 0.42}],
   "replace": true}
  ```
  The mod checks that the Sim's age and frame match the request. It refuses to apply on a mismatch,
  because modifiers are calibrated per age and frame.

## 2.4 Can we modify a Sim while CAS is open?

**EXPERIMENTAL; the expected answer is no.** CAS edits a client-side working copy and commits it
on exit, and the script layer runs on the simulation side. The workflow above avoids the question
by applying in live mode first and then opening CAS. E2 checks that a face applied in live mode survives a CAS round trip.
