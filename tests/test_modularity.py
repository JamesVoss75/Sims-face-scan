"""The photo analyzer and the Sims side (game data, solver, mod) must stay independent.

faceanalysis -> produces a facial profile (JSON); never imports ts4face or the mod.
ts4face      -> game data, codec, solver; never imports faceanalysis.
mod          -> runs inside the game; imports only the stdlib and game modules.
The only link is the profile JSON (schema facescan.profile/1).
"""
import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def imported_roots(folder: Path) -> set[str]:
    roots = set()
    for py in folder.rglob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            if isinstance(node, ast.Import):
                roots |= {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                roots.add(node.module.split(".")[0])
    return roots


def test_analyzer_does_not_import_sims_side():
    assert not imported_roots(REPO / "faceanalysis") & {"ts4face", "facescan_bridge"}


def test_sims_side_does_not_import_analyzer():
    assert "faceanalysis" not in imported_roots(REPO / "ts4face")
    for heavy in ("mediapipe", "cv2", "PIL", "matplotlib"):
        assert heavy not in imported_roots(REPO / "ts4face"), heavy


def test_mod_uses_only_stdlib_and_game_modules():
    allowed = {"binascii", "json", "os", "struct", "sys", "time", "traceback",
               "services", "sims4", "protocolbuffers"}
    assert imported_roots(REPO / "mod" / "facescan_bridge") <= allowed
