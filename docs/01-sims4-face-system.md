# 1. How The Sims 4 stores and changes a face

Evidence labels used in all documents:

- **CONFIRMED**: verified in this project, either in source code we read or by running a test.
- **LIKELY**: supported by published code or documentation, but not yet tested by us in the game.
- **EXPERIMENTAL**: plausible, but needs a test before we rely on it.
- **UNSUPPORTED**: no credible way to do it today.

All "source" references are to the repositories listed in [references.md](references.md). The clones we read are listed there with their commit dates.

## 1.1 The data model: a face is a small list of IDs and floats

**CONFIRMED (source).** A Sim's whole face and body shape is one protobuf blob,
`BlobSimFacialCustomizationData`:

```
message BlobSimFacialCustomizationData {
  repeated uint64   sculpts             = 1;  // Sculpt resource instance IDs
  repeated Modifier face_modifiers      = 2;
  repeated Modifier body_modifiers      = 3;
  repeated Modifier aged_face_modifiers = 4;
  repeated Modifier aged_body_modifiers = 5;
  message Modifier { uint64 key = 1; float amount = 2; }  // key = SimModifier instance ID
}
```

Sources: `TS4SimRipper/src/Proto/PersistenceBlobs.cs`. In save files, the blob is
stored as bytes in `SimData.facial_attr` (field 18, `FileSerialization.cs`). Mannequins use
`facial_attributes`, and genetic data has a second copy in `genetic_data.sculpts_and_mods_attr`
(`SIMInfo.cs` lines 238–300).

What this means:

- A face is **not** a set of vertex positions. It is (a) at most one **sculpt** per facial region
  and (b) a sparse list of **(modifier ID, amount)** pairs. A modifier that is not listed has amount 0.
- Everything the CAS drag tools do ends up as entries in this list. So if we can write the list,
  we have the same control as CAS. We do not need to automate the mouse.
- The format is small and stable. Field numbers in protobuf do not change without breaking every
  existing save, so it is very likely to survive game updates.

`ts4face/facial_blob.py` is our codec for this blob. Its tests check it against the real protobuf
runtime using the same schema (`tests/test_facial_blob.py`, **CONFIRMED**, 5/5 pass).

## 1.2 Modifier IDs are hashes of readable names

**CONFIRMED (test).** A SimModifier (SMOD, resource type `0xC5F6763E`) instance ID is the
FNV-1 64-bit hash of its lowercased name. For example, `fnv64("yfheadNose_TipWide") = 0x8088D1E4B2013F98`.
We hashed the 957 names in TS4 MorphMaker's `ModifierList.txt`, and 947 matched the game IDs exactly.
The other 10 are community guesses at the original names. (`ts4face/fnv.py`, `tests/test_fnv_catalog.py`.)

The name prefix encodes age and frame, followed by region and direction:
`yfhead` (young adult/adult, shared by both frames for most face modifiers), `ymhead`, `cuhead`
(child), `puhead` (toddler), `iuhead` (infant), `ad/ac/al/ax` (pets). Example names:
`yfheadNose_Wide`, `yfheadModifier_Eyes_CornerUp`, `yfheadJaw_Underbite`.

## 1.3 Modifier amounts, scales and limits

**CONFIRMED (source and data).** EA tuning resources `Client_CASModifierTuning_<Age>` give these values
for each modifier:

| Field | Meaning (as used by SimRipper) |
|---|---|
| `Scale` | Multiplier applied to the stored amount before the morph is evaluated: `weight = amount × Scale` (`Form1.cs` ~l.899) |
| `LimitDirectManip` | Maximum amount that dragging in CAS can reach |
| `LimitRandomize` | Maximum amount used by the CAS randomizer |
| `MinValue` | A lower bound (exact semantics: **EXPERIMENTAL**) |

The Young Adult tuning in the copy shipped with SimRipper (2023) lists **132 modifiers, 100 of them
facial**. These pair into about **36 two-sided axes** (for example, Nose Wide ↔ Narrow) plus about
**28 one-sided** modifiers (for example, Cheeks Gaunt) (`ts4face/catalog.py`).

