"""Download the MediaPipe Face Landmarker model into models/ (git-ignored) and verify it."""
import hashlib
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from faceanalysis.landmarks import MODEL_NAME, MODEL_SHA256, MODEL_URL  # noqa: E402


def main() -> int:
    dest = Path(__file__).resolve().parents[1] / "models" / MODEL_NAME
    dest.parent.mkdir(exist_ok=True)
    if not dest.exists():
        print(f"Downloading {MODEL_URL}")
        urllib.request.urlretrieve(MODEL_URL, dest)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    if digest != MODEL_SHA256:
        print(f"WARNING: sha256 {digest} differs from the pinned {MODEL_SHA256}")
        return 1
    print(f"OK {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
