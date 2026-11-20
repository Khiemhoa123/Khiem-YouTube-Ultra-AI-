# -*- coding: utf-8 -*-
"""Khiem YouTube V2 updater, opt-in updates of existing and new Python modules."""
from pathlib import Path
import ast
import datetime
import json
import os
import shutil
import subprocess
import tempfile
import tkinter as tk
from tkinter import messagebox, scrolledtext
import threading

ROOT = Path(__file__).resolve().parent
REPO = "https://github.com/Khiemhoa123/Khiem-YouTube-Ultra-AI-.git"
BACKUPS = ROOT / "_AUTO_UPDATE_BACKUPS"

def git(*args, cwd=None):
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    p = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True,
                       text=True, encoding="utf-8", errors="replace",
                       timeout=180, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if p.returncode:
        raise RuntimeError(p.stderr[-1200:] + "\nCheck Git for Windows and GitHub login.")
    return p.stdout.strip()

def changed_files(checkout):
    result = []
    for src in sorted(checkout.glob("*.py")):
        dst = ROOT / src.name
        if src.name in ("khiem_auto_update.py", "khiem_auto_update_v2.py") or src.is_symlink() or src.stat().st_size > 2 * 1024 * 1024:
            continue
        if dst.is_symlink() or (dst.exists() and not dst.is_file()):
            continue
        ast.parse(src.read_text(encoding="utf-8-sig"), filename=str(src))
        if not dst.exists() or src.read_bytes() != dst.read_bytes():
            result.append((src, dst))
    return result

def update(log, install=False):
    if not shutil.which("git"):
        raise RuntimeError("Install Git for Windows first: https://git-scm.com/downloads/win")
    with tempfile.TemporaryDirectory(prefix="khiem_update_") as temp:
        checkout = Path(temp) / "repo"
        log("Connecting to private GitHub...")
        git("clone", "--quiet", "--depth", "1", "--branch", "main", REPO, str(checkout))
        revision = git("rev-parse", "HEAD", cwd=checkout)
        changes = changed_files(checkout)
        log("GitHub revision: " + revision[:12])
        log("Changed Python files: " + str(len(changes)))
        for _, dst in changes:
            log(("  UPDATE " if dst.exists() else "  NEW    ") + dst.name)
        if not changes or not install:
            return
        # Confirmation is handled on the Tk main thread before starting this worker.
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup = BACKUPS / stamp
        backup.mkdir(parents=True, exist_ok=False)
        manifest = {"revision": revision, "entries": [{"name": d.name, "existed": d.exists()} for _, d in changes]}
        for _, dst in changes:
            if dst.exists():
                shutil.copy2(dst, backup / dst.name)
        (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        replaced = []
        try:
            for src, dst in changes:
                staged = dst.with_name(dst.name + ".khiem_new")
                shutil.copy2(src, staged)
                os.replace(staged, dst)
                replaced.append(dst)
        except Exception:
            for dst in replaced:
                if (backup / dst.name).exists():
                    shutil.copy2(backup / dst.name, dst)
                else:
                    dst.unlink(missing_ok=True)
            raise
        log("Update complete. Restart editor. Backup: " + str(backup))

def restore(log):
    if not BACKUPS.is_dir():
        raise RuntimeError("No backup yet.")
    folders = sorted(p for p in BACKUPS.iterdir() if (p / "manifest.json").is_file())
    if not folders:
        raise RuntimeError("No valid backup.")
    backup = folders[-1]
    data = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    entries = data.get("entries", [{"name": n, "existed": True} for n in data.get("files", [])])
    names = [e["name"] for e in entries]
    if not all(isinstance(n, str) and Path(n).name == n and n.endswith(".py")
               and n not in ("khiem_auto_update.py", "khiem_auto_update_v2.py") for n in names):
        raise RuntimeError("Invalid backup manifest.")
    # Confirmation is handled on the Tk main thread before starting this worker.
    # Preflight all files before modifying anything.
    for entry in entries:
        if not isinstance(entry.get("existed"), bool):
            raise RuntimeError("Invalid manifest entry")
        if entry["existed"] and not (backup / entry["name"]).is_file():
            raise RuntimeError("Missing backup file: " + entry["name"])
    for entry in entries:
        name = entry["name"]
        if entry["existed"]:
            shutil.copy2(backup / name, ROOT / name)
        else:
            (ROOT / name).unlink(missing_ok=True)
    log("Restored. Restart editor.")

class UI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Khiem YouTube | AUTO UPDATE V2")
        self.root.geometry("780x450")
        self.last_check = None
        self.logbox = scrolledtext.ScrolledText(self.root, font=("Consolas", 10))
        self.logbox.pack(fill="both", expand=True, padx=12, pady=12)
        bar = tk.Frame(self.root)
        bar.pack(pady=8)
        self.buttons = []
        for title, task in [
            ("Check updates", lambda: self.start(self.check)),
            ("Install ALL changed/new", self.confirm_install),
            ("Restore backup", self.confirm_restore),
        ]:
            btn = tk.Button(bar, text=title, padx=10, command=task)
            btn.pack(side="left", padx=5)
            self.buttons.append(btn)
        self.log("App folder: " + str(ROOT))
        self.log("Only root-level .py files are eligible. Review all changes first.")

    def log(self, line):
        self.root.after(0, lambda: (self.logbox.insert("end", str(line) + "\n"),
                                    self.logbox.see("end")))

    def check(self, log):
        update(log, False)
        self.last_check = True

    def confirm_install(self):
        if not self.last_check:
            messagebox.showwarning("Check first", "Click Check updates before installing.")
            return
        if messagebox.askyesno("Install ALL", "Close the main editor first. This replaces ALL changed/new Python files. Have you reviewed the changes and made a separate backup?"):
            self.start(lambda log: update(log, True))

    def confirm_restore(self):
        if messagebox.askyesno("Restore", "Close the main editor first. Restore the latest backup?"):
            self.start(restore)

    def start(self, task):
        for b in self.buttons:
            b.configure(state="disabled")
        def work():
            try:
                task(self.log)
            except Exception as exc:
                self.log("ERROR: " + str(exc))
            finally:
                self.root.after(0, lambda: [b.configure(state="normal") for b in self.buttons])
        threading.Thread(target=work, daemon=True).start()

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    UI().run()
