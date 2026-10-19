# References

## Code we read for this research (cloned 2026-10-19)

| Project | Link | Licence | What we used it for |
|---|---|---|---|
| TS4 SimRipper Classic (CmarNYC) | https://github.com/CmarNYC-Tools/TS4SimRipper | GPL-3.0 | Save-file protobufs (`Proto/*.cs`), facial blob, morph application order and weights (`Form1.cs`), SMOD/Sculpt/DMAP/BGEO/BOND/GEOM/RIG parsers, `CASModifierTuning.package` |
| TS4 MorphMaker (CmarNYC) | https://github.com/CmarNYC-Tools/TS4MorphMaker | GPL-3.0 | HotSpotControl (`HOTC.cs`), CAS presets (`CPRE.cs`), modifier/hotspot/preset name lists |
| s4pi / s4pe (Sims4Tools) | https://github.com/s4ptacle/Sims4Tools | GPL-3.0 | DBPF package format, resource type list |
| Sims4SlowGrowthMod | https://github.com/TwidWawMon/Sims4SlowGrowthMod (`sim_modifier.py`) | see repo | Working script-mod code that reads and writes `sim_info.facial_attributes` with `PersistenceBlobs_pb2` |

MTS pages for the tools: SimRipper https://modthesims.info/d/635720 · MorphMaker https://modthesims.info/d/613061

## Other modding resources

- Sims 4 Studio: https://sims4studio.com (package editing, decompiled-script access)
- Sims4CommunityLibrary (S4CL): https://github.com/ColonolNutty/Sims4CommunityLibrary (large script-mod utility library; uses `sims.sim_info_base_wrapper`)
- Python decompilers for game scripts: https://github.com/reyemxela/sims4-decompiler, https://github.com/KitsuneDev/FastDec-TS4, workspace https://github.com/ssinakhot/sims4-workspace
- Python 3.7 move (2018): https://modthesims.info/t/618718, https://simscommunity.info/2018/10/03/modders-beware-the-sims-4-is-getting-a-python-upgrade/
- Script mod tutorial: https://medium.com/@lli-1990/tutorial-write-the-sims-4-script-mod-with-python-part-1-introduction-6d49d0dcab92
- Patch tracking for broken mods (e.g. 1.117 Aug 2025 broke many script mods): https://forums.ea.com/discussions/the-sims-4-mods-and-custom-content-en/old-broken-and-updated-sims-4-mods-and-cc-patch-1-122-march-17-2026-/13252814

## Face analysis

- MediaPipe Face Landmarker (478 3D landmarks, 52 blendshapes, transformation matrix; Apache-2.0): https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker
- FLAME model and licences (FLAME 2023 Open is CC-BY-4.0; the others are non-commercial): https://flame.is.tue.mpg.de/modellicense.html
- MediaPipe→FLAME landmark embedding (`mediapipe_landmark_embedding.npz`, 105 points) is used in e.g. https://huggingface.co/spaces/BestWJH/PEAR/blob/main/models/modules/flame/FLAME.py; official download location to be confirmed
- Pixel3DMM (ICLR 2026, CC BY-NC 4.0): https://github.com/SimonGiebenhain/pixel3dmm, https://arxiv.org/abs/2505.00615
- MICA (ECCV 2022): https://github.com/Zielon/MICA, https://arxiv.org/abs/2204.06607
- OpenCV: https://opencv.org
