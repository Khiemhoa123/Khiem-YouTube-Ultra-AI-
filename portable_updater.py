# -*- coding: utf-8 -*-
"""Khiem Youtube Portable updater. Supports SHA256-verified multipart GitHub releases."""
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

REPO = "Khiemhoa123/Khiem-YouTube-Ultra-AI-"
ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
API = "https://api.github.com/repos/" + REPO + "/releases/latest"
CHUNK = 4 * 1024 * 1024
PROTECTED = {"models", "tools", "_PORTABLE_BACKUP", "_AUTO_UPDATE_BACKUPS"}
PROTECTED_FILES = {"KhiemUpdater.exe", "khiem_settings.json", "project_queue_v11.json", "portable_version.txt"}

def request(url):
    return urllib.request.Request(url, headers={"User-Agent": "KhiemYoutube-Updater", "Accept": "application/vnd.github+json"})

def fetch_json(url):
    with urllib.request.urlopen(request(url), timeout=60) as response:
        return json.load(response)

def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()

def download(url, target, expected_size=None, expected_sha=None):
    h = hashlib.sha256()
    total = 0
    with urllib.request.urlopen(request(url), timeout=120) as response, target.open("wb") as out:
        while True:
            data = response.read(CHUNK)
            if not data:
                break
            out.write(data)
            h.update(data)
            total += len(data)
            if expected_size:
                status.set(f"Dang tai {target.name}: {total * 100 // expected_size}%")
            else:
                status.set(f"Dang tai {target.name}: {total // (1024 * 1024)} MiB")
            window.update_idletasks()
    if expected_size is not None and total != expected_size:
        raise RuntimeError(f"Sai dung luong {target.name}: {total} != {expected_size}")
    if expected_sha and h.hexdigest().lower() != expected_sha.lower():
        raise RuntimeError("SHA256 khong khop: " + target.name)

def valid_part(part):
    if not isinstance(part, dict):
        raise RuntimeError("Manifest part khong hop le")
    name = part.get("name")
    size = part.get("size")
    digest = part.get("sha256")
    if not isinstance(name, str) or not name.startswith("portable_update.part") or not name.rsplit("part", 1)[-1].isdigit():
        raise RuntimeError("Ten part khong hop le")
    if "/" in name or "\\" in name or not isinstance(size, int) or size <= 0 or size > 2 * 1024 ** 3:
        raise RuntimeError("Dung luong hoac ten part khong hop le")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdefABCDEF" for c in digest):
        raise RuntimeError("SHA256 part khong hop le")

def get_archive(release, manifest, assets, work):
    archive = work / "update.zip"
    parts = manifest.get("parts")
    if parts is not None:
        if manifest.get("format") != "multipart-v1" or not isinstance(parts, list) or not parts or len(parts) > 100:
            raise RuntimeError("Dinh dang multipart khong hop le")
        names = [p.get("name") for p in parts if isinstance(p, dict)]
        if len(set(names)) != len(parts):
            raise RuntimeError("Part trung ten")
        for part in parts:
            valid_part(part)
            if part["name"] not in assets:
                raise RuntimeError("GitHub Release thieu " + part["name"])
        if manifest.get("zip_size") != sum(p["size"] for p in parts):
            raise RuntimeError("Tong dung luong manifest khong khop")
        # Stream parts into one ZIP; never keep multi-GB downloads in RAM.
        with archive.open("wb") as joined:
            for index, part in enumerate(parts, 1):
                status.set(f"Dang tai phan {index}/{len(parts)}...")
                window.update_idletasks()
                temp = work / part["name"]
                download(assets[part["name"]]["browser_download_url"], temp, part["size"], part["sha256"])
                with temp.open("rb") as source:
                    shutil.copyfileobj(source, joined, CHUNK)
                temp.unlink()
    else:
        if "portable_update.zip" not in assets:
            raise RuntimeError("Release thieu portable_update.zip")
        download(assets["portable_update.zip"]["browser_download_url"], archive)
    if sha256(archive) != manifest.get("zip_sha256"):
        raise RuntimeError("SHA256 ZIP khong khop")
    return archive

