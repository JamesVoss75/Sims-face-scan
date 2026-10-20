"""Build facescan_bridge.ts4script: Python 3.7 bytecode plus the source.

The game loads .ts4script zips containing compiled .pyc (a zip holding only
.py files is reportedly ignored); community templates also ship the .py
next to it.  Both are written with the same timestamp so the .pyc is used.

    py -3.7 mod/build.py         -> mod/dist/facescan_bridge.ts4script

Python 3.7 is only needed for this packaged form.  Without it, the installer
uses the loose-script form (Mods/FaceScanBridge/Scripts/facescan_bridge.py),
which needs no build.  Installing is a separate step:
scripts/windows/install_bridge_mod.ps1.
"""
import importlib.util
import os
import py_compile
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "facescan_bridge"
DIST = HERE / "dist"
OUT = DIST / "facescan_bridge.ts4script"


def main():
    if sys.version_info[:2] != (3, 7):
        sys.exit("Build with Python 3.7 (this is %d.%d). On Windows: py -3.7 mod/build.py" % sys.version_info[:2])
    DIST.mkdir(exist_ok=True)
    stamp = (int(time.time()) // 2) * 2  # zip timestamps have 2-second resolution
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(str(OUT), "w", zipfile.ZIP_STORED) as z:
        for py in sorted(SRC.glob("*.py")):
            src = Path(tmp) / py.name
            shutil.copyfile(str(py), str(src))
            os.utime(str(src), (stamp, stamp))
            pyc = Path(tmp) / (py.stem + ".pyc")
            py_compile.compile(str(src), cfile=str(pyc), doraise=True)
            if pyc.read_bytes()[:4] != importlib.util.MAGIC_NUMBER:
                sys.exit("unexpected .pyc header for " + py.name)
            date_time = time.localtime(stamp)[:6]
            for path, arc in ((pyc, py.stem + ".pyc"), (src, py.name)):
                info = zipfile.ZipInfo(arc, date_time=date_time)
                z.writestr(info, path.read_bytes())
    with zipfile.ZipFile(str(OUT)) as z:
        names = z.namelist()
    print("built %s (%s), magic %s" % (OUT, ", ".join(names), importlib.util.MAGIC_NUMBER.hex()))


if __name__ == "__main__":
    main()
