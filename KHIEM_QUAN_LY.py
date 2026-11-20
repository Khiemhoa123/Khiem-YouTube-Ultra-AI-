
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from datetime import datetime
import threading
import subprocess
import shutil
import json
import os

ROOT = Path(__file__).resolve().parent
SETTINGS = ROOT / "khiem_manager_settings.json"
LAUNCHER = ROOT / "MO_KHIEM_YOUTUBE.bat"

def read_settings():
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}

class Manager:
    def __init__(self):
        self.win = tk.Tk()
        self.win.title("KHIEM YOUTUBE | PROJECT MANAGER")
        self.win.geometry("780x520")
        self.win.configure(bg="#101722")
        self.data = read_settings()
        self.working = False

        self.backup_dir = tk.StringVar(
            value=self.data.get(
                "backup_dir",
                str(ROOT.parent / "KHIEM_BACKUPS")
            )
        )
        self.last_project = tk.StringVar(
            value=self.data.get("last_project", "")
        )

        self.build()

    def label(self, parent, value, size=10):
        return tk.Label(
            parent, text=value,
            bg="#1b2635", fg="#f1f5fa",
            font=("Segoe UI", size)
        )

    def button(self, parent, value, action):
        return tk.Button(
            parent, text=value, command=action,
            bg="#23c7b7", fg="#101722",
            font=("Segoe UI", 10, "bold"),
            relief="flat", padx=12, pady=8
        )

    def build(self):
        tk.Label(
            self.win,
            text="KHIÊM YOUTUBE",
            bg="#101722", fg="white",
            font=("Segoe UI", 23, "bold")
        ).pack(anchor="w", padx=24, pady=(18, 0))

        tk.Label(
            self.win,
            text="PROJECT MANAGER | GIAI ĐOẠN 1",
            bg="#101722", fg="#23c7b7",
            font=("Segoe UI", 10)
        ).pack(anchor="w", padx=24, pady=(0, 18))

        panel = tk.Frame(
            self.win, bg="#1b2635", padx=18, pady=18
        )
        panel.pack(fill="both", expand=True, padx=24)

        self.label(
            panel, "Thư mục sao lưu", 11
        ).pack(anchor="w")

        row = tk.Frame(panel, bg="#1b2635")
        row.pack(fill="x", pady=(5, 16))

        tk.Entry(
            row, textvariable=self.backup_dir,
            font=("Segoe UI", 10)
        ).pack(side="left", fill="x", expand=True)

        self.button(
            row, "Chọn",
            self.choose_backup
        ).pack(side="left", padx=6)

        self.label(
            panel, "Tên dự án đang làm", 11
        ).pack(anchor="w")

        tk.Entry(
            panel, textvariable=self.last_project,
            font=("Segoe UI", 10)
        ).pack(fill="x", pady=(5, 16))

        actions = tk.Frame(panel, bg="#1b2635")
        actions.pack(fill="x")

        self.button(
            actions, "LƯU THIẾT LẬP",
            self.save
        ).pack(side="left", padx=(0, 8))

        self.button(
            actions, "SAO LƯU V6.9",
            self.backup
        ).pack(side="left", padx=(0, 8))

        self.button(
            actions, "MỞ V6.9",
            self.launch
        ).pack(side="left")

        self.status = tk.StringVar(value="Sẵn sàng")
        self.label(
            panel, "Trạng thái", 11
        ).pack(anchor="w", pady=(25, 6))

        tk.Label(
            panel, textvariable=self.status,
            bg="#1b2635", fg="#23c7b7",
            anchor="w", justify="left",
            wraplength=680,
            font=("Segoe UI", 10)
        ).pack(fill="x")

        tk.Label(
            self.win,
            text="Bản V6.9 gốc không bị chỉnh sửa.",
            bg="#101722", fg="#a9b8c9",
            font=("Segoe UI", 10)
        ).pack(anchor="w", padx=24, pady=12)

    def choose_backup(self):
        folder = filedialog.askdirectory()
        if folder:
            self.backup_dir.set(folder)

    def save(self):
        try:
            data = {
                "backup_dir": self.backup_dir.get(),
                "last_project": self.last_project.get()
            }
            SETTINGS.write_text(
                json.dumps(
                    data, ensure_ascii=False, indent=2
                ),
                encoding="utf-8"
            )
            self.status.set("Đã lưu thiết lập.")
        except Exception as error:
            messagebox.showerror("Lỗi lưu", str(error))

    def backup(self):
        if self.working:
            return

        source = ROOT.resolve()
        destination_root = Path(
            self.backup_dir.get()
        ).expanduser().resolve()

        # Không cho đặt thư mục sao lưu bên trong nguồn.
        if (
            destination_root == source
            or source in destination_root.parents
        ):
            messagebox.showerror(
                "Đường dẫn không hợp lệ",
                "Hãy chọn thư mục sao lưu nằm ngoài "
                "thư mục phần mềm V6.9."
            )
            return

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = destination_root / (
            "V6_9_BACKUP_" + stamp
        )

        self.save()
        self.working = True
        self.status.set("Đang sao lưu, vui lòng chờ...")

        def job():
            try:
                destination_root.mkdir(
                    parents=True, exist_ok=True
                )

                shutil.copytree(
                    source, target,
                    ignore=shutil.ignore_patterns(
                        "__pycache__", "*.pyc"
                    )
                )
                result = "Sao lưu hoàn tất:\n" + str(target)
            except Exception as error:
                result = "Sao lưu thất bại: " + str(error)
            finally:
                def finish():
                    self.working = False
                    self.status.set(result)

                self.win.after(0, finish)

        threading.Thread(
            target=job, daemon=True
        ).start()

    def launch(self):
        if not LAUNCHER.is_file():
            messagebox.showerror(
                "Thiếu file",
                "Không tìm thấy MO_KHIEM_YOUTUBE.bat"
            )
            return

        self.save()
        try:
            subprocess.Popen(
                ["cmd.exe", "/c", str(LAUNCHER)],
                cwd=str(ROOT),
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            self.status.set("Đã yêu cầu mở V6.9.")
        except Exception as error:
            messagebox.showerror(
                "Không mở được", str(error)
            )

    def run(self):
        self.win.mainloop()

if __name__ == "__main__":
    Manager().run()
