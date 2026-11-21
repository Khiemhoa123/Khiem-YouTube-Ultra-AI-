# -*- coding: utf-8 -*-
"""Khiem YouTube manual GitHub updater. No unattended installation."""
from pathlib import Path
import ast
import datetime
import hashlib
import json
import os
import shutil
import sys
import importlib.util
import subprocess
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox

ROOT = Path(__file__).resolve().parent
REPO = "https://github.com/Khiemhoa123/Khiem-YouTube-Ultra-AI-.git"
BACKUPS = ROOT / "_AUTO_UPDATE_BACKUPS"
SKIP = set()
KEEP = {"khiem_settings.json", "project_queue_v11.json"}

# Conservative cleanup: only unmistakable disposable artifacts, never source,
# launchers, models, settings, project media, or unknown files.
CLEAN_SUFFIXES = (".pyc", ".pyo", ".tmp", ".khiem_new")
CLEAN_NAMES = {"__pycache__"}
CLEAN_ARCHIVE = ROOT / "_CLEANUP_ARCHIVE"

def cleanup_candidates():
    found = []
    for p in ROOT.iterdir():
        if p.is_symlink() or p.name in {BACKUPS.name, CLEAN_ARCHIVE.name}:
            continue
        if p.is_dir() and p.name in CLEAN_NAMES:
            found.append(p)
        elif p.is_file() and p.name.lower().endswith(CLEAN_SUFFIXES):
            found.append(p)
    return found

def git(*args, cwd=None):
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    p = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", timeout=180,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if p.returncode:
        raise RuntimeError(p.stderr[-1000:] or "Git failed. Sign in with Git Credential Manager.")
    return p.stdout.strip()

def check_file(src):
    if src.is_symlink() or src.suffix.lower() != ".py":
        raise ValueError("Unsafe source file: " + src.name)
    ast.parse(src.read_text(encoding="utf-8-sig"), filename=str(src))

