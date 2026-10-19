"""Build facescan_bridge.ts4script (a zip of .pyc files compiled by Python 3.7).

The game loads .pyc only when compiled by the same interpreter version it embeds
(3.7 since the November 2018 patch; re-check on your install).  Run with 3.7:

    py -3.7 mod/build.py            -> mod/dist/facescan_bridge.ts4script

Copying the result into the Mods folder is a manual step on purpose.
"""
import py_compile
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "facescan_bridge"
DIST = HERE / "dist"


def main():
    if sys.version_info[:2] != (3, 7):
        sys.exit("Build with Python 3.7 (found %d.%d)" % sys.version_info[:2])
    DIST.mkdir(exist_ok=True)
    out = DIST / "facescan_bridge.ts4script"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for py in sorted(SRC.glob("*.py")):
            pyc = DIST / (py.stem + ".pyc")
            py_compile.compile(str(py), cfile=str(pyc), doraise=True)
            z.write(pyc, py.stem + ".pyc")
            pyc.unlink()
    print(out)


if __name__ == "__main__":
    main()