def safe_extract(archive, stage):
    with zipfile.ZipFile(archive) as z:
        if "KhiemYoutube.exe" not in z.namelist():
            raise RuntimeError("ZIP thieu KhiemYoutube.exe")
        seen = set()
        for item in z.infolist():
            if item.is_dir():
                continue
            name = item.filename.replace("\\", "/")
            rel = Path(name)
            if rel.is_absolute() or ".." in rel.parts or ":" in name or not rel.parts:
                raise RuntimeError("Duong dan ZIP khong an toan")
            if rel.parts[0] in PROTECTED or rel.name in PROTECTED_FILES:
                continue
            if name in seen:
                raise RuntimeError("ZIP co file trung: " + name)
            seen.add(name)
            target = stage.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(item) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output, CHUNK)
    if not (stage / "KhiemYoutube.exe").is_file():
        raise RuntimeError("Goi cap nhat thieu KhiemYoutube.exe")

def apply():
    status.set("Dang kiem tra GitHub Release...")
    window.update_idletasks()
    release = fetch_json(API)
    assets = {x["name"]: x for x in release.get("assets", [])}
    if "portable_manifest.json" not in assets:
        raise RuntimeError("Chua co portable_manifest.json tren GitHub Release")
    manifest = fetch_json(assets["portable_manifest.json"]["browser_download_url"])
    if manifest.get("version") != release.get("tag_name"):
        raise RuntimeError("Manifest khong khop tag GitHub")
    version = manifest["version"]
    current = ROOT / "portable_version.txt"
    if current.is_file() and current.read_text(encoding="utf-8").strip() == version:
        messagebox.showinfo("Khiem Youtube", "Phan mem da la phien ban moi nhat.")
        return
    if not messagebox.askyesno("Cap nhat Khiem Youtube", f"Cai phien ban {version}?\nHay dong KhiemYoutube.exe truoc khi tiep tuc.\nCan du dung luong trong de tai va giai nen."):
        return
    work = Path(tempfile.mkdtemp(prefix="khiem_update_"))
    try:
        archive = get_archive(release, manifest, assets, work)
        status.set("Dang giai nen va kiem tra...")
        window.update_idletasks()
        stage = work / "stage"
        stage.mkdir()
        safe_extract(archive, stage)
        status.set("Dang doi KhiemYoutube.exe dong...")
        window.update_idletasks()
        for _ in range(60):
            try:
                with (ROOT / "KhiemYoutube.exe").open("ab"):
                    break
            except PermissionError:
                time.sleep(1)
        else:
            raise RuntimeError("Hay dong KhiemYoutube.exe roi thu lai")
        # Keep backups for rollback. Do not overwrite the updater while it is running.
        backup = ROOT / "_PORTABLE_BACKUP"
        backup.mkdir(exist_ok=True)
        changed = []
        try:
            for source in stage.rglob("*"):
                if not source.is_file():
                    continue
                rel = source.relative_to(stage)
                destination = ROOT / rel
                if destination.is_file() and sha256(destination) == sha256(source):
                    continue
                previous = backup / rel
                previous.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    shutil.copy2(destination, previous)
                destination.parent.mkdir(parents=True, exist_ok=True)
                # Record before copying, so a partially copied file can be rolled back.
                changed.append((destination, previous))
                shutil.copy2(source, destination)
            current.write_text(version, encoding="utf-8")
        except Exception:
            for destination, previous in reversed(changed):
                if previous.exists():
                    shutil.copy2(previous, destination)
                elif destination.exists():
                    destination.unlink()
            raise
        status.set("Cap nhat thanh cong: " + version)
        messagebox.showinfo("Khiem Youtube", "Cap nhat thanh cong. Mo lai KhiemYoutube.exe.")
    finally:
        shutil.rmtree(work, ignore_errors=True)

window = tk.Tk()
window.title("KHIEM YOUTUBE | CAP NHAT PORTABLE")
window.geometry("540x210")
ttk.Label(window, text="CAP NHAT PORTABLE TU GITHUB", font=("Segoe UI", 14, "bold")).pack(pady=(20, 8))
status = tk.StringVar(value="San sang kiem tra phien ban moi.")
ttk.Label(window, textvariable=status, wraplength=500).pack(pady=6)
def start():
    button.configure(state="disabled")
    try:
        apply()
    except Exception as exc:
        status.set("Cap nhat that bai")
        messagebox.showerror("Cap nhat", str(exc))
    finally:
        button.configure(state="normal")
button = ttk.Button(window, text="KIEM TRA VA CAP NHAT", command=start)
button.pack(pady=12)
if __name__ == "__main__":
    window.mainloop()
