# FaceScan Python probe: prints one line describing the interpreter that runs it.
#   FACESCAN_PROBE|<major.minor.micro>|<sys.executable>|<bits>
# Used by scripts/windows/common.ps1 to detect Python. It is a file (not
# `python -c "..."`) because Windows PowerShell 5.1 strips double quotes from
# native-command arguments. Must run on any Python version: no f-strings.
import struct
import sys

v = sys.version_info
print("FACESCAN_PROBE|%d.%d.%d|%s|%d" % (v[0], v[1], v[2], sys.executable or "", struct.calcsize("P") * 8))
