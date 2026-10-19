"""Build facescan_bridge.ts4script: a zip of .pyc files compiled by Python 3.7.

The game loads .pyc compiled by the interpreter version it embeds (3.7 since
the November 2018 patch; `facescan.info` prints the version actually running).

    py -3.7 mod/build.py         -> mod/dist/facescan_bridge.ts4script

Installing (copying into the Mods folder) is a separate, explicit step:
scripts/windows/install_bridge_mod.ps1.
"""
import importlib.util
import py_compile
import sys
import tempfile
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
    sources = sorted(SRC.glob("*.py"))
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(str(OUT), "w", zipfile.ZIP_STORED) as z:
        for py in sources:
            pyc = Path(tmp) / (py.stem + ".pyc")
            py_compile.compile(str(py), cfile=str(pyc), doraise=True)
            if pyc.read_bytes()[:4] != importlib.util.MAGIC_NUMBER:
                sys.exit("unexpected .pyc header for " + py.name)
            z.write(str(pyc), py.stem + ".pyc")
    with zipfile.ZipFile(str(OUT)) as z:
        names = z.namelist()
    print("built %s (%s), magic %s" % (OUT, ", ".join(names), importlib.util.MAGIC_NUMBER.hex()))


if __name__ == "__main__":
    main()
