"""Locate the Sims 4 install and user-data folders (Windows), read-only."""
from __future__ import annotations

import os
import sys
from pathlib import Path

USER_DIR_PARTS = ("Electronic Arts", "The Sims 4")

COMMON_INSTALL_DIRS = [
    r"C:\Program Files\EA Games\The Sims 4",
    r"C:\Program Files (x86)\Origin Games\The Sims 4",
    r"C:\Program Files (x86)\Steam\steamapps\common\The Sims 4",
    r"C:\Program Files\Steam\steamapps\common\The Sims 4",
    r"D:\SteamLibrary\steamapps\common\The Sims 4",
    r"C:\Program Files\Origin Games\The Sims 4",
]


def looks_like_install(path: Path) -> bool:
    return (path / "Data" / "Client").is_dir() or (path / "Game" / "Bin").is_dir()


def _registry_install_dirs() -> list[str]:
    if sys.platform != "win32":
        return []
    import winreg
    found = []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for key in (r"SOFTWARE\Maxis\The Sims 4", r"SOFTWARE\WOW6432Node\Maxis\The Sims 4"):
            try:
                with winreg.OpenKey(hive, key) as k:
                    found.append(winreg.QueryValueEx(k, "Install Dir")[0])
            except OSError:
                pass
    return found


def find_install_dirs() -> list[Path]:
    seen, out = set(), []
    for p in _registry_install_dirs() + COMMON_INSTALL_DIRS:
        path = Path(p)
        key = str(path).lower()
        if key not in seen and path.is_dir() and looks_like_install(path):
            seen.add(key)
            out.append(path)
    return out


def documents_dir() -> Path:
    """The user's real Documents folder (handles OneDrive redirection on Windows)."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        # CSIDL_PERSONAL = 5, SHGFP_TYPE_CURRENT = 0
        if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0:
            return Path(buf.value)
    return Path(os.path.expanduser("~")) / "Documents"


def user_data_dir() -> Path:
    """Documents/Electronic Arts/The Sims 4 (Mods, saves, Tray, facescan live here)."""
    return documents_dir().joinpath(*USER_DIR_PARTS)


def latest_save(saves_dir: Path) -> Path | None:
    saves = [p for p in saves_dir.glob("*.save") if p.is_file()]
    return max(saves, key=lambda p: p.stat().st_mtime) if saves else None
