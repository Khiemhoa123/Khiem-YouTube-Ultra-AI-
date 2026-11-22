# -*- coding: utf-8 -*-
"""Khiem Youtube Portable updater. Supports SHA256-verified multipart GitHub releases."""
import hashlib
import queue
import threading
import urllib.error
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
CHUNK = 1024 * 1024
EVENTS = queue.Queue()
DOWNLOAD_STATE = {"done": 0, "total": 0, "started": 0.0}

def report(message):
    EVENTS.put(("status", message))

def ui_dialog(kind, title, message):
    reply = queue.Queue(maxsize=1)
    EVENTS.put(("dialog", kind, title, message, reply))
    return reply.get()

def report_progress(filename, received, size, global_done, global_total, speed):
    EVENTS.put(("progress", filename, received, size, global_done, global_total, speed))

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

def download(url, target, expected_size=None, expected_sha=None, base_done=0, grand_total=None):
    """Resume partial downloads with HTTP Range, retry network failures."""
    target.parent.mkdir(parents=True, exist_ok=True)
    total_size = expected_size or 0
    last_update = 0.0
    for attempt in range(7):
        offset = target.stat().st_size if target.exists() else 0
        if expected_size and offset > expected_size:
            target.unlink()
            offset = 0
        if expected_size and offset == expected_size:
            if not expected_sha or sha256(target).lower() == expected_sha.lower():
                report_progress(target.name, offset, expected_size, base_done + offset, grand_total or expected_size, 0)
                return
            target.unlink()
            offset = 0
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        req = request(url)
        for key, value in headers.items():
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                code = response.getcode()
                if offset and code != 206:
                    # Server ignored Range; restart rather than append duplicate bytes.
                    offset = 0
                    target.unlink(missing_ok=True)
                if offset and code == 206:
                    content_range = response.headers.get("Content-Range", "")
                    if not content_range.startswith(f"bytes {offset}-"):
                        raise RuntimeError("May chu tra ve Range khong dung")
                started = time.monotonic()
                initial = offset
                with target.open("ab" if offset else "wb") as out:
                    while True:
                        data = response.read(CHUNK)
                        if not data:
                            break
                        out.write(data)
                        offset += len(data)
                        now = time.monotonic()
                        if now - last_update >= 0.25:
                            speed = (offset - initial) / max(now - started, 0.1)
                            report_progress(target.name, offset, total_size, base_done + offset, grand_total or total_size, speed)
                            last_update = now
            if expected_size is not None and offset != expected_size:
                raise IOError(f"Tai chua du {target.name}: {offset}/{expected_size}")
            if expected_sha and sha256(target).lower() != expected_sha.lower():
                target.unlink(missing_ok=True)
                raise RuntimeError("SHA256 khong khop: " + target.name)
            report_progress(target.name, offset, total_size or offset, base_done + offset, grand_total or total_size or offset, 0)
            return
        except (OSError, urllib.error.URLError, RuntimeError) as exc:
            if attempt == 6:
                raise RuntimeError(f"Tai {target.name} that bai sau 7 lan thu: {exc}") from exc
            report(f"Ket noi gian doan, thu lai lan {attempt + 2}/7: {target.name}")
            time.sleep(min(2 ** attempt, 15))


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
        grand_total = sum(p["size"] for p in parts)
        done = 0
        for index, part in enumerate(parts, 1):
            report(f"Dang tai phan {index}/{len(parts)}: {part['name']}")
            download(assets[part["name"]]["browser_download_url"], work / part["name"],
                     part["size"], part["sha256"], done, grand_total)
            done += part["size"]
        report("Dang ghep cac phan thanh ZIP...")
        with archive.open("wb") as joined:
            for part in parts:
                with (work / part["name"]).open("rb") as source:
                    shutil.copyfileobj(source, joined, CHUNK)
    else:
        if "portable_update.zip" not in assets:
            raise RuntimeError("Release thieu portable_update.zip")
        download(assets["portable_update.zip"]["browser_download_url"], archive)
    report("Dang kiem tra SHA256 ZIP...")
    if sha256(archive) != manifest.get("zip_sha256"):
        archive.unlink(missing_ok=True)
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
    report("Dang kiem tra GitHub Release...")
    pass
    release = fetch_json(API)
    assets = {x["name"]: x for x in release.get("assets", [])}
    if "portable_manifest.json" not in assets:
        raise RuntimeError("Chua co portable_manifest.json tren GitHub Release")
    manifest = fetch_json(assets["portable_manifest.json"]["browser_download_url"])
    if manifest.get("version") != release.get("tag_name"):
        raise RuntimeError("Manifest khong khop tag GitHub")
    version = manifest["version"]
    current = ROOT / "portable_version.txt"
    if current.is_file() and current.read_text(encoding="utf-8").strip() == version and not force_reinstall:
        ui_dialog("info", "Khiem Youtube", "Phan mem da la phien ban moi nhat.")
        return
    if not ui_dialog("ask", "Cap nhat Khiem Youtube", f"Cai phien ban {version}?\nHay dong KhiemYoutube.exe truoc khi tiep tuc.\nCan du dung luong trong de tai va giai nen."):
        return
    work = Path(tempfile.gettempdir()) / "khiem_youtube_updates" / version
    work.mkdir(parents=True, exist_ok=True)
    try:
        archive = get_archive(release, manifest, assets, work)
        report("Dang giai nen va kiem tra...")
        pass
        stage = work / "stage"
        stage.mkdir(exist_ok=True)
        safe_extract(archive, stage)
        report("Dang doi KhiemYoutube.exe dong...")
        pass
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
        report("Cap nhat thanh cong: " + version)
        ui_dialog("info", "Khiem Youtube", "Cap nhat thanh cong. Mo lai KhiemYoutube.exe.")
    finally:
        # Keep verified parts for resume after interruption; remove extracted stage.
        shutil.rmtree(work / "stage", ignore_errors=True)

