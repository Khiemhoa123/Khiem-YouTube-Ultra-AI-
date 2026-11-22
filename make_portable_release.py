# -*- coding: utf-8 -*-
"""Build verified, GitHub-friendly multipart Portable release assets."""
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "dist_portable" / "KhiemYoutube"
OUTPUT = ROOT / "portable_release_assets"
VERSION = "v11.4"
PART_SIZE = 1500 * 1024 * 1024  # 1,500 MiB, below GitHub's 2 GiB limit
EXCLUDE_DIRS = {"models", "tools", "_PORTABLE_BACKUP", "_AUTO_UPDATE_BACKUPS"}
EXCLUDE_FILES = {"KhiemUpdater.exe", "portable_version.txt", "khiem_settings.json", "project_queue_v11.json"}

def say(message):
    print(message, flush=True)

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    say("BUOC 1/5: Kiem tra ban Portable...")
    if not (SOURCE / "KhiemYoutube.exe").is_file():
        raise RuntimeError("Thieu dist_portable/KhiemYoutube/KhiemYoutube.exe")
    if not (SOURCE / "KhiemUpdater.exe").is_file():
        raise RuntimeError("Thieu KhiemUpdater.exe. Hay build updater rieng truoc.")
    files = []
    for folder, dirs, names in os.walk(SOURCE):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS)
        for name in sorted(names):
            path = Path(folder) / name
            if name in EXCLUDE_FILES or path.is_symlink():
                continue
            files.append((path, path.relative_to(SOURCE).as_posix()))
    if not any(name == "KhiemYoutube.exe" for _, name in files):
        raise RuntimeError("Danh sach file thieu KhiemYoutube.exe")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    zip_tmp = OUTPUT / "portable_update.zip.tmp"
    manifest_tmp = OUTPUT / "portable_manifest.json.tmp"
    # Never delete the previous successful release assets until the new ones pass verification.
    zip_tmp.unlink(missing_ok=True)
    manifest_tmp.unlink(missing_ok=True)
    new_parts = []
    try:
        say(f"BUOC 2/5: Nen {len(files)} file. Vui long doi...")
        with zipfile.ZipFile(zip_tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
            for index, (path, name) in enumerate(files, 1):
                archive.write(path, name)
                if index == 1 or index % 25 == 0 or index == len(files):
                    say(f"  {index}/{len(files)}: {name[:65]}")
        say("BUOC 3/5: Kiem tra ZIP...")
        with zipfile.ZipFile(zip_tmp) as archive:
            if "KhiemYoutube.exe" not in archive.namelist():
                raise RuntimeError("ZIP thieu KhiemYoutube.exe")
            bad = archive.testzip()
            if bad:
                raise RuntimeError("ZIP bi loi: " + bad)
        zip_sha = digest(zip_tmp)
        say("BUOC 4/5: Chia thanh cac phan duoi 2 GiB...")
        parts = []
        with zip_tmp.open("rb") as source:
            number = 0
            while True:
                first = source.read(min(4 * 1024 * 1024, PART_SIZE))
                if not first:
                    break
                number += 1
                name = f"portable_update.part{number:03d}"
                target = OUTPUT / (name + ".tmp")
                new_parts.append(target)
                h = hashlib.sha256()
                size = 0
                with target.open("wb") as output:
                    chunk = first
                    while chunk:
                        output.write(chunk)
                        h.update(chunk)
                        size += len(chunk)
                        if size >= PART_SIZE:
                            break
                        chunk = source.read(min(4 * 1024 * 1024, PART_SIZE - size))
                parts.append({"name": name, "size": size, "sha256": h.hexdigest()})
                say(f"  Phan {number}: {size / (1024 ** 2):.1f} MiB")
        if not parts:
            raise RuntimeError("Khong tao duoc phan nao")
        # Verify each part and the reconstructed ZIP digest before publishing.
        joined = hashlib.sha256()
        for item, temp in zip(parts, new_parts):
            if temp.stat().st_size != item["size"] or digest(temp) != item["sha256"]:
                raise RuntimeError("Loi kiem tra phan: " + item["name"])
            with temp.open("rb") as f:
                for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
                    joined.update(block)
        if joined.hexdigest() != zip_sha:
            raise RuntimeError("SHA256 cac phan ghep lai khong khop ZIP")
        manifest = {
            "version": VERSION,
            "format": "multipart-v1",
            "zip_sha256": zip_sha,
            "zip_size": zip_tmp.stat().st_size,
            "parts": parts,
        }
        manifest_tmp.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        say("BUOC 5/5: Hoan tat...")
        for item, temp in zip(parts, new_parts):
            temp.replace(OUTPUT / item["name"])
        manifest_tmp.replace(OUTPUT / "portable_manifest.json")
        # Old assets are removed only after the new manifest and parts are ready.
        (OUTPUT / "portable_update.zip").unlink(missing_ok=True)
        for old in OUTPUT.glob("portable_update.part*"):
            if old.name not in {p["name"] for p in parts}:
                old.unlink()
        say("")
        say("========== THANH CONG ==========")
        for part in parts:
            say(f"UPLOAD: {part['name']} ({part['size'] / (1024 ** 2):.1f} MiB)")
        say("UPLOAD: portable_manifest.json")
        say("KHONG upload portable_update.zip; khong upload file .tmp")
        say("Phai build va cai KhiemUpdater.exe moi truoc khi test.")
    finally:
        zip_tmp.unlink(missing_ok=True)
        manifest_tmp.unlink(missing_ok=True)
        for path in new_parts:
            path.unlink(missing_ok=True)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        say(f"LOI: {type(exc).__name__}: {exc}")
        sys.exit(1)