| Region | Facial modifiers in YA tuning |
|---|---|
| Nose | 26 |
| Eyes | 19 |
| Mouth | 17 |
| Cheeks | 9 |
| Ears | 8 |
| Head | 7 |
| Jaw | 7 |
| Chin | 4 |
| Brows | 3 |

Stored amounts are in **[0, 1]**, and each direction is its own modifier. Published mod code
(Sims4SlowGrowthMod) uses separate "grow" and "shrink" keys and writes `abs(value)`, which agrees.
CAS never writes negative amounts (**LIKELY**). Whether the engine accepts amounts > 1 or < 0, or
values above `LimitDirectManip`, is **EXPERIMENTAL** (experiment E2, step 3).

**Important:** the tuning list is not the complete list of modifiers. MorphMaker's list has 241
`yfhead*` names, but the tuning has 100. Some modifiers exist without tuning overrides (`Scale` = 1),
and some are only reachable through sculpts or presets. The complete set of modifiers that CAS can
drag comes from the HotSpotControl resources (§1.5).

## 1.4 How a modifier deforms the head (the "forward model")

**CONFIRMED (source); the match with the engine is LIKELY.** Each SMOD points to up to three kinds of
deformation data (`SMOD.cs`):

| Resource | Type ID | What it does |
|---|---|---|
| BGEO (blend geometry) | `0x067CAA11` | Per-vertex position and normal deltas. Linear in weight. |
| DMAP (deformer map) | `0xDB43E069` | Texture-space displacement map (shape and normals), sampled at each vertex's UV1. Linear in weight. |
| BOND (bone delta) | `0x0355E0A6` | Per-bone offset, scale and rotation. Applied through skinning. Nearly linear for small weights. |

SimRipper rebuilds a Sim's head on the CPU like this (`Form1.cs` l.740–1000, `GEOM.cs` `BoneMorpher` l.2578):

```
mesh = base head GEOM (per age/frame)
for each sculpt (one per region):  apply its BGEO/DMAP/BOND at weight 1
for each face modifier m:          apply its BGEO/DMAP/BOND at weight m.amount × Scale(m)
```

This is the key finding of the research. **The deformation each slider causes is stored in
the game files as explicit data, and an open-source tool already evaluates it.** So we can calibrate
from the game assets. We do not need thousands of screenshots.

Caveats:

- SimRipper is a community reimplementation. SimRipper exports are widely used and look like the
  game, but **we have not verified that its result matches the engine at sub-millimeter accuracy**.
  Experiment E3 measures this.
- SimRipper has the `CASModifierDampening` logic **commented out**. The engine may scale some
  modifiers down depending on the active sculpts. **EXPERIMENTAL.** If this is ignored, it
  shows up as a gap between our model and the game, which E3 will detect.
- DMAP and BGEO effects add linearly. BOND transforms compose (scale × rotation × offset per bone),
  so large combinations of modifiers are slightly nonlinear. That is easy to handle in the optimizer.

## 1.5 Detail Edit Mode and mouse dragging

**CONFIRMED (source).** Dragging is driven by data. HotSpotControl resources (`HOTC`, type `0x8B18FF6E`,
MorphMaker `HOTC.cs`) define each clickable hotspot. Each hotspot records:

- region, sub-region, level (`Normal`, `Micro`, `TopLevel`), age/frame, and gender restriction
- a list of sliders, each with a **view angle** (Front, 3/4 left/right, Profile left/right) and **four
  SMOD IDs**, one per drag direction