def human(n):
    return f"{n / (1024 * 1024):,.1f} MB"

window = tk.Tk()
window.title("KHIEM YOUTUBE | CAP NHAT PORTABLE")
window.geometry("700x430")
window.minsize(640, 400)
frame = ttk.Frame(window, padding=20)
frame.pack(fill="both", expand=True)
ttk.Label(frame, text="KHIEM YOUTUBE | GITHUB UPDATER", font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 12))
status = tk.StringVar(value="San sang kiem tra phien ban moi.")
ttk.Label(frame, textvariable=status, wraplength=650).pack(anchor="w", pady=(0, 12))
ttk.Label(frame, text="TIEN TRINH TONG", font=("Segoe UI", 10, "bold")).pack(anchor="w")
overall = ttk.Progressbar(frame, maximum=100)
overall.pack(fill="x", pady=(5, 4))
overall_text = tk.StringVar(value="0%")
ttk.Label(frame, textvariable=overall_text).pack(anchor="w", pady=(0, 12))
ttk.Label(frame, text="FILE DANG TAI", font=("Segoe UI", 10, "bold")).pack(anchor="w")
filename_text = tk.StringVar(value="Chua tai")
ttk.Label(frame, textvariable=filename_text).pack(anchor="w")
filebar = ttk.Progressbar(frame, maximum=100)
filebar.pack(fill="x", pady=(5, 4))
file_text = tk.StringVar(value="0 MB / 0 MB")
ttk.Label(frame, textvariable=file_text).pack(anchor="w")
speed_text = tk.StringVar(value="Toc do: -- MB/s     Con lai: --")
ttk.Label(frame, textvariable=speed_text).pack(anchor="w", pady=(8, 12))
detail_text = tk.StringVar(value="Trang thai: cho kiem tra")
ttk.Label(frame, textvariable=detail_text).pack(anchor="w", pady=(0, 10))
running = False
force_reinstall = False

def worker():
    try:
        apply()
    except Exception as exc:
        report("Cap nhat that bai")
        ui_dialog("error", "Cap nhat", str(exc))
    finally:
        EVENTS.put(("finished",))

def start():
    global running, force_reinstall
    if running:
        return
    force_reinstall = reinstall_var.get()
    running = True
    button.configure(state="disabled")
    reinstall_checkbox.configure(state="disabled")
    threading.Thread(target=worker, daemon=True).start()

reinstall_var = tk.BooleanVar(value=False)
reinstall_checkbox = ttk.Checkbutton(frame, text="Cai lai ban hien tai (chi dung de thu nghiem tren ban sao Portable)", variable=reinstall_var)
reinstall_checkbox.pack(anchor="w", pady=(2, 5))
button = ttk.Button(frame, text="KIEM TRA VA CAP NHAT", command=start)
button.pack(anchor="w", pady=8)

def pump():
    global running
    for _ in range(150):
        try:
            item = EVENTS.get_nowait()
        except queue.Empty:
            break
        kind = item[0]
        if kind == "status":
            status.set(item[1])
            detail_text.set("Trang thai: " + item[1])
        elif kind == "progress":
            _, filename, received, size, total_received, total, speed = item
            filename_text.set(filename)
            filebar["value"] = 100 * received / size if size else 0
            overall["value"] = 100 * total_received / total if total else 0
            overall_text.set(f"{overall['value']:.1f}%  |  {human(total_received)} / {human(total)}")
            file_text.set(f"{human(received)} / {human(size)}")
            if speed > 0:
                eta = max(0, total - total_received) / speed
                speed_text.set(f"Toc do: {human(speed)}/s     Con lai uoc tinh: {int(eta // 60)} phut {int(eta % 60)} giay")
        elif kind == "dialog":
            _, dialog_kind, title, message, reply = item
            if dialog_kind == "ask":
                result = messagebox.askyesno(title, message)
            elif dialog_kind == "error":
                messagebox.showerror(title, message)
                result = None
            else:
                messagebox.showinfo(title, message)
                result = None
            reply.put(result)
        elif kind == "finished":
            running = False
            button.configure(state="normal")
            reinstall_checkbox.configure(state="normal")
    window.after(100, pump)

window.after(100, pump)
if __name__ == "__main__":
    window.mainloop()
