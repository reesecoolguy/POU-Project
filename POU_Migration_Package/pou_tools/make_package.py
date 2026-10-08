"""Zip the package folder for hand-over (dist/POU_Migration_Package.zip) with a sha256 manifest.

This ZIP is a WORKING FOLDER (scripts, sources, documents, generated files). It is NOT a Power Platform solution and cannot be imported into
Power Apps or Power Automate; the only solution-shaped artefact is flows/POU_Flows_solution_CANDIDATE.zip, which is labelled unvalidated."""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXCLUDE_DIRS = {".venv", "__pycache__", ".pytest_cache", "dist", ".git"}
TOP = "POU_Migration_Package"


def files():
    for p in sorted(ROOT.rglob("*")):
        if p.is_file() and not (set(p.relative_to(ROOT).parts) & EXCLUDE_DIRS) and p.suffix != ".pyc":
            yield p


def main():
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    manifest = {}
    zpath = dist / "POU_Migration_Package.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files():
            rel = p.relative_to(ROOT).as_posix()
            manifest[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
            info = zipfile.ZipInfo(f"{TOP}/{rel}", date_time=(2026, 1, 1, 0, 0, 0))     # fixed time: the zip is reproducible
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, p.read_bytes())
        z.writestr(zipfile.ZipInfo(f"{TOP}/MANIFEST.sha256.json", date_time=(2026, 1, 1, 0, 0, 0)), json.dumps(manifest, indent=1))
    h = hashlib.sha256(zpath.read_bytes()).hexdigest()
    (dist / "POU_Migration_Package.zip.sha256").write_text(f"{h}  POU_Migration_Package.zip\n")
    print(f"{zpath} ({zpath.stat().st_size:,} bytes, {len(manifest)} files) sha256 {h}")


if __name__ == "__main__":
    main()
