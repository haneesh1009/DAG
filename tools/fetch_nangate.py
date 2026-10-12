"""Fetch the public reference library without adding it to source control."""
import hashlib
import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/The-OpenROAD-Project/OpenROAD-flow-scripts/master/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib"
SHA256 = "8d540a4d4cf6d09d27c87ad067857a9c0c2eeb023ab7a56e058cd3113db4e9b1"
TARGET = Path(__file__).resolve().parents[1] / "third_party/nangate45/NangateOpenCellLibrary_typical.lib"


def main():
    data = TARGET.read_bytes() if TARGET.exists() else urllib.request.urlopen(URL, timeout=60).read()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise SystemExit("Reference library checksum mismatch; inspect upstream changes before updating the expected hash.")
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_bytes(data)
    print(f"Verified {TARGET}")


if __name__ == "__main__":
    main()
