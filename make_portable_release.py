# -*- coding: utf-8 -*-
"""Build and verify GitHub Portable release assets without rebuilding the EXE."""
import hashlib
import json
import os
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "dist_portable" / "KhiemYoutube"
OUTPUT = ROOT / "portable_release_assets"
VERSION = "v11.4"
EXCLUDE_DIRS = {"models", "tools", "_PORTABLE_BACKUP", "_AUTO_UPDATE_BACKUPS"}
EXCLUDE_FILES = {"KhiemUpdater.exe", "portable_version.txt", "khiem_settings.json", "project_queue_v11.json"}

def say(message):
    print(message, flush=True)

def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def main():
    say("BUOC 1/4: Kiem tra Portable goc...")
    if not (SOURCE / "KhiemYoutube.exe").is_file():
        raise RuntimeError("Thieu dist_portable\\KhiemYoutube\\KhiemYoutube.exe")
    if not (SOURCE / "KhiemUpdater.exe").is_file():
        raise RuntimeError("Thieu KhiemUpdater.exe trong Portable goc")
    files = []
    for folder, dirs, names in os.walk(SOURCE):
        relative_folder = Path(folder).relative_to(SOURCE)
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith("_PORTABLE_BACKUP"))
        for name in sorted(names):
            path = Path(folder) / name
            if name in EXCLUDE_FILES or path.is_symlink():
                continue
            files.append((path, path.relative_to(SOURCE).as_posix()))
    if not any(rel == "KhiemYoutube.exe" for _, rel in files):
        raise RuntimeError("Khong co KhiemYoutube.exe trong danh sach nen")
    say(f"Tim thay {len(files)} files. Bat dau tao ZIP...")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    archive = OUTPUT / "portable_update.zip"
    manifest = OUTPUT / "portable_manifest.json"
    temp_zip = OUTPUT / "portable_update.zip.tmp"
    temp_json = OUTPUT / "portable_manifest.json.tmp"
    temp_zip.unlink(missing_ok=True)
    temp_json.unlink(missing_ok=True)
    try:
        say("BUOC 2/4: Dang dong goi (co hien tien trinh)...")
        # ZIP_STORED is much faster and avoids long blank CMD windows.
        with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as z:
            for i, (path, rel) in enumerate(files, 1):
                z.write(path, rel)
                if i == 1 or i % 25 == 0 or i == len(files):
                    say(f"  Da dong goi {i}/{len(files)} files: {rel[:70]}")
        say("BUOC 3/4: Kiem tra ZIP...")
        with zipfile.ZipFile(temp_zip, "r") as z:
            if "KhiemYoutube.exe" not in z.namelist():
                raise RuntimeError("ZIP thieu KhiemYoutube.exe")
            bad = z.testzip()
            if bad:
                raise RuntimeError(f"ZIP bi loi o file: {bad}")
        say("BUOC 4/4: Tinh SHA256 va tao manifest...")
        digest = checksum(temp_zip)
        temp_json.write_text(json.dumps({"version": VERSION, "zip_sha256": digest}, indent=2), encoding="utf-8")
        # Publish both only after all validation has passed.
        temp_zip.replace(archive)
        temp_json.replace(manifest)
        say("")
        say("========== THANH CONG ==========")
        say(f"ZIP: {archive} ({archive.stat().st_size / 1024 / 1024:.1f} MB)")
        say(f"JSON: {manifest}")
        say(f"SHA256: {digest}")
        say("Da xac nhan ZIP co KhiemYoutube.exe va khong bi loi.")
        say("Hay tai CA HAI file len GitHub Release v11.4.")
    finally:
        temp_zip.unlink(missing_ok=True)
        temp_json.unlink(missing_ok=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        say(f"LOI: {type(exc).__name__}: {exc}")
        sys.exit(1)