class UI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("KHIÊM YOUTUBE | CẬP NHẬT AN TOÀN")
        self.root.geometry("820x630")
        self.root.minsize(680, 520)
        self.repo_dir = None
        self.temp = None
        self.revision = ""
        self.candidates = []
        self.selected = {}
        self.busy = False
        self.mode = tk.StringVar(value="safe")
        self.backup = tk.BooleanVar(value=True)
        self.verify = tk.BooleanVar(value=True)
        self.restart = tk.BooleanVar(value=False)
        self.cleanup_enabled = tk.BooleanVar(value=False)
        ttk.Label(self.root, text="CẬP NHẬT KHIÊM YOUTUBE",
                  font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=16, pady=(14, 5))
        ttk.Label(self.root, text="Xem thay đổi, chọn file và xác nhận trước khi cài. Không cập nhật khi đang xuất video.").pack(anchor="w", padx=16)
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=16, pady=12)
        self.check_btn = ttk.Button(bar, text="KIỂM TRA GITHUB", command=self.check)
        self.check_btn.pack(side="left", padx=(0, 8))
        self.install_btn = ttk.Button(bar, text="CẬP NHẬT ĐÃ CHỌN", command=self.install, state="disabled")
        self.install_btn.pack(side="left", padx=(0, 8))
        ttk.Button(bar, text="KHÔI PHỤC BẢN CŨ", command=self.restore).pack(side="left")
        self.status = tk.StringVar(value="Chưa kiểm tra cập nhật.")
        ttk.Label(self.root, textvariable=self.status, wraplength=780).pack(anchor="w", padx=16)
        options = ttk.LabelFrame(self.root, text="Tùy chọn cập nhật")
        options.pack(fill="x", padx=16, pady=8)
        for value, label in [("safe", "An toàn: chỉ cập nhật file đang có"),
                             ("custom", "Tùy chỉnh: tự tích chọn file"),
                             ("full", "Đầy đủ: cho phép thêm module Python mới")]:
            ttk.Radiobutton(options, text=label, variable=self.mode, value=value,
                            command=self.refresh).pack(anchor="w", padx=8, pady=2)
        ttk.Checkbutton(options, text="Sao lưu trước khi cài (bắt buộc)", variable=self.backup,
                        state="disabled").pack(anchor="w", padx=8)
        ttk.Checkbutton(options, text="Kiểm tra cú pháp và nội dung (bắt buộc)", variable=self.verify,
                        state="disabled").pack(anchor="w", padx=8)
        ttk.Checkbutton(options, text="Khởi động lại sau khi cập nhật (đóng phần mềm rồi mở thủ công để an toàn)",
                        variable=self.restart, state="disabled").pack(anchor="w", padx=8)
        ttk.Checkbutton(options, text="Dọn dẹp file tạm sau khi cập nhật (xem trước và xác nhận riêng)", variable=self.cleanup_enabled).pack(anchor="w", padx=8, pady=3)
        ttk.Button(bar, text="XEM & DỌN FILE TẠM", command=self.cleanup_preview).pack(side="left", padx=(8, 0))
        ttk.Label(self.root, text="Danh sách file Python thay đổi").pack(anchor="w", padx=16)
        frame = ttk.Frame(self.root)
        frame.pack(fill="both", expand=True, padx=16, pady=6)
        canvas = tk.Canvas(frame, highlightthickness=0)
        scroll = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        self.file_frame = ttk.Frame(canvas)
        self.file_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.file_frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.logbox = tk.Text(self.root, height=6, state="disabled")
        self.logbox.pack(fill="x", padx=16, pady=(0, 12))
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def log(self, line):
        def append():
            self.logbox.configure(state="normal")
            self.logbox.insert("end", str(line) + "\n")
            self.logbox.see("end")
            self.logbox.configure(state="disabled")
        self.root.after(0, append)

    def task(self, work):
        if self.busy:
            return
        self.busy = True
        self.check_btn.configure(state="disabled")
        self.install_btn.configure(state="disabled")
        def run():
            try:
                work()
            except Exception as exc:
                self.log("LỖI: " + str(exc))
                self.root.after(0, lambda: messagebox.showerror("Cập nhật", str(exc)))
            finally:
                self.root.after(0, self.done)
        threading.Thread(target=run, daemon=True).start()

    def done(self):
        self.busy = False
        self.check_btn.configure(state="normal")
        self.refresh()

    def check(self):
        def work():
            if not shutil.which("git"):
                raise RuntimeError("Cần cài Git for Windows và đăng nhập tài khoản có quyền xem repository.")
            if self.temp:
                self.temp.cleanup()
            self.temp = tempfile.TemporaryDirectory(prefix="khiem_update_")
            self.repo_dir = Path(self.temp.name) / "repo"
            self.log("Đang tải danh sách mã nguồn từ GitHub...")
            git("clone", "--quiet", "--depth", "1", "--branch", "main", REPO, str(self.repo_dir))
            self.revision = git("rev-parse", "HEAD", cwd=self.repo_dir)
            result = []
            for src in sorted(self.repo_dir.glob("*.py")):
                if src.name in SKIP or src.is_symlink():
                    continue
                dst = ROOT / src.name
                if dst.is_symlink():
                    continue
                check_file(src)
                if not dst.exists() or hashlib.sha256(src.read_bytes()).digest() != hashlib.sha256(dst.read_bytes()).digest():
                    result.append((src, dst, dst.exists()))
            self.candidates = result
            self.root.after(0, self.refresh)
            self.root.after(0, lambda: self.status.set(
                f"GitHub {self.revision[:12]} | {len(result)} file thay đổi | Thư mục: {ROOT}"))
            self.log("Đã kiểm tra: " + str(len(result)) + " file thay đổi.")
        self.task(work)

    def refresh(self):
        for child in self.file_frame.winfo_children():
            child.destroy()
        self.selected = {}
        for src, dst, exists in self.candidates:
            allowed = exists or self.mode.get() == "full"
            checked = allowed and self.mode.get() != "custom"
            var = tk.BooleanVar(value=checked)
            self.selected[src.name] = var
            label = ("THAY ĐỔI  " if exists else "FILE MỚI   ") + src.name
            ttk.Checkbutton(self.file_frame, text=label, variable=var,
                            state=("normal" if allowed else "disabled")).pack(anchor="w", pady=2)
        self.install_btn.configure(state="normal" if self.candidates and not self.busy else "disabled")

    def install(self):
        if self.busy or not self.repo_dir:
            return
        selected = [(s, d, exists) for s, d, exists in self.candidates
                    if self.selected.get(s.name) and self.selected[s.name].get()
                    and (exists or self.mode.get() == "full")]
        if not selected:
            messagebox.showinfo("Cập nhật", "Chưa chọn file để cập nhật.")
            return
        # Install only when Vietsub modules are being updated, with user consent.
        needs_translation = any(src.name in ("smart_vietsub_v11.py", "khiem_ui.py")
                                for src, _, _ in selected)
        install_translation = needs_translation and importlib.util.find_spec("deep_translator") is None
        summary = "\n".join(("Thay: " if exists else "Thêm: ") + s.name for s, _, exists in selected)
        if not messagebox.askyesno("XÁC NHẬN CẬP NHẬT",
            "Hãy đóng cửa sổ Khiêm YouTube đang chạy và đảm bảo không có dự án xuất MP4/CapCut.\n\n"
            "Sẽ sao lưu rồi cập nhật các file:\n" + summary[:2200] +
            ("\n\nSẽ tự cài deep-translator qua pip (cần Internet) trong đúng Python của trình cập nhật." if install_translation else "") +
            "\n\nĐã đóng phần mềm và muốn tiếp tục?"):
            return
        def work():
            if install_translation:
                self.log("Đang cài deep-translator cho Python đang chạy trình cập nhật...")
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "deep-translator"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                    timeout=240,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if result.returncode != 0:
                    raise RuntimeError("Không cài được deep-translator. Chưa thay file phần mềm. "
                                       + (result.stderr or result.stdout)[-1400:])
                self.log("Đã cài deep-translator thành công.")
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            backup = BACKUPS / stamp
            backup.mkdir(parents=True, exist_ok=False)
            manifest = {"revision": self.revision, "files": [d.name for _, d, _ in selected],
                        "created": [d.name for _, d, exists in selected if not exists]}
            staged = []
            replaced = []
            try:
                for src, dst, exists in selected:
                    check_file(src)
                    if exists:
                        shutil.copy2(dst, backup / dst.name)
                    tmp = dst.with_name(dst.name + ".khiem_new")
                    shutil.copy2(src, tmp)
                    staged.append(tmp)
                    check_file(tmp.with_suffix(".py") if False else src)
                (backup / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
                for (src, dst, _), tmp in zip(selected, staged):
                    os.replace(tmp, dst)
                    replaced.append(dst)
                self.log("THÀNH CÔNG. Sao lưu: " + str(backup))
                if self.cleanup_enabled.get():
                    self.root.after(0, self.cleanup_preview)
                self.root.after(0, lambda: messagebox.showinfo(
                    "Hoàn tất", "Đã cập nhật. Hãy mở lại Khiêm YouTube để sử dụng bản mới."))
            except Exception:
                for dst in replaced:
                    original = backup / dst.name
                    if original.exists():
                        shutil.copy2(original, dst)
                    elif dst.exists():
                        dst.unlink()
                raise
            finally:
                for tmp in staged:
                    tmp.unlink(missing_ok=True)
        self.task(work)

    def cleanup_preview(self):
        if self.busy:
            return
        items = cleanup_candidates()
        if not items:
            messagebox.showinfo("Dọn dẹp", "Không có file tạm an toàn cần dọn. Các file Python, BAT và dữ liệu dự án được giữ nguyên.")
            return
        window = tk.Toplevel(self.root)
        window.title("Xem trước dọn dẹp | không xóa vĩnh viễn")
        window.geometry("650x430")
        ttk.Label(window, text="Chỉ chuyển file tạm vào kho lưu trữ, không xóa mã nguồn.", wraplength=600).pack(anchor="w", padx=12, pady=10)
        pane = ttk.Frame(window)
        pane.pack(fill="both", expand=True, padx=12)
        listbox = tk.Listbox(pane, selectmode="extended")
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(pane, command=listbox.yview)
        scrollbar.pack(side="right", fill="y")
        listbox.configure(yscrollcommand=scrollbar.set)
        for item in items:
            listbox.insert("end", item.name + ("/" if item.is_dir() else ""))
        listbox.select_set(0, "end")
        def execute():
            indices = listbox.curselection()
            chosen = [items[i] for i in indices]
            if not chosen:
                return
            if not messagebox.askyesno("Xác nhận dọn dẹp",
                "Đã đóng phần mềm chính và dừng mọi dự án?\\n\\n"
                + "Chuyển " + str(len(chosen)) + " mục vào kho lưu trữ?\\n"
                + "Không xóa vĩnh viễn, có thể khôi phục thủ công.", parent=window):
                return
            stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            dest = CLEAN_ARCHIVE / stamp
            dest.mkdir(parents=True, exist_ok=False)
            moved = []
            try:
                for item in chosen:
                    # Recheck allowlist and root before moving.
                    if item not in cleanup_candidates() or item.parent != ROOT:
                        continue
                    shutil.move(str(item), str(dest / item.name))
                    moved.append(item.name)
                (dest / "cleanup_manifest.json").write_text(
                    json.dumps({"moved": moved}, ensure_ascii=False, indent=2),
                    encoding="utf-8")
                self.log("Đã lưu trữ " + str(len(moved)) + " file tạm tại " + str(dest))
                window.destroy()
                messagebox.showinfo("Dọn dẹp", "Đã chuyển " + str(len(moved)) + " mục vào: " + str(dest))
            except Exception as exc:
                messagebox.showerror("Dọn dẹp", str(exc), parent=window)
        ttk.Button(window, text="CHUYỂN MỤC ĐÃ CHỌN VÀO KHO LƯU TRỮ", command=execute).pack(pady=10)

    def restore(self):
        if self.busy:
            return
        backups = sorted(p for p in BACKUPS.glob("*") if (p / "manifest.json").is_file()) if BACKUPS.exists() else []
        if not backups:
            messagebox.showinfo("Khôi phục", "Chưa có bản sao lưu.")
            return
        folder = backups[-1]
        if not messagebox.askyesno("Khôi phục", "Đóng phần mềm trước. Khôi phục bản " + folder.name + "?"):
            return
        def work():
            data = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
            created = set(data.get("created", []))
            for name in data["files"]:
                if Path(name).name != name or not name.endswith(".py"):
                    raise ValueError("Backup không hợp lệ")
                dst = ROOT / name
                if name in created:
                    dst.unlink(missing_ok=True)
                else:
                    shutil.copy2(folder / name, dst)
            self.log("Đã khôi phục. Mở lại phần mềm.")
        self.task(work)

    def close(self):
        if self.busy:
            messagebox.showwarning("Đang xử lý", "Đợi cập nhật hoặc kiểm tra hoàn tất.")
            return
        if self.temp:
            self.temp.cleanup()
        self.root.destroy()

if __name__ == "__main__":
    UI().root.mainloop()
