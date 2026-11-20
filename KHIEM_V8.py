
# KHIEM YOUTUBE V8.0 ULTRA PRO
# Project Manager - Stage 1
# Safe launcher, backup and diagnostics

import os
import sys
import json
import shutil
import subprocess
import threading
import tkinter as tk

from pathlib import Path
from datetime import datetime
from tkinter import messagebox

ROOT = Path(__file__).resolve().parent
BACKUP_ROOT = ROOT / "_V8_BACKUPS"
SETTINGS = ROOT / "v8_settings.json"

SOURCE_FILES = [
    "app.py",
    "semantic.py",
    "capcut.py",
    "khiem_ui.py",
    "smart_v71.py",
    "turbo_cache.py",
    "quality_v72.py",
    "khiem_settings.json",
    "khiem_manager_settings.json",
]

REQUIRED = [
    "app.py",
    "semantic.py",
    "capcut.py",
    "khiem_ui.py",
    "quality_v72.py",
]

BG = "#0d1521"
PANEL = "#1b293a"
TEXT = "#f1f5f9"
MUTED = "#a8b6c8"
ACCENT = "#21c8bb"


def load_settings():
    if SETTINGS.exists():
        try:
            return json.loads(
                SETTINGS.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            pass
    return {"last_action": ""}


def save_settings(data):
    temp = SETTINGS.with_suffix(".json.tmp")
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    temp.replace(SETTINGS)


def verify_sources():
    missing = []

    for name in REQUIRED:
        if not (ROOT / name).is_file():
            missing.append(name)

    if not (ROOT / "template").is_dir():
        missing.append("template/")

    return missing


def create_backup():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = BACKUP_ROOT / stamp
    destination.mkdir(parents=True, exist_ok=False)

    copied = []

    for name in SOURCE_FILES:
        source = ROOT / name
        if source.is_file():
            shutil.copy2(source, destination / name)
            copied.append(name)

    # Back up CapCut template as well.
    template = ROOT / "template"
    if template.is_dir():
        shutil.copytree(
            template,
            destination / "template"
        )
        copied.append("template/")

    manifest = {
        "created_at": datetime.now().isoformat(),
        "source": str(ROOT),
        "files": copied,
    }

    (destination / "manifest.json").write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    return destination


def launch_python(filename):
    path = ROOT / filename

    if not path.is_file():
        raise FileNotFoundError(filename)

    subprocess.Popen(
        [sys.executable, str(path)],
        cwd=str(ROOT),
        creationflags=getattr(
            subprocess,
            "CREATE_NEW_CONSOLE",
            0
        )
    )


def launch_main():
    launcher = ROOT / "MO_KHIEM_YOUTUBE.bat"

    if launcher.is_file() and os.name == "nt":
        os.startfile(str(launcher))
        return

    launch_python("khiem_ui.py")


class KhiemV8:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("KHIÊM YOUTUBE V8.0 ULTRA PRO")
        self.root.geometry("900x620")
        self.root.minsize(750, 540)
        self.root.configure(bg=BG)

        self.settings = load_settings()
        self.busy = False

        self.build()
        self.check()

    def log(self, text):
        self.output.configure(state="normal")
        self.output.insert("end", text + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def build(self):
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=28, pady=(24, 16))

        tk.Label(
            header,
            text="KHIÊM YOUTUBE",
            font=("Segoe UI", 25, "bold"),
            fg=TEXT,
            bg=BG
        ).pack(anchor="w")

        tk.Label(
            header,
            text="V8.0 ULTRA PRO  |  PROJECT MANAGER",
            font=("Segoe UI", 10),
            fg=ACCENT,
            bg=BG
        ).pack(anchor="w", pady=5)

        tk.Label(
            header,
            text="Giữ nguyên bộ xuất CapCut hiện tại",
            fg=MUTED,
            bg=BG
        ).pack(anchor="w")

        body = tk.Frame(
            self.root,
            bg=PANEL,
            padx=22,
            pady=20
        )
        body.pack(
            fill="both",
            expand=True,
            padx=28,
            pady=(0, 24)
        )

        tk.Label(
            body,
            text="QUẢN LÝ PHẦN MỀM",
            fg=TEXT,
            bg=PANEL,
            font=("Segoe UI", 13, "bold")
        ).pack(anchor="w", pady=(0, 14))

        actions = tk.Frame(body, bg=PANEL)
        actions.pack(fill="x")

        self.add_button(
            actions,
            "KIỂM TRA MÃ NGUỒN",
            self.check
        )

        self.add_button(
            actions,
            "SAO LƯU PHẦN MỀM",
            self.backup
        )

        self.add_button(
            actions,
            "MỞ PHẦN MỀM CHÍNH",
            self.open_main
        )

        self.add_button(
            actions,
            "MỞ QUALITY CONTROL",
            self.open_quality
        )

        self.add_button(
            actions,
            "MỞ THƯ MỤC V8",
            self.open_folder
        )

        tk.Label(
            body,
            text="NHẬT KÝ HOẠT ĐỘNG",
            fg=TEXT,
            bg=PANEL,
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", pady=(22, 8))

        self.output = tk.Text(
            body,
            height=13,
            bg="#101b2a",
            fg="#c7f9ee",
            insertbackground="white",
            relief="flat",
            font=("Consolas", 10),
            padx=12,
            pady=12,
            state="disabled"
        )
        self.output.pack(fill="both", expand=True)

    def add_button(self, parent, title, callback):
        tk.Button(
            parent,
            text=title,
            command=callback,
            bg=ACCENT,
            fg="#071319",
            activebackground="#64e1d6",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=12,
            pady=10
        ).pack(
            fill="x",
            pady=4
        )

    def check(self):
        missing = verify_sources()

        self.log("Đang kiểm tra thành phần V8.0...")

        if missing:
            for name in missing:
                self.log("THIẾU: " + name)

            self.log(
                "Chưa đủ thành phần để chạy phần mềm chính."
            )
        else:
            self.log("ĐÃ CÓ ĐỦ CÁC THÀNH PHẦN BẮT BUỘC.")
            self.log("Bộ xuất CapCut chưa bị thay đổi.")

        self.log("-" * 46)

    def backup(self):
        if self.busy:
            return

        self.busy = True
        self.log("Đang sao lưu mã nguồn...")

        def worker():
            try:
                destination = create_backup()
                self.root.after(
                    0,
                    lambda: self.log(
                        "SAO LƯU THÀNH CÔNG: "
                        + str(destination)
                    )
                )
            except Exception as error:
                msg = str(error)
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "Lỗi sao lưu", msg
                    )
                )
            finally:
                self.root.after(
                    0,
                    self.finish_backup
                )

        threading.Thread(
            target=worker,
            daemon=True
        ).start()

    def finish_backup(self):
        self.busy = False

    def open_main(self):
        try:
            launch_main()
            self.log("Đã yêu cầu mở phần mềm chính.")
            self.settings["last_action"] = "main"
            save_settings(self.settings)
        except Exception as error:
            messagebox.showerror(
                "Không mở được phần mềm",
                str(error)
            )

    def open_quality(self):
        try:
            launch_python("quality_v72.py")
            self.log("Đã yêu cầu mở Quality Control.")
        except Exception as error:
            messagebox.showerror(
                "Không mở được Quality Control",
                str(error)
            )

    def open_folder(self):
        if os.name == "nt":
            os.startfile(str(ROOT))
        else:
            self.log("Thư mục: " + str(ROOT))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    KhiemV8().run()
