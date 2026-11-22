# -*- coding: utf-8 -*-
"""Create the two assets required by KhiemUpdater.exe from an existing build."""
import hashlib
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "dist_portable" / "KhiemYoutube"
OUTPUT = ROOT / "portable_release_assets"
VERSION = "v11.4"
EXCLUDE_ROOT = {"models", "tools", "_PORTABLE_BACKUP", "_AUTO_UPDATE_BACKUPS"}
EXCLUDE_FILES = {"KhiemUpdater.exe", "portable_version.txt", "khiem_settings.json", "project_queue_v11.json"}

def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def main():
    if not (SOURCE / "KhiemYoutube.exe").is_file():
        raise RuntimeError("Khong tim thay dist_portable/KhiemYoutube/KhiemYoutube.exe")
    if not (SOURCE / "KhiemUpdater.exe").is_file():
        raise RuntimeError("Thieu KhiemUpdater.exe. Ban can build Portable moi.")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    archive = OUTPUT / "portable_update.zip"
    count = 0
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for path in sorted(SOURCE.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            rel = path.relative_to(SOURCE)
            if rel.parts[0] in EXCLUDE_ROOT or path.name in EXCLUDE_FILES:
                continue
            zipped.write(path, rel.as_posix())
            count += 1
    if not count:
        raise RuntimeError("Goi cap nhat rong.")
    manifest = OUTPUT / "portable_manifest.json"
    manifest.write_text(json.dumps({
        "version": VERSION,
        "zip_sha256": sha256(archive)
    }, indent=2), encoding="utf-8")
    with zipfile.ZipFile(archive) as zipped:
        if zipped.testzip() is not None:
            raise RuntimeError("ZIP khong hop le.")
    print("DA TAO THANH CONG", count, "files")
    print("ZIP:", archive)
    print("MANIFEST:", manifest)
    print("SHA256:", sha256(archive))
    print("Tai hai file nay len GitHub Release", VERSION)
if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("LOI:", exc)
        sys.exit(1)