Examples include `NoseBridgeMacroHotspotControl`, `CheekBoneHotspotControl_Micro`, `EyesLidUpperHotspotControl`,
and `MouthCornerHotspotControl` (295 hotspots across all ages in MorphMaker's list).

So a mouse drag is "pick the SMOD for this hotspot, view and direction, then change its amount".
That is the same operation as writing the blob directly, with extra UI limits. **We gain nothing
by automating the mouse**, except as a last-resort fallback.

## 1.6 Presets

**CONFIRMED (source).** CAS presets (`CPRE`, type `0xEAA32ADD`, MorphMaker `CPRE.cs`) contain an
age/frame, a region (whole face or one feature), an archetype, a display index, and a list of
**sculpt links plus (modifier, weight) pairs**. Presets therefore live in the same parameter space
as the free sliders. A region preset is a starting point in that space, not a separate system.
Presets can be found and listed automatically from the game packages (**LIKELY**, E1).

Sculpts (`type 0x9D1AB874`, `Sculpt.cs`) are region-level shape bundles. SimRipper keeps
**one sculpt per region**: EYES, NOSE, MOUTH, CHEEKS, CHIN, JAW, FOREHEAD (`Form1.cs` l.746).
They are discrete choices.

## 1.7 Symmetry

**LIKELY.** SimRipper's DMAP morph code has a `mirrorX` path (`DMAP.cs`, `GetAdjustedDelta`), and
CAS face controls are symmetric by default. Separate left and right face modifiers do not appear in
the EA modifier list. **Real facial asymmetry therefore cannot be represented with EA's own modifiers**
(**LIKELY UNSUPPORTED** without custom sliders, which the project rules exclude).

## 1.8 Frames, ages, species

**CONFIRMED (data).** The game has separate tuning files per age (Infant, Toddler, Child, Teen,
YoungAdult, Adult, Elder, plus pet ages). Many face modifiers share the `yf` names across both frames.
Gender-specific deformer maps are swapped through `Client_CASModifierPartGenderDmaps`. **The
calibration must be done separately for each age and frame**, because the base mesh, scales and DMAPs
differ. The MVP covers Young Adult in both frames.

## 1.9 Skin tone, eyes, brows, hair

These are **not** in the facial blob. Skin tone is `SimData.skin_tone` (a TONE resource ID) with
`skin_tone_val_shift`. Eye color, brows, hair and facial hair are CAS parts in the Sim's outfits
(`SIMInfo.cs`). Script mods can usually change these (**LIKELY**), but we treat them as a later phase.
Face shape is the hard part, and likeness depends most on it.

## 1.10 How appearance is saved and loaded

- **Save files** (`saves/*.save`): DBPF packages with protobuf `SaveGameData`. SimRipper **reads**
  them (**CONFIRMED** in source). Writing them back is possible in principle, but it carries a risk
  of corrupting the save, and no maintained open-source writer exists (**EXPERIMENTAL**, not recommended).
- **Tray / Gallery** (`Tray/*.trayitem, .householdbinary, .hhi, .sgi`): what "Save to Library"
  produces. No documented, verified open-source writer exists for these files (**EXPERIMENTAL**). Let the
  game write them: apply the face in the game, then use "Save to Library" (§2).
- **Running game**: the script-mod attribute `sim_info.facial_attributes` returns and accepts
  the serialized blob. Published mod code reads, edits and writes it back
  (`Sims4SlowGrowthMod/sim_modifier.py`, using `protocolbuffers.PersistenceBlobs_pb2`). **LIKELY.**
  We have not yet run it ourselves; experiment E2 tests it.

## 1.11 What is still unknown

| Question | Status | Experiment |
|---|---|---|
| Does writing `facial_attributes` in live mode update the visible Sim immediately? | LIKELY | E2 step 2 |
| Does "Modify in CAS" show and keep a scripted face? | LIKELY | E2 step 5 |
| Can a script change a Sim while CAS is open? | EXPERIMENTAL (expected no) | E2 step 7 |
| Exact list of sculpts, presets and hotspots for the current game version | LIKELY enumerable | E1 |
| Does the SimRipper-style forward model match the engine? | LIKELY | E3 |
| Effect of `MinValue` and of dampening | EXPERIMENTAL | E3 |
| Embedded Python version on the current patch (assumed 3.7) | LIKELY | E2 build |
