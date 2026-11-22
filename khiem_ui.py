
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font as tkfont
from pathlib import Path
import threading
import json
import os
import re
import traceback
import time
import shutil
import tempfile
from project_queue_v11 import ProjectQueue
from queue_precheck_v11 import inspect as inspect_project

import app as engine

try:
    import customtkinter as ctk
    ctk.set_appearance_mode("dark")
    CTK_READY = True
except ImportError:
    ctk = None
    CTK_READY = False


COLORS = {
    "bg": "#071321",
    "panel": "#102437",
    "input": "#1C354B",
    "text": "#F2F6FC",
    "muted": "#AAB9CA",
    "accent": "#13D5F5"
}

DEFAULTS = {
    "project_folder": "",
    "voice": "",
    "interview_folder": "",
    "interview_max_seconds": "30",
    "interview_enabled": False,
    "txt": "",
    "images": "",
    "videos": "",
    "out": "",
    "draft_root": str(
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "CapCut/User Data/Projects/com.lveditor.draft"
    ),
    "sample": "",
    "name": "New Project",
    "speed": "Smart",
    "smart_timeline": "1",
    "min_video_percent": "40",
    "target_video_percent": "60",
    "vn": "1",
    "an": "3",
    "videomode": "Cố định",
    "videotime": "5",
    "imagemode": "Cố định",
    "imagetime": "5",
    "background": "Nền mờ",
    "blur": "30",
    "transition": "Dissolve",
    "transition_time": "0.5",
    "iz": "110",
    "vz": "100",
    "res": "3840x2160",
    "fps": "30",
    "gpu": True,
    "ai": True,
    "align": True,
    "effects": ["Zoom in", "Zoom out"]
}


class KhiemYoutube:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("KHIEM YOUTUBE V11.3 | ULTRA AI STUDIO")
        self.root.geometry("1240x850")
        self.root.minsize(1000, 650)
        self.root.configure(bg=COLORS["bg"])
        self.root.option_add("*highlightThickness", 0)

        self.settings_file = (
            Path(__file__).resolve().parent
            / "khiem_settings.json"
        )

        self.vars = {}
        saved = self.load_settings()

        for key, default in DEFAULTS.items():
            if key in ("gpu", "ai", "align", "effects", "interview_enabled"):
                continue
            self.vars[key] = tk.StringVar(
                value=saved.get(key, default)
            )

        self.gpu = tk.BooleanVar(
            value=saved.get("gpu", True)
        )
        self.ai = tk.BooleanVar(
            value=saved.get("ai", True)
        )
        self.align = tk.BooleanVar(
            value=saved.get("align", True)
        )

        chosen = saved.get(
            "effects", DEFAULTS["effects"]
        )

        self.effects = {
            effect: tk.BooleanVar(
                value=effect in chosen
            )
            for effect in (
                "Zoom in", "Zoom out", "Tĩnh"
            )
        }

        self.interview_enabled = tk.BooleanVar(value=saved.get("interview_enabled", False))
        self.interview_enabled.trace_add("write", lambda *_: self.save_settings())
        self.busy = False
        self.queue = ProjectQueue(Path(__file__).resolve().parent / "project_queue_v11.json")
        self.queue_running = False
        self.active_job = None
        self.queue_mode = False
        self.editing_job_id = None
        self.queue_shutdown = tk.BooleanVar(value=False)
        self.queue_shutdown_confirmed = False
        self.progress = tk.DoubleVar(value=0)
        self.run_started_at = None
        self.run_timer_active = False
        self.run_elapsed = tk.StringVar(value="Thời gian chạy: 00:00:00")
        self.run_stage = tk.StringVar(value="Trạng thái: Chưa chạy")
        self.buttons = []

        self.configure_style()
        self.build_interface()

        for var in self.vars.values():
            var.trace_add(
                "write",
                lambda *_: self.save_settings()
            )

        for var in [
            self.gpu, self.ai, self.align,
            *self.effects.values()
        ]:
            var.trace_add(
                "write",
                lambda *_: self.save_settings()
            )

        self.recovery_mode = ""
        self.recovery_project = ""
        self.recovery_last_stage = ""
        self.root.after(600, self.recovery_check)
        self.root.protocol(
            "WM_DELETE_WINDOW", self.close
        )

    def build_interview_audio_tab(self):
        """Standalone speaker MP3 extraction, separate from video editing."""
        tab = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(tab, text="05  INTERVIEW AUDIO")
        tab.columnconfigure(1, weight=1)
        self.ia_source = tk.StringVar()
        self.ia_output = tk.StringVar()
        from interview_token_store import load_token, save_token
        self.ia_token = tk.StringVar(value=load_token())
        self.ia_token.trace_add("write", lambda *_: save_token(self.ia_token.get()))
        self.ia_seconds = tk.IntVar(value=35)
        ttk.Label(tab, text="TÁCH GIỌNG INTERVIEW THÀNH MP3", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 5))
        ttk.Label(tab, text="Video phỏng vấn").grid(row=1, column=0, sticky="w")
        ttk.Entry(tab, textvariable=self.ia_source).grid(row=1, column=1, sticky="ew", padx=5, pady=2)
        ttk.Button(tab, text="Chọn video", command=self.ia_choose_video).grid(row=1, column=2)
        ttk.Label(tab, text="Thư mục xuất MP3").grid(row=2, column=0, sticky="w")
        ttk.Entry(tab, textvariable=self.ia_output).grid(row=2, column=1, sticky="ew", padx=5, pady=2)
        ttk.Button(tab, text="Chọn thư mục", command=self.ia_choose_output).grid(row=2, column=2)
        ttk.Label(tab, text="Hugging Face token").grid(row=3, column=0, sticky="w")
        ttk.Entry(tab, textvariable=self.ia_token, show="*").grid(row=3, column=1, sticky="ew", padx=5, pady=2)
        ttk.Label(tab, text="Đã lưu token", foreground=COLORS["muted"]).grid(row=3, column=2, sticky="w")

        ttk.Label(tab, text="Thời lượng mỗi MP3 (giây)").grid(row=5, column=0, sticky="w", pady=3)
        ttk.Spinbox(tab, from_=30, to=45, textvariable=self.ia_seconds, width=8).grid(row=5, column=1, sticky="w", padx=8)
        self.ia_button = ttk.Button(tab, text="PHÂN TÍCH VÀ NGHE THỬ", command=self.ia_start)
        self.ia_button.grid(row=6, column=0, columnspan=3, sticky="ew", pady=5)
        # V7: always-visible compact live timeline, above the preview list.
        self.ia_live_phase = tk.StringVar(value="Sẵn sàng phân tích")
        self.ia_live_window = tk.StringVar(value="Chưa quét video")
        self.ia_live_timer = tk.StringVar(value="00:00:00")
        live = ttk.LabelFrame(tab, text="TIẾN TRÌNH", padding=5)
        live.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(0, 3))
        live.columnconfigure(0, weight=1)
        ttk.Label(live, textvariable=self.ia_live_phase,
                  font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(live, textvariable=self.ia_live_timer,
                  font=("Consolas", 10, "bold")).grid(row=0, column=1, sticky="e")
        self.ia_live_bar = ttk.Progressbar(live, mode="indeterminate")
        self.ia_live_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=2)
        ttk.Label(live, textvariable=self.ia_live_window,
                  foreground=COLORS["muted"]).grid(row=2, column=0, columnspan=2, sticky="w")
        # V6: review MP3 previews before copying any selected voice to output.
        self.ia_previews = {}
        self.ia_preview_dir = None
        self.ia_player = None
        review = ttk.LabelFrame(tab, text="NGHE THỬ VÀ XUẤT", padding=5)
        review.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(0, 3))
        review.columnconfigure(0, weight=1)
        self.ia_voice_list = ttk.Treeview(review, columns=("length", "file"),
                                          show="headings", height=3, selectmode="extended")
        self.ia_voice_list.heading("length", text="Thời lượng")
        self.ia_voice_list.heading("file", text="Giọng được AI nhận diện")
        self.ia_voice_list.column("length", width=110, stretch=False)
        self.ia_voice_list.column("file", width=260, stretch=True)
        self.ia_voice_list.grid(row=0, column=0, columnspan=3, sticky="ew")
        self.ia_play_button = ttk.Button(review, text="▶ Nghe",
                                         command=self.ia_play, state="disabled")
        self.ia_play_button.grid(row=1, column=0, sticky="w", pady=2)
        self.ia_stop_button = ttk.Button(review, text="■ Dừng",
                                         command=self.ia_stop_audio)
        self.ia_stop_button.grid(row=1, column=1, sticky="w", pady=2)
        self.ia_export_button = ttk.Button(review, text="Xuất MP3",
                                           command=self.ia_export_selected, state="disabled")
        self.ia_export_button.grid(row=1, column=2, sticky="e", pady=2)

        # Compact vertical workflow. The bar indicates activity, not a guessed percent.
        self.ia_status = tk.StringVar(value="Sẵn sàng")
        self.ia_elapsed = tk.StringVar(value="00:00:00")
        self.ia_files = tk.StringVar(value="0")
        self.ia_speakers = tk.StringVar(value="Chưa phân tích")
        self.ia_started = None
        self.ia_running = False
        self.ia_file_count = 0
        self.ia_stage_index = -1
        summary = ttk.LabelFrame(tab, text="TIẾN TRÌNH XỬ LÝ", padding=10)
        # Keep old progress widgets for callbacks, but hide the duplicate panel.
        summary.grid(row=9, column=0, columnspan=3, sticky="ew")
        summary.grid_remove()
        summary.columnconfigure(0, weight=1)
        ttk.Label(summary, textvariable=self.ia_status, font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(summary, text="Thời gian:", foreground=COLORS["muted"]).grid(row=0, column=1, padx=(16, 4))
        ttk.Label(summary, textvariable=self.ia_elapsed, font=("Consolas", 11, "bold")).grid(row=0, column=2)
        ttk.Label(summary, text="MP3:", foreground=COLORS["muted"]).grid(row=0, column=3, padx=(16, 4))
        ttk.Label(summary, textvariable=self.ia_files, font=("Segoe UI", 11, "bold")).grid(row=0, column=4)
        self.ia_progress = ttk.Progressbar(summary, mode="indeterminate")
        self.ia_progress.grid(row=1, column=0, columnspan=5, sticky="ew", pady=(9, 8))
        self.ia_steps = (
            "1. Nạp mô hình AI",
            "2. Trích xuất âm thanh",
            "3. Phân tích người nói",
            "4. Làm sạch và xuất MP3",
        )
        self.ia_step_labels = []
        for i, name in enumerate(self.ia_steps):
            lbl = ttk.Label(summary, text="○  " + name, foreground=COLORS["muted"])
            lbl.grid(row=i+2, column=0, columnspan=5, sticky="w", pady=2)
            self.ia_step_labels.append(lbl)
        ttk.Label(summary, text="Số người nói:").grid(row=6, column=0, sticky="w", pady=(7, 0))
        ttk.Label(summary, textvariable=self.ia_speakers).grid(row=6, column=1, columnspan=4, sticky="w", pady=(7, 0))
        details = ttk.LabelFrame(tab, text="NHẬT KÝ", padding=4)
        details.grid(row=10, column=0, columnspan=3, sticky="nsew")
        details.rowconfigure(0, weight=1)
        details.columnconfigure(0, weight=1)
        self.ia_log = tk.Text(details, height=4, wrap="word", font=("Consolas", 9), spacing1=3)
        self.ia_log.grid(row=0, column=0, sticky="nsew")
        ia_scroll = ttk.Scrollbar(details, orient="vertical", command=self.ia_log.yview)
        ia_scroll.grid(row=0, column=1, sticky="ns")
        self.ia_log.configure(yscrollcommand=ia_scroll.set)
        tab.rowconfigure(10, weight=1)


    def ia_choose_video(self):
        value = filedialog.askopenfilename(filetypes=[("Video", "*.mp4 *.mov *.mkv *.avi *.webm"), ("All files", "*.*")])
        if value:
            self.ia_source.set(value)
            if not self.ia_output.get():
                self.ia_output.set(str(Path(value).parent / "Interview_Audio"))

    def ia_choose_output(self):
        value = filedialog.askdirectory()
        if value: self.ia_output.set(value)

    def ia_start(self):
        source = self.ia_source.get().strip()
        output = self.ia_output.get().strip()
        token = self.ia_token.get().strip()
        if not Path(source).is_file() or not output or not token:
            messagebox.showerror("Interview Audio", "Chọn video, thư mục xuất và nhập Hugging Face token.")
            return
        try:
            seconds = int(self.ia_seconds.get())
            if not 30 <= seconds <= 45:
                raise ValueError("Chọn thời lượng từ 30 đến 45 giây.")
        except (ValueError, tk.TclError) as exc:
            messagebox.showerror("Interview Audio", str(exc))
            return
        self.ia_stop_audio()
        import shutil
        if self.ia_preview_dir:
            shutil.rmtree(self.ia_preview_dir, ignore_errors=True)
        self.ia_preview_dir = None
        self.ia_previews.clear()
        for item in self.ia_voice_list.get_children():
            self.ia_voice_list.delete(item)
        self.ia_play_button.configure(state="disabled")
        self.ia_export_button.configure(state="disabled")
        self.ia_button.configure(state="disabled")
        self.ia_log.delete("1.0", "end")
        self.ia_started = time.monotonic()
        self.ia_running = True
        self.ia_file_count = 0
        self.ia_files.set("0")
        self.ia_elapsed.set("Đã chạy: 00:00:00")
        self.ia_status.set("Đang chuẩn bị...")
        self.ia_speakers.set("Chưa phân tích")
        self.ia_stage_index = -1
        self.ia_render_steps()
        self.ia_progress.start(12)
        self.ia_live_phase.set("Đang chuẩn bị mô hình AI...")
        self.ia_live_window.set("Chưa quét video")
        self.ia_live_timer.set("00:00:00")
        self.ia_live_bar.start(12)
        self.ia_tick()
        def report(message):
            self.root.after(0, lambda msg=str(message): self.ia_on_message(msg))
        def work():
            try:
                from interview_audio import export_speakers
                import tempfile
                preview_dir = tempfile.mkdtemp(prefix="khiem_interview_review_")
                self.ia_preview_dir = preview_dir
                result = export_speakers(source, preview_dir, token, seconds, log=report)
                self.root.after(0, lambda data=dict(result): self.ia_ready(data))
                report(f"ĐÃ PHÂN TÍCH: {len(result)} giọng. Nghe thử và chọn giọng để xuất.")
            except Exception as exc:
                report("LỖI: " + str(exc))
            finally:
                self.root.after(0, self.ia_finish)
        threading.Thread(target=work, daemon=True).start()

    def ia_ready(self, results):
        from pathlib import Path
        from interview_audio import _duration
        self.ia_previews = dict(results)
        for key, path in results.items():
            try:
                seconds = _duration(path)
            except Exception:
                seconds = 0
            self.ia_voice_list.insert("", "end", iid=str(key),
                                      values=(f"{seconds:.1f} giây", Path(path).name))
        if results:
            first = next(iter(results))
            self.ia_voice_list.selection_set(first)
            self.ia_play_button.configure(state="normal")
            self.ia_export_button.configure(state="normal")
            self.ia_status.set("Đã phân tích. Hãy nghe thử và chọn giọng.")
        else:
            self.ia_status.set("Không có giọng đủ 30 giây để nghe thử.")

    def ia_stop_audio(self):
        player = getattr(self, "ia_player", None)
        if player is not None and player.poll() is None:
            player.terminate()
        self.ia_player = None

    def ia_play(self):
        selected = self.ia_voice_list.selection()
        if not selected:
            messagebox.showinfo("Interview Audio", "Hãy chọn một giọng để nghe thử.")
            return
        path = self.ia_previews.get(selected[0])
        if not path:
            return
        self.ia_stop_audio()
        import shutil
        import subprocess
        ffplay = shutil.which("ffplay")
        if ffplay:
            self.ia_player = subprocess.Popen(
                [ffplay, "-nodisp", "-autoexit", "-loglevel", "error", str(path)],
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            os.startfile(str(path))
            self.ia_on_message("Máy chưa có ffplay. Đã mở file bằng trình nghe MP3 mặc định.")

    def ia_export_selected(self):
        selected = self.ia_voice_list.selection()
        if not selected:
            messagebox.showwarning("Interview Audio", "Chọn ít nhất một giọng để xuất.")
            return
        import shutil
        output = Path(self.ia_output.get().strip())
        output.mkdir(parents=True, exist_ok=True)
        count = 0
        for key in selected:
            src = self.ia_previews.get(key)
            if not src or not Path(src).is_file():
                continue
            base = Path(src).name
            dest = output / base
            index = 2
            while dest.exists():
                dest = output / f"{Path(base).stem}_{index}.mp3"
                index += 1
            shutil.copy2(src, dest)
            count += 1
            self.ia_on_message(f"Đã xuất: {dest}")
        self.ia_files.set(str(count))
        messagebox.showinfo("Interview Audio", f"Đã xuất {count} MP3 vào:\\n{output}")

    def ia_tick(self):
        if not self.ia_running:
            return
        seconds = int(max(0, time.monotonic() - self.ia_started))
        clock = f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"
        self.ia_elapsed.set("Đã chạy: " + clock)
        self.ia_live_timer.set(clock)
        self.root.after(1000, self.ia_tick)

    def ia_render_steps(self):
        for i, label in enumerate(self.ia_step_labels):
            if i < self.ia_stage_index:
                label.configure(text="✓  " + self.ia_steps[i], foreground="#49C99A")
            elif i == self.ia_stage_index:
                label.configure(text="●  " + self.ia_steps[i], foreground="#39C6ED")
            else:
                label.configure(text="○  " + self.ia_steps[i], foreground=COLORS["muted"])

    def ia_on_message(self, message):
        # Separate each log event onto its own line, not a continuous string.
        self.ia_log.insert("end", message + "\n")
        self.ia_log.see("end")
        # The backend reports actual scan windows and model status.
        if "quét đoạn" in message or "quét cửa sổ" in message:
            self.ia_live_window.set(message)
            self.ia_live_phase.set("AI đang phân tích giọng nói")
        elif "AI xong đoạn" in message:
            self.ia_live_window.set(message)
            self.ia_live_phase.set("Đang kiểm tra các giọng đủ 30 giây")
        elif "Đã xuất" in message and "Speaker_" in message:
            self.ia_live_window.set(message)
            self.ia_live_phase.set("Đang chuẩn bị bản nghe thử")
        elif "Đang tải mô hình" in message:
            self.ia_live_phase.set("Đang nạp mô hình AI")
        elif "Video dài" in message:
            self.ia_live_window.set(message)
        stage = None
        if "Đang tải mô hình" in message or "Đã dùng lại mô hình" in message:
            stage = 0
        elif "quét đoạn" in message:
            stage = 1
        elif "AI xong đoạn" in message:
            stage = 2
        elif "Đã xuất" in message or "Đang xuất" in message:
            stage = 3
        if stage is not None:
            self.ia_stage_index = max(self.ia_stage_index, stage)
            self.ia_status.set(self.ia_steps[self.ia_stage_index][3:])
            self.ia_render_steps()
        if "AI xong đoạn" in message:
            self.ia_speakers.set(message)
        if "Đã xuất Speaker_" in message:
            self.ia_file_count += 1
            self.ia_files.set(str(self.ia_file_count))
        if message.startswith("ĐÃ PHÂN TÍCH:"):
            self.ia_live_phase.set("Phân tích xong. Chọn giọng để nghe thử")
            self.ia_live_window.set(message)
        if message.startswith("HOÀN THÀNH"):
            self.ia_status.set("Hoàn thành")
            self.ia_stage_index = len(self.ia_steps)
            self.ia_render_steps()
        elif message.startswith("LỖI:"):
            self.ia_status.set("Có lỗi, xem nhật ký")
        elif message.startswith("LỖI Speaker"):
            self.ia_status.set("Một người nói không đủ 30 giây, tiếp tục xử lý")

    def ia_finish(self):
        self.ia_running = False
        self.ia_progress.stop()
        self.ia_live_bar.stop()
        self.ia_button.configure(state="normal")

    def load_settings(self):
        try:
            return json.loads(
                self.settings_file.read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, ValueError):
            return {}

    def get_config(self):
        config = {
            key: var.get()
            for key, var in self.vars.items()
        }

        if config.get("project_folder", "").strip():
            folder = Path(config["project_folder"].strip())
            structured = (folder / "01 - Voice").is_dir() and (folder / "02 - Kich Ban TXT").is_dir()
            if structured:
                for key, dirname in (("voice", "01 - Voice"), ("txt", "02 - Kich Ban TXT"),
                                     ("images", "03 - Hinh Anh"), ("videos", "04 - Video"),
                                     ("interview_folder", "05 - Interview"), ("out", "06 - Xuat Video")):
                    config[key] = str(folder / dirname)
            else:
                for key in ("voice", "txt", "images", "videos"):
                    config[key] = str(folder)
        config.update({
            "interview_enabled": self.interview_enabled.get(),
            "gpu": self.gpu.get(),
            "ai": self.ai.get(),
            "align": self.align.get(),
            "effects": [
                key for key, var
                in self.effects.items()
                if var.get()
            ]
        })
        return config

    def save_settings(self):
        # Atomic replace avoids truncated JSON if power is lost mid-write.
        try:
            data = json.dumps(self.get_config(), ensure_ascii=False, indent=2)
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(prefix=".settings_", suffix=".tmp",
                                        dir=str(self.settings_file.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp, self.settings_file)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
        except (OSError, TypeError, ValueError):
            pass

    def recovery_write(self, state, stage=""):
        # Status journal only. Do not claim frame-accurate rendering resume.
        try:
            payload = {"state": state, "stage": str(stage)[:240],
                       "updated": time.time(), "mode": getattr(self, "recovery_mode", ""),
                       "project": getattr(self, "recovery_project", "")}
            target = self.settings_file.with_name("khiem_recovery.json")
            fd, temp = tempfile.mkstemp(prefix=".recovery_", suffix=".tmp", dir=str(target.parent))
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(payload, stream, ensure_ascii=False, indent=2)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temp, target)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
        except (OSError, ValueError):
            pass

    def recovery_check(self):
        target = self.settings_file.with_name("khiem_recovery.json")
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        interrupted = [j for j in self.queue.jobs if j.get("status") == "interrupted"]
        if data.get("state") != "running" and not interrupted:
            return
        project = data.get("project") or (interrupted[0].get("name") if interrupted else "Dự án")
        stage = data.get("stage") or "Không rõ giai đoạn"
        self.log("AUTO RECOVERY: phát hiện phiên làm việc bị gián đoạn: " + str(project))
        self.recovery_write("interrupted", stage)
        if interrupted:
            if messagebox.askyesno("AUTO RECOVERY", "Phát hiện %s dự án bị gián đoạn.\\n"
                                   "Dự án: %s\\nBước gần nhất: %s\\n\\n"
                                   "Chuyển các dự án này về trạng thái chờ để kiểm tra và chạy lại?\\n"
                                   "Không tự tiếp tục tại giây render cũ." %
                                   (len(interrupted), project, stage)):
                for job in interrupted:
                    self.queue.retry(job)
                self.queue_refresh()
                self.log("AUTO RECOVERY: đã đưa dự án gián đoạn về hàng chờ. Hãy kiểm tra trước khi chạy.")
        else:
            messagebox.showwarning("AUTO RECOVERY", "Phiên trước bị gián đoạn tại: %s\\n"
                                   "Bước gần nhất: %s\\n"
                                   "Vui lòng kiểm tra file đầu ra trước khi chạy lại." % (project, stage))

    def configure_style(self):
        c = COLORS
        style = ttk.Style(self.root)
        style.theme_use("clam")
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont", "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont"):
            tkfont.nametofont(name).configure(family="Segoe UI", size=11)
        self.root.option_add("*Font", ("Segoe UI", 11))
        style.configure(".", font=("Segoe UI", 11))
        style.configure("Treeview", font=("Segoe UI", 11), rowheight=28)
        style.configure("Treeview.Heading", font=("Segoe UI", 12, "bold"))

        # Consistent dark editor cards and native widget surfaces.
        style.configure("TLabelframe", background=c["panel"],
                        bordercolor="#28516B", lightcolor="#28516B",
                        darkcolor="#28516B", relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background=c["panel"],
                        foreground=c["accent"], font=("Segoe UI", 12, "bold"))
        style.configure("TCombobox", bordercolor="#28516B",
                        lightcolor=c["input"], darkcolor=c["input"],
                        arrowcolor=c["accent"])
        style.configure("TEntry", bordercolor="#28516B",
                        lightcolor=c["input"], darkcolor=c["input"],
                        insertcolor=c["text"])
        style.configure("TButton", bordercolor="#28516B",
                        lightcolor=c["input"], darkcolor=c["input"])
        style.configure("TPanedwindow", background=c["bg"])
        style.configure("Sash", sashthickness=6, background="#28516B")
        style.configure("Vertical.TScrollbar", background=c["input"],
                        troughcolor=c["bg"], arrowcolor=c["text"],
                        bordercolor=c["panel"], lightcolor=c["input"], darkcolor=c["input"])
        self.root.option_add("*TCombobox*Listbox.background", c["input"])
        self.root.option_add("*TCombobox*Listbox.foreground", c["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#087E9B")
        self.root.option_add("*TCombobox*Listbox.selectForeground", c["text"])


        style.configure(
            "TNotebook",
            background=c["bg"],
            borderwidth=0
        )
        style.configure(
            "TNotebook.Tab",
            background=c["panel"],
            foreground=c["muted"],
            padding=(28, 8),
            font=("Segoe UI", 12, "bold")
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", c["accent"])],
            foreground=[("selected", c["bg"])]
        )

        style.configure(
            "TFrame",
            background=c["panel"]
        )
        style.configure(
            "TLabel",
            background=c["panel"],
            foreground=c["text"],
            font=("Segoe UI", 11)
        )
        style.configure(
            "TCheckbutton",
            background=c["panel"],
            foreground=c["text"],
            font=("Segoe UI", 11)
        )
        style.map(
            "TCheckbutton",
            background=[("active", c["panel"])]
        )

        style.configure(
            "TEntry",
            fieldbackground=c["input"],
            foreground=c["text"],
            padding=4
        )
        style.configure(
            "TCombobox",
            fieldbackground=c["input"],
            background=c["input"],
            foreground=c["text"],
            padding=3
        )
        style.map(
            "TCombobox",
            fieldbackground=[
                ("readonly", c["input"])
            ],
            foreground=[
                ("readonly", c["text"])
            ]
        )

        style.configure(
            "TButton",
            background=c["input"],
            foreground=c["text"],
            padding=(8, 4),
            font=("Segoe UI", 11)
        )

        style.configure(
            "Accent.TButton",
            background=c["accent"],
            foreground=c["bg"],
            padding=(8, 4),
            font=("Segoe UI", 12, "bold")
        )
        style.map(
            "Accent.TButton",
            background=[
                ("active", "#53E0D3")
            ]
        )

        style.configure(
            "Horizontal.TProgressbar",
            troughcolor=c["input"],
            background=c["accent"]
        )

    def build_interface(self):
        header = tk.Frame(
            self.root,
            bg=COLORS["bg"],
            padx=25,
            pady=8
        )
        header.pack(fill="x")

        self.studio_button(header, "CẬP NHẬT GITHUB", self.open_safe_updater, primary=True).pack(side="right", anchor="n", padx=(8, 0))
        self.studio_button(header, "DỌN FILE RÁC", self.creator_cleanup_dialog).pack(side="right", anchor="n", padx=(8, 0))

        tk.Label(header, text="▣  KHIÊM YOUTUBE", bg=COLORS["bg"],
                 fg=COLORS["text"], font=("Segoe UI", 22, "bold")).pack(side="left")
        tk.Label(header, text="  |  ULTRA AI STUDIO v11.3", bg=COLORS["bg"],
                 fg=COLORS["accent"], font=("Segoe UI", 14, "bold")).pack(side="left")

        self.balance_status = tk.StringVar(value="Chưa có kết quả")
        self.scene_status = tk.StringVar(value="Chưa lập timeline")

        self.split = ttk.Panedwindow(self.root, orient="vertical")
        self.split.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.tabs = ttk.Notebook(self.split)
        self.split.add(self.tabs, weight=1)

        self.project_tab = ttk.Frame(
            self.tabs, padding=22
        )
        self.editor_tab = ttk.Frame(
            self.tabs, padding=22
        )

        self.tabs.add(
            self.project_tab,
            text="01  DỰ ÁN"
        )
        self.tabs.add(
            self.editor_tab,
            text="02  BIÊN TẬP"
        )

        self.build_project()
        self.build_editor()
        self.build_export()
        self.build_queue()
        self.build_creator()
        self.build_interview_audio_tab()


    def build_creator(self):

        self.creator_tab = ttk.Frame(self.tabs, padding=14)
        self.tabs.add(self.creator_tab, text="04  TẠO DỰ ÁN")
        self.creator_registry_file = self.settings_file.with_name("khiem_channels.json")
        self.creator_channels = self.creator_load_channels()
        self.creator_channel = tk.StringVar(value="")
        self.creator_new_channel = tk.StringVar(value="")
        self.creator_edit_name = tk.StringVar(value="")
        self.creator_edit_base = tk.StringVar(value="")
        self.creator_base = tk.StringVar(value=str(Path.home() / "Documents" / "KHIEM YOUTUBE"))
        self.creator_name = tk.StringVar(value="")
        self.creator_selected = tk.StringVar(value="")
        self.creator_channel_search = tk.StringVar(value="")
        self.creator_project_search = tk.StringVar(value="")
        self.creator_preview = tk.StringVar(value="")
        self.creator_channel_path_text = tk.StringVar(value="")
        self.heading(self.creator_tab, "QUẢN LÝ KÊNH & DỰ ÁN")
        ttk.Label(self.creator_tab, text="Chọn kênh đã lưu, tạo dự án, sau đó chọn dự án để điền Tab 01.").pack(anchor="w", pady=(0, 10))

        channel = ttk.LabelFrame(self.creator_tab, text="01  KÊNH YOUTUBE", padding=12)
        channel.pack(fill="x", pady=(0, 10))
        channel.columnconfigure(0, weight=1)
        row = ttk.Frame(channel)
        row.pack(fill="x")
        ttk.Label(row, text="Tìm kênh:").pack(side="left", padx=(0, 6))
        self.creator_channel_search_entry = ttk.Entry(row, textvariable=self.creator_channel_search, width=19)
        self.creator_channel_search_entry.pack(side="left", padx=(0, 8))
        self.creator_channel_dropdown = ttk.Combobox(row, textvariable=self.creator_channel,
                                                     state="readonly", width=30)
        self.creator_channel_dropdown.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.studio_button(row, "+ THÊM KÊNH", self.creator_show_add_channel, primary=True).pack(side="left", padx=(0, 6))
        self.studio_button(row, "SỬA KÊNH", self.creator_show_edit_channel).pack(side="left")
        self.creator_channel_suggestions = tk.Listbox(channel, height=5, exportselection=False, bg=COLORS["input"], fg=COLORS["text"], selectbackground=COLORS["accent"], selectforeground=COLORS["bg"], relief="flat", highlightthickness=0)
        self.creator_channel_suggestions.bind("<ButtonRelease-1>", lambda _e: self.creator_pick_suggestion("channel"))
        ttk.Label(channel, textvariable=self.creator_channel_path_text,
                  foreground=COLORS["muted"]).pack(anchor="w", pady=(7, 0))

        project = ttk.LabelFrame(self.creator_tab, text="02  TẠO DỰ ÁN", padding=12)
        project.pack(fill="x", pady=(0, 10))
        row = ttk.Frame(project)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.creator_name).pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.studio_button(row, "+ TẠO DỰ ÁN", self.creator_create, primary=True).pack(side="left")
        ttk.Label(project, textvariable=self.creator_preview,
                  foreground=COLORS["muted"], wraplength=800).pack(anchor="w", pady=(7, 0))

        chooser = ttk.LabelFrame(self.creator_tab, text="03  CHỌN DỰ ÁN ĐỂ DỰNG", padding=12)
        chooser.pack(fill="x")
        row = ttk.Frame(chooser)
        row.pack(fill="x")
        ttk.Label(row, text="Tìm dự án:").pack(side="left", padx=(0, 6))
        self.creator_project_search_entry = ttk.Entry(row, textvariable=self.creator_project_search, width=19)
        self.creator_project_search_entry.pack(side="left", padx=(0, 8))
        self.creator_project_suggestions = tk.Listbox(chooser, height=5, exportselection=False, bg=COLORS["input"], fg=COLORS["text"], selectbackground=COLORS["accent"], selectforeground=COLORS["bg"], relief="flat", highlightthickness=0)
        self.creator_project_suggestions.bind("<ButtonRelease-1>", lambda _e: self.creator_pick_suggestion("project"))
        self.creator_dropdown = ttk.Combobox(row, textvariable=self.creator_selected,
                                             state="readonly", width=30)
        self.creator_dropdown.pack(side="left", fill="x", expand=True, padx=(0, 8))
        actions = ttk.Frame(chooser)
        actions.pack(fill="x", pady=(10, 0))
        self.studio_button(actions, "LÀM MỚI", self.creator_refresh).pack(side="left", padx=(0, 8))
        self.studio_button(actions, "MỞ THƯ MỤC", self.creator_open_selected).pack(side="left")
        self.studio_button(actions, "CHUYỂN SANG TAB 01  →  ĐIỀN ĐƯỜNG DẪN", self.creator_apply, primary=True).pack(side="right")
        self.creator_channel_search_entry.bind("<Down>", lambda _e: self.creator_focus_suggestions("channel"))
        self.creator_project_search_entry.bind("<Down>", lambda _e: self.creator_focus_suggestions("project"))
        self.creator_channel_search_entry.bind("<Return>", lambda _e: self.creator_pick_first("channel"))
        self.creator_project_search_entry.bind("<Return>", lambda _e: self.creator_pick_first("project"))
        self.creator_channel_suggestions.bind("<Return>", lambda _e: self.creator_pick_suggestion("channel"))
        self.creator_project_suggestions.bind("<Return>", lambda _e: self.creator_pick_suggestion("project"))
        self.creator_channel_search.trace_add("write", lambda *_: self.creator_filter_channels())
        self.creator_project_search.trace_add("write", lambda *_: self.creator_filter_projects())
        self.creator_channel.trace_add("write", lambda *_: (self.creator_refresh(), self.creator_update_preview(),
                                                             self.creator_sync_edit(), self.creator_update_channel_path()))
        self.creator_name.trace_add("write", lambda *_: self.creator_update_preview())
        self.creator_refresh_channels()
        self.creator_sync_edit()
        self.creator_update_channel_path()

    def creator_show_suggestions(self, kind, matches, query):
        widget = self.creator_channel_suggestions if kind == "channel" else self.creator_project_suggestions
        widget.delete(0, "end")
        if not query or not matches:
            widget.pack_forget()
            return
        for name in matches[:30]:
            widget.insert("end", name)
        widget.configure(height=min(len(matches), 6))
        if not widget.winfo_manager():
            widget.pack(fill="x", padx=(0, 8), pady=(4, 2))

    def creator_focus_suggestions(self, kind):
        widget = self.creator_channel_suggestions if kind == "channel" else self.creator_project_suggestions
        if widget.size():
            widget.focus_set()
            widget.selection_clear(0, "end")
            widget.selection_set(0)
            widget.activate(0)
        return "break"

    def creator_pick_first(self, kind):
        widget = self.creator_channel_suggestions if kind == "channel" else self.creator_project_suggestions
        if widget.size():
            widget.selection_clear(0, "end")
            widget.selection_set(0)
            self.creator_pick_suggestion(kind)
        return "break"

    def creator_pick_suggestion(self, kind):
        widget = self.creator_channel_suggestions if kind == "channel" else self.creator_project_suggestions
        selection = widget.curselection()
        if not selection:
            return "break"
        name = widget.get(selection[0])
        if kind == "channel":
            if name not in self.creator_channels:
                return "break"
            self.creator_channel.set(name)
            self.creator_channel_search.set("")
            self.creator_project_search.set("")
            self.creator_channel_search_entry.focus_set()
        else:
            if name not in getattr(self, "creator_project_names", []):
                return "break"
            self.creator_selected.set(name)
            self.creator_project_search.set("")
            self.creator_project_search_entry.focus_set()
        widget.pack_forget()
        return "break"

    def creator_filter_channels(self):
        names = sorted(self.creator_channels, key=str.casefold)
        query = self.creator_channel_search.get().strip().casefold()
        matches = [name for name in names if query in name.casefold()]
        self.creator_channel_dropdown.configure(values=matches)
        self.creator_show_suggestions("channel", matches, query)

    def creator_filter_projects(self):
        query = self.creator_project_search.get().strip().casefold()
        names = getattr(self, "creator_project_names", [])
        matches = [name for name in names if query in name.casefold()]
        self.creator_dropdown.configure(values=matches)
        self.creator_show_suggestions("project", matches, query)

    def creator_update_channel_path(self):
        try:
            self.creator_channel_path_text.set("Thư mục: " + str(self.creator_channel_path()))
        except ValueError:
            self.creator_channel_path_text.set("Chưa có kênh. Bấm + THÊM KÊNH để bắt đầu.")

    def creator_channel_dialog(self, editing=False):
        if editing and not self.creator_channel.get():
            messagebox.showinfo("Chọn kênh", "Hãy chọn kênh trước.")
            return
        if editing:
            self.creator_sync_edit()
        dialog = tk.Toplevel(self.root)
        dialog.title("TẠO KÊNH MỚI TỪ KÊNH ĐÃ CHỌN" if editing else "THÊM KÊNH MỚI")
        dialog.configure(bg=COLORS["panel"])
        dialog.geometry("640x225")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        name_var = self.creator_edit_name if editing else self.creator_new_channel
        path_var = self.creator_edit_base if editing else self.creator_base
        ttk.Label(body, text="Tên kênh mới").grid(row=0, column=0, sticky="w", pady=8)
        ttk.Entry(body, textvariable=name_var).grid(row=0, column=1, columnspan=2, sticky="ew", padx=8, pady=8)
        ttk.Label(body, text="Nơi lưu kênh").grid(row=1, column=0, sticky="w", pady=8)
        ttk.Entry(body, textvariable=path_var).grid(row=1, column=1, sticky="ew", padx=8, pady=8)
        choose = self.creator_choose_edit if editing else self.creator_choose
        self.studio_button(body, "CHỌN...", choose).grid(row=1, column=2, pady=8)
        ttk.Label(body, text="Thư mục kênh cũ và dữ liệu cũ sẽ không bị thay đổi." if editing
                  else "Chỉ cần lưu kênh một lần. Lần sau chọn từ danh sách.",
                  foreground=COLORS["muted"]).grid(row=2, column=0, columnspan=3, sticky="w", pady=6)
        def submit():
            before = dict(self.creator_channels)
            if editing:
                self.creator_edit_channel()
            else:
                self.creator_create_channel()
            if self.creator_channels != before:
                dialog.destroy()
        self.studio_button(body, "TẠO THƯ MỤC KÊNH MỚI" if editing else "LƯU KÊNH",
                           submit, primary=True).grid(row=3, column=1, sticky="w", padx=8, pady=5)
        dialog.bind("<Escape>", lambda _e: dialog.destroy())

    def creator_show_add_channel(self):
        self.creator_channel_dialog(False)

    def creator_show_edit_channel(self):
        self.creator_channel_dialog(True)

    def creator_cleanup_candidates(self):
        # Strict allowlist: only Python bytecode caches and aged application logs
        # inside the application's own directory. Never scan channel/project roots.
        root = Path(__file__).resolve().parent
        candidates = []
        now = time.time()
        for cache in root.rglob("__pycache__"):
            try:
                if not cache.is_dir() or cache.is_symlink():
                    continue
                if any(part in (".git", "venv", ".venv", "site-packages") for part in cache.relative_to(root).parts):
                    continue
                for item in cache.iterdir():
                    if item.is_file() and not item.is_symlink() and item.suffix in (".pyc", ".pyo"):
                        candidates.append(item)
            except (OSError, ValueError):
                continue
        # Only old logs at application root, not nested project or user folders.
        for pattern in ("*.log",):
            for item in root.glob(pattern):
                try:
                    if item.is_file() and not item.is_symlink() and now - item.stat().st_mtime > 30 * 86400:
                        candidates.append(item)
                except OSError:
                    continue
        return list(dict.fromkeys(candidates))

    def creator_cleanup_dialog(self):
        if self.busy or self.queue_running or any(j.get("status") == "running" for j in self.queue.jobs):
            messagebox.showwarning("Đang xử lý", "Không thể dọn rác khi tác vụ đang chạy.")
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("DỌN DẸP FILE RÁC | KHIÊM YOUTUBE")
        dialog.geometry("690x440")
        dialog.minsize(540, 340)
        dialog.transient(self.root)
        body = ttk.Frame(dialog, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Chỉ quét cache Python và log ứng dụng cũ hơn 30 ngày.").pack(anchor="w")
        ttk.Label(body, text="Không xóa ảnh, video, voice, TXT, CapCut, MP4 hoặc thư mục dự án.",
                  foreground=COLORS["muted"]).pack(anchor="w", pady=(0, 8))
        status = tk.StringVar(value="Bấm QUÉT để kiểm tra dung lượng.")
        ttk.Label(body, textvariable=status).pack(anchor="w", pady=(0, 8))
        listing = tk.Listbox(body, bg=COLORS["input"], fg=COLORS["text"],
                             selectbackground=COLORS["accent"], relief="flat")
        listing.pack(fill="both", expand=True, pady=(0, 10))
        found = []
        def scan():
            found.clear()
            listing.delete(0, "end")
            found.extend(self.creator_cleanup_candidates())
            total = 0
            for path in found:
                try:
                    size = path.stat().st_size
                    total += size
                    listing.insert("end", "%s   (%.1f KB)" % (path.name, size / 1024))
                except OSError:
                    continue
            status.set("%s file có thể dọn | %.2f MB" % (len(found), total / 1048576))
        def remove():
            if self.busy or self.queue_running or any(j.get("status") == "running" for j in self.queue.jobs):
                messagebox.showwarning("Đang xử lý", "Hãy đợi tác vụ hoàn thành.", parent=dialog)
                return
            if not found:
                messagebox.showinfo("Dọn dẹp", "Không có file nào cần xóa. Hãy quét trước.", parent=dialog)
                return
            if not messagebox.askyesno("Xác nhận xóa", "Xóa %s file cache/log đã liệt kê?\\nKhông ảnh hưởng dữ liệu dự án." % len(found), parent=dialog):
                return
            allowed = set(self.creator_cleanup_candidates())
            deleted, failed = 0, 0
            for path in found:
                if path not in allowed:
                    continue
                try:
                    path.unlink()
                    deleted += 1
                except OSError:
                    failed += 1
            scan()
            self.log("Dọn file rác: %s file đã xóa, %s lỗi." % (deleted, failed))
            messagebox.showinfo("Kết quả", "Đã xóa %s file. Không xóa được %s file." % (deleted, failed), parent=dialog)
        buttons = ttk.Frame(body)
        buttons.pack(fill="x")
        self.studio_button(buttons, "QUÉT FILE RÁC", scan).pack(side="left", padx=(0, 8))
        self.studio_button(buttons, "XÓA FILE ĐÃ QUÉT", remove, primary=True).pack(side="left")
        self.studio_button(buttons, "ĐÓNG", dialog.destroy).pack(side="right")
        scan()

    def creator_open_selected(self):
        try:
            name = self.creator_selected.get().strip()
            if not name:
                raise ValueError("Chưa chọn dự án.")
            folder = self.creator_channel_path() / name
            if not folder.is_dir():
                raise ValueError("Thư mục dự án không tồn tại.")
            os.startfile(str(folder))
        except (OSError, ValueError, AttributeError) as exc:
            messagebox.showerror("Mở thư mục", str(exc))

    def creator_sync_edit(self):
        try:
            folder = self.creator_channel_path()
            self.creator_edit_name.set(self.creator_channel.get())
            self.creator_edit_base.set(str(folder.parent))
        except ValueError:
            self.creator_edit_name.set("")
            self.creator_edit_base.set("")

    def creator_choose_edit(self):
        folder = filedialog.askdirectory(title="Chọn nơi chuyển kênh đến")
        if folder:
            self.creator_edit_base.set(folder)

    def creator_edit_channel(self):
        # Editing a channel creates a separate new channel folder. Never rename,
        # move, copy or delete the existing folder or its projects.
        if self.busy or self.queue_running or any(j.get("status") == "running" for j in self.queue.jobs):
            messagebox.showwarning("Đang xử lý", "Hãy đợi tác vụ và hàng đợi hoàn thành.")
            return
        try:
            old_name = self.creator_channel.get().strip()
            old = self.creator_channel_path()
            new_name = self.creator_edit_name.get().strip()
            self.creator_validate_name(new_name, "Tên kênh mới")
            parent = self.creator_edit_base.get().strip()
            if not parent:
                raise ValueError("Chưa chọn thư mục lưu kênh mới.")
            new = (Path(parent).expanduser() / new_name).resolve()
            if new_name in self.creator_channels:
                raise ValueError("Tên kênh này đã có trong danh sách. Hãy chọn tên khác.")
            if new.exists():
                raise ValueError("Thư mục mới đã tồn tại. Không ghi đè dữ liệu.")
            if not messagebox.askyesno("Tạo kênh mới từ kênh đã chọn",
                    "Tạo thư mục kênh mới tại:\\n%s\\n\\n"
                    "Kênh cũ '%s' và toàn bộ dự án, hàng đợi, đường dẫn cũ sẽ được giữ nguyên. "
                    "Không sao chép dữ liệu sang thư mục mới. Tiếp tục?" % (new, old_name)):
                return
            new.mkdir(parents=True, exist_ok=False)
            self.creator_channels[new_name] = str(new)
            try:
                self.creator_save_channels()
            except OSError:
                self.creator_channels.pop(new_name, None)
                try:
                    new.rmdir()
                except OSError:
                    pass
                raise
            self.creator_refresh_channels()
            self.creator_channel.set(new_name)
            self.creator_name.set("")
            self.creator_sync_edit()
            self.log("Đã tạo kênh mới: " + str(new) + " | Kênh cũ giữ nguyên: " + str(old))
            messagebox.showinfo("Đã tạo kênh mới",
                "Đã tạo và lưu kênh mới. Kênh cũ và các dự án cũ vẫn giữ nguyên.")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Không thể tạo kênh mới", str(exc))

    def creator_load_channels(self):
        try:
            data = json.loads(self.creator_registry_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}
        except (OSError, ValueError, TypeError):
            pass
        return {}

    def creator_save_channels(self):
        self.creator_registry_file.parent.mkdir(parents=True, exist_ok=True)
        temp = self.creator_registry_file.with_suffix(".tmp")
        temp.write_text(json.dumps(self.creator_channels, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.creator_registry_file)

    def creator_validate_name(self, name, label):
        if not name or name in (".", "..") or name.endswith((".", " ")) or any(
                ch in '<>:"/\\\\|?*' or ord(ch) < 32 for ch in name):
            raise ValueError(label + " không hợp lệ.")
        if name.upper().split(".")[0] in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
            raise ValueError(label + " trùng tên hệ thống Windows.")

    def creator_channel_path(self):
        channel = self.creator_channel.get().strip()
        folder = self.creator_channels.get(channel)
        if not folder:
            raise ValueError("Hãy chọn một kênh đã lưu.")
        return Path(folder)

    def creator_refresh_channels(self):
        names = sorted(self.creator_channels, key=str.casefold)
        self.creator_filter_channels()
        if self.creator_channel.get() not in names:
            self.creator_channel.set(names[0] if names else "")
        self.creator_refresh()
        self.creator_update_preview()

    def creator_create_channel(self):
        if self.busy or self.queue_running:
            messagebox.showwarning("Đang xử lý", "Hãy đợi tác vụ hoàn thành.")
            return
        try:
            name = self.creator_new_channel.get().strip()
            self.creator_validate_name(name, "Tên kênh")
            if name in self.creator_channels:
                self.creator_channel.set(name)
                messagebox.showinfo("Kênh đã lưu", "Kênh này đã có trong danh sách.")
                return
            base = self.creator_base.get().strip()
            if not base:
                raise ValueError("Hãy chọn nơi lưu kênh.")
            folder = Path(base).expanduser() / name
            if folder.exists() and not folder.is_dir():
                raise ValueError("Đường dẫn kênh đang là file.")
            folder.mkdir(parents=True, exist_ok=True)
            self.creator_channels[name] = str(folder.resolve())
            try:
                self.creator_save_channels()
            except OSError:
                del self.creator_channels[name]
                raise
            self.creator_refresh_channels()
            self.creator_channel.set(name)
            self.creator_new_channel.set("")
            self.log("Đã lưu kênh: " + str(folder))
            messagebox.showinfo("Đã lưu kênh", "Từ lần sau chỉ cần chọn tên kênh trong danh sách.")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Tạo kênh", str(exc))

    def creator_refresh(self):
        try:
            base = self.creator_channel_path()
        except ValueError:
            self.creator_project_names = []
            self.creator_filter_projects()
            self.creator_selected.set("")
            return
        folders = ("01 - Voice", "02 - Kich Ban TXT", "03 - Hinh Anh",
                   "04 - Video", "05 - Interview", "06 - Xuat Video")
        names = []
        try:
            if base.is_dir():
                names = sorted((p.name for p in base.iterdir()
                                if p.is_dir() and all((p / folder).is_dir() for folder in folders)),
                               key=str.casefold)
        except OSError:
            pass
        self.creator_project_names = names
        self.creator_filter_projects()
        if self.creator_selected.get() not in names:
            self.creator_selected.set(names[0] if names else "")

    def creator_apply(self):
        if self.busy or self.queue_running:
            messagebox.showwarning("Đang xử lý", "Đợi tác vụ hiện tại hoàn thành trước khi đổi dự án.")
            return
        name = self.creator_selected.get().strip()
        if name not in getattr(self, "creator_project_names", []):
            messagebox.showinfo("Chọn dự án", "Hãy chọn một dự án có trong danh sách của kênh hiện tại.")
            return
        try:
            target = self.creator_channel_path() / name
            folders = {
                "voice": "01 - Voice", "txt": "02 - Kich Ban TXT",
                "images": "03 - Hinh Anh", "videos": "04 - Video",
                "interview_folder": "05 - Interview", "out": "06 - Xuat Video"
            }
            if not all((target / dirname).is_dir() for dirname in folders.values()):
                raise ValueError("Dự án thiếu thư mục chuẩn. Hãy kiểm tra lại.")
            self.vars["name"].set(name)
            self.vars["project_folder"].set(str(target))
            for key, dirname in folders.items():
                self.vars[key].set(str(target / dirname))
            self.interview_enabled.set(False)
            self.save_settings()
            self.tabs.select(self.project_tab)
            self.log("Đã chọn dự án và điền Tab 01: " + name)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Chọn dự án", str(exc))

    def creator_choose(self):
        folder = filedialog.askdirectory(title="Chọn nơi lưu kênh mới")
        if folder:
            self.creator_base.set(folder)

    def creator_target(self):
        name = self.creator_name.get().strip()
        self.creator_validate_name(name, "Tên dự án")
        return self.creator_channel_path() / name

    def creator_update_preview(self):
        try:
            self.creator_preview.set(str(self.creator_target()))
        except ValueError:
            self.creator_preview.set("Chọn kênh đã lưu và nhập tên dự án.")

    def creator_create(self):
        if self.busy or self.queue_running:
            messagebox.showwarning("Đang xử lý", "Hãy đợi tác vụ hiện tại hoàn tất.")
            return
        try:
            target = self.creator_target()
            folders = {
                "voice": "01 - Voice", "txt": "02 - Kich Ban TXT",
                "images": "03 - Hinh Anh", "videos": "04 - Video",
                "interview_folder": "05 - Interview", "out": "06 - Xuat Video"
            }
            if target.exists() and not target.is_dir():
                raise ValueError("Đường dẫn dự án đã là một file.")
            if target.exists() and any(target.iterdir()):
                if not messagebox.askyesno("Dự án đã tồn tại",
                        "Thư mục này đã có dữ liệu. Giữ nguyên file cũ và chỉ tạo các thư mục còn thiếu?"):
                    return
            target.mkdir(parents=True, exist_ok=True)
            for dirname in folders.values():
                (target / dirname).mkdir(exist_ok=True)
            self.creator_refresh()
            self.creator_selected.set(target.name)
            self.log("Đã tạo thư mục dự án: " + str(target))
            messagebox.showinfo("Đã tạo dự án",
                "Đã tạo bộ thư mục. Tab 01 chưa thay đổi.\\n"
                "Khi cần dựng, chọn dự án trong danh sách và bấm ĐIỀN VÀO TAB 01.")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Không thể tạo dự án", str(exc))

    def creator_open(self):
        try:
            folder = self.creator_target()
            if not folder.is_dir():
                messagebox.showinfo("Chưa tạo", "Hãy tạo dự án trước.")
                return
            os.startfile(str(folder))
        except (OSError, ValueError, AttributeError) as exc:
            messagebox.showerror("Mở thư mục", str(exc))

    def heading(self, parent, title):
        ttk.Label(
            parent,
            text=title,
            font=("Segoe UI", 15, "bold")
        ).pack(
            anchor="w",
            pady=(0, 15)
        )

    def field(
        self, parent, key, label,
        options=None
    ):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=1)

        ttk.Label(
            row,
            text=label,
            width=31
        ).pack(side="left")

        if options is None:
            widget = ttk.Entry(
                row,
                textvariable=self.vars[key]
            )
        else:
            widget = ttk.Combobox(
                row,
                textvariable=self.vars[key],
                values=options,
                state="readonly"
            )

        widget.pack(
            side="left",
            fill="x",
            expand=True
        )

    def folder_field(
        self, parent, key, label
    ):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=3)

        ttk.Label(
            row,
            text=label,
            width=25
        ).pack(side="left")

        ttk.Entry(
            row,
            textvariable=self.vars[key]
        ).pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 8)
        )

        def browse():
            folder = filedialog.askdirectory()
            if folder:
                self.vars[key].set(folder)

        ttk.Button(
            row,
            text="Chọn...",
            command=browse
        ).pack(side="right")

    def studio_button(self, parent, title, command, primary=False):
        if CTK_READY:
            return ctk.CTkButton(
                parent, text=title, command=command, corner_radius=10,
                height=38, font=("Segoe UI", 12, "bold"),
                fg_color="#087FAD" if primary else "#193D58",
                hover_color="#0DB8DC" if primary else "#245575",
                text_color="#FFFFFF", border_width=1,
                border_color="#13D5F5" if primary else "#35617C"
            )
        return ttk.Button(parent, text=title, command=command,
                          style="Accent.TButton" if primary else "TButton")

    def studio_card(self, parent):
        if CTK_READY:
            return ctk.CTkFrame(parent, fg_color="#102437", corner_radius=14,
                                border_width=1, border_color="#23617F")
        return tk.Frame(parent, bg=COLORS["panel"],
                        highlightbackground="#23617F", highlightthickness=1)

    def build_project(self):
        # Three-column studio dashboard, with all existing path settings.
        self.project_tab.configure(padding=10)
        body = tk.Canvas(self.project_tab, bg=COLORS["bg"], highlightthickness=0)
        scroll = ttk.Scrollbar(self.project_tab, orient="vertical", command=body.yview)
        body.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        body.pack(fill="both", expand=True)
        shell = ttk.Frame(body, padding=6)
        win = body.create_window((0, 0), window=shell, anchor="nw")
        shell.bind("<Configure>", lambda e: body.configure(scrollregion=body.bbox("all")))
        body.bind("<Configure>", lambda e: body.itemconfigure(win, width=e.width))
        def project_wheel(event):
            if self.tabs.select() != str(self.project_tab):
                return
            delta = getattr(event, "delta", 0)
            step = -1 if delta > 0 or getattr(event, "num", 0) == 4 else 1
            body.yview_scroll(step * 3, "units")
            return "break"

        def bind_project_wheel(widget):
            for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                widget.bind(sequence, project_wheel, add="+")
            for child in widget.winfo_children():
                bind_project_wheel(child)

        for col, weight in enumerate((5, 7)):
            shell.columnconfigure(col, weight=weight, uniform="studio")

        def panel(col, title):
            frame = self.studio_card(shell)
            frame.grid(row=0, column=col, sticky="nsew", padx=5, pady=5)
            tk.Label(frame, text=title, bg=COLORS["panel"], fg=COLORS["accent"],
                     font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=12, pady=(10, 7))
            return frame

        left = panel(0, "DỰ ÁN HIỆN TẠI")
        ttk.Label(left, text="Tên dự án").pack(anchor="w", padx=12)
        ttk.Entry(left, textvariable=self.vars["name"]).pack(fill="x", padx=12, pady=(2, 6))
        for key, label in (
            ("project_folder", "Thư mục chung"),
            ("txt", "Kịch bản TXT"), ("voice", "Voice MP3"),
            ("images", "Thư mục ảnh"), ("videos", "Thư mục video"),
            ("interview_folder", "Interview (tùy chọn)"),
            ("out", "Nơi xuất kết quả"), ("draft_root", "Thư mục CapCut"),
            ("sample", "Mẫu CapCut tùy chọn")):
            line = ttk.Frame(left)
            line.pack(fill="x", padx=12, pady=3)
            ttk.Label(line, text=label, width=23).pack(side="left")
            ttk.Entry(line, textvariable=self.vars[key], width=12).pack(side="left", fill="x", expand=True)
            def browse(k=key):
                folder = filedialog.askdirectory()
                if folder:
                    self.vars[k].set(folder)
            ttk.Button(line, text="…", width=3, command=browse).pack(side="right", padx=(4, 0))

        center = panel(1, "ULTRA AI STUDIO")
        banner = self.studio_card(center)
        banner.pack(fill="x",padx=12,pady=(0,12))
        tk.Label(banner,text="Dựng video YouTube tự động bằng AI",bg="#0B1E32",fg="#F2F6FC",font=("Segoe UI",13,"bold")).pack(anchor="w",padx=12,pady=(10,4))
        indicators = tk.Frame(banner,bg="#0B1E32")
        indicators.pack(anchor="w",padx=12,pady=(4,10))
        for label,var in (("CLIP",self.ai),("Whisper",self.align),("NVENC",self.gpu),("Smart Timeline",self.vars["smart_timeline"])):
            status = tk.Label(indicators,bg="#0B1E32",font=("Segoe UI",11))
            status.pack(side="left",padx=(0,12))
            def refresh(*args, v=var, w=status, name=label):
                enabled = str(v.get()).lower() in ("1","true")
                w.configure(text=("✓ " if enabled else "○ ")+name,fg="#13D5F5" if enabled else "#AAB9CA")
            refresh()
            var.trace_add("write",refresh)
        ttk.Label(center,text="THAO TÁC NHANH",foreground=COLORS["accent"],font=("Segoe UI",12,"bold")).pack(anchor="w",padx=12,pady=(1,4))
        actions = ttk.Frame(center)
        actions.pack(fill="x",padx=12)
        for i in range(3):
            actions.columnconfigure(i,weight=1,uniform="actions")
        for i,(label,mode) in enumerate((("Xuất CapCut","capcut"),("Kiểm tra tư liệu","check"),("Xuất MP4","render"))):
            button=self.studio_button(actions,label,lambda m=mode:self.start(m),primary=mode=="capcut")
            button.grid(row=0,column=i,sticky="ew",padx=2,pady=2)
            self.buttons.append(button)
        for i,(label,mode) in enumerate((("+ Đợi CapCut","capcut"),("+ Đợi MP4","render"))):
            self.studio_button(actions,label,lambda m=mode:self.queue_add(m)).grid(row=1,column=i,sticky="ew",padx=2,pady=2)
        self.studio_button(actions,"Mở thư mục xuất",self.open_output).grid(row=1,column=2,sticky="ew",padx=2,pady=2)
        status_frame=ttk.Frame(center)
        status_frame.pack(fill="x",padx=12,pady=(12,0))
        ttk.Label(status_frame,textvariable=self.run_stage,wraplength=440).pack(side="left")
        ttk.Label(status_frame,textvariable=self.run_elapsed).pack(side="right")
        ttk.Progressbar(center,variable=self.progress,maximum=100).pack(fill="x",padx=12,pady=8)
        for var in (self.scene_status,self.balance_status):
            ttk.Label(center,textvariable=var,wraplength=500).pack(anchor="w",padx=12,pady=1)
        bind_project_wheel(body)

    def build_editor(self):
        # Scrollable editor: works on smaller displays and with mouse wheel.
        canvas = tk.Canvas(self.editor_tab, bg=COLORS["panel"],
                           highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(self.editor_tab, orient="vertical",
                                  command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        editor_body = ttk.Frame(canvas, padding=(12, 8))
        window_id = canvas.create_window((0, 0), window=editor_body, anchor="nw")
        editor_body.bind("<Configure>",
                         lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda event: canvas.itemconfigure(window_id, width=event.width))

        def wheel(event):
            if self.tabs.select() == str(self.editor_tab):
                canvas.yview_scroll(-int(event.delta / 120) if event.delta else 0, "units")

        def wheel_linux_up(event):
            if self.tabs.select() == str(self.editor_tab):
                canvas.yview_scroll(-1, "units")

        def wheel_linux_down(event):
            if self.tabs.select() == str(self.editor_tab):
                canvas.yview_scroll(1, "units")

        def enable_wheel(event):
            self.root.bind_all("<MouseWheel>", wheel)
            self.root.bind_all("<Button-4>", wheel_linux_up)
            self.root.bind_all("<Button-5>", wheel_linux_down)

        def disable_wheel(event):
            self.root.unbind_all("<MouseWheel>")
            self.root.unbind_all("<Button-4>")
            self.root.unbind_all("<Button-5>")

        canvas.bind("<Enter>", enable_wheel)
        canvas.bind("<Leave>", disable_wheel)
        editor_body.bind("<Enter>", enable_wheel)



        fields = [
            (
                "speed", "Chế độ AI",
                ["Fast", "Smart", "Deep"]
            ),
            ("smart_timeline", "AI SMART TIMELINE (1=bật, 0=tắt)", None),
            ("min_video_percent", "Video tối thiểu (% thời lượng)", None),
            ("target_video_percent", "Video mục tiêu (% thời lượng)", None),
            ("vn", "Số video mỗi chu kỳ", None),
            ("an", "Số ảnh mỗi chu kỳ", None),
            (
                "videomode", "Chế độ video",
                ["Cố định", "Random"]
            ),
            ("videotime", "Video (giây)", None),
            (
                "imagemode", "Chế độ ảnh",
                ["Cố định", "Random"]
            ),
            ("imagetime", "Ảnh (giây)", None),
            ("iz", "Zoom ảnh (%)", None),
            ("vz", "Zoom video (%)", None),
            (
                "background", "Kiểu nền",
                ["Nền đen", "Nền mờ", "Nền trắng", "Nền xám", "Nền xanh đen"]
            ),
            ("blur", "Độ mờ nền", None),
            (
                "transition", "Chuyển cảnh",
                [
                    "Không",
                    "Dissolve",
                    "Fade",
                    "Mờ đen",
                    "Slide Left",
                    "Slide Right",
                    "Blur",
                    "Zoom Transition",
                    "Random"
                ]
            ),
            (
                "transition_time",
                "Thời gian chuyển cảnh",
                ["0.3", "0.5", "0.7", "1.0"]
            ),
            (
                "res", "Độ phân giải",
                [
                    "3840x2160",
                    "2560x1440",
                    "1920x1080"
                ]
            ),
            (
                "fps", "FPS",
                ["24", "30", "60"]
            )
        ]

        mapping = {k: (label, opts) for k, label, opts in fields}
        groups = [
            ("AI & TỶ LỆ", ("speed", "smart_timeline", "min_video_percent", "target_video_percent")),
            ("TƯ LIỆU", ("vn", "an", "videomode", "videotime", "imagemode", "imagetime", "iz", "vz")),
            ("HIỆU ỨNG & NỀN", ("transition", "transition_time", "background", "blur")),
            ("CHẤT LƯỢNG", ("res", "fps"))
        ]
        for col in (0, 1):
            editor_body.columnconfigure(col, weight=1, uniform="settings")
        for i, (title, keys) in enumerate(groups):
            card = ttk.LabelFrame(editor_body, text=title, padding=8)
            card.grid(row=i//2, column=i%2, sticky="nsew", padx=5, pady=5)
            card.columnconfigure(1, weight=1)
            for row, key in enumerate(keys):
                label, opts = mapping[key]
                ttk.Label(card, text=label, wraplength=180).grid(row=row, column=0, sticky="w", pady=2)
                widget = (ttk.Combobox(card, textvariable=self.vars[key], values=opts, state="readonly", width=12)
                          if opts else ttk.Entry(card, textvariable=self.vars[key], width=12))
                widget.grid(row=row, column=1, sticky="ew", padx=(6,0), pady=2)
            if i == 3:
                for j, (label, var) in enumerate([("NVENC", self.gpu), ("CLIP", self.ai), ("Whisper", self.align), *self.effects.items()]):
                    ttk.Checkbutton(card, text=label, variable=var).grid(row=2+j//2, column=j%2, sticky="w", pady=2)
        intro = ttk.Frame(editor_body)
        intro.grid(row=3,column=0,columnspan=2,sticky="w",padx=5,pady=2)
        ttk.Checkbutton(intro,text="Interview nếu phù hợp",variable=self.interview_enabled).pack(side="left",padx=(0,8))
        ttk.Label(intro,text="Intro tối đa (giây)").pack(side="left")
        ttk.Entry(intro,textvariable=self.vars["interview_max_seconds"],width=5).pack(side="left",padx=5)
        ttk.Label(editor_body, text="CapCut: Mờ đen native; các hiệu ứng khác dành cho MP4.", wraplength=850).grid(row=2,column=0,columnspan=2,sticky="w",pady=4)

    def build_export(self):
        self.log_panel = ttk.Frame(self.split, padding=(8, 4))
        self.split.add(self.log_panel, weight=0)
        self.root.after(200, lambda: self.resize_log(0.80))
        self.tabs.bind("<<NotebookTabChanged>>", lambda e: self.resize_log(.92 if self.tabs.select() == str(self.editor_tab) else .80), add="+")
        header = ttk.Frame(self.log_panel)
        header.pack(fill="x")
        ttk.Label(header, text="NHẬT KÝ XỬ LÝ", foreground=COLORS["accent"], font=("Segoe UI", 12, "bold")).pack(side="left")
        for label, fn in (("Xóa", lambda: self.log_box.delete("1.0", "end")),
                          ("Phóng to", lambda: self.resize_log(.50)),
                          ("Thu nhỏ", lambda: self.resize_log(1.0)),
                          ("Mặc định", lambda: self.resize_log(.80))):
            ttk.Button(header, text=label, command=fn).pack(side="right", padx=2)
        body = ttk.Frame(self.log_panel)
        body.pack(fill="both", expand=True)
        self.log_box = tk.Text(body, height=3, bg="#0D141E", fg="#DDE9F5",
                               insertbackground="white", font=("Consolas", 12), relief="flat", wrap="word")
        for tag, color in (("warning","#FBBF24"),("error","#F87171"),("success","#4ADE80"),("info","#DDE9F5")):
            self.log_box.tag_configure(tag, foreground=color)
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.log_box.yview)
        scroll.pack(side="right", fill="y")
        self.log_box.configure(yscrollcommand=scroll.set)
        self.log_box.pack(side="left", fill="both", expand=True)

    def resize_log(self, fraction):
        height = self.split.winfo_height()
        if height > 100:
            self.split.sashpos(0, min(height - 40, int(height*fraction)))

    def build_queue(self):
        self.queue_tab = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(self.queue_tab, text="03  HÀNG ĐỢI")
        self.heading(self.queue_tab, "Dự án chạy lần lượt, lỗi tự chuyển dự án sau")
        top = ttk.Frame(self.queue_tab)
        top.pack(fill="x", pady=5)
        for label, mode in (("Thêm CapCut", "capcut"), ("Thêm MP4", "render")):
            ttk.Button(top, text=label, command=lambda m=mode: self.queue_add(m)).pack(side="left", padx=4)
        ttk.Button(top, text="KIỂM TRA TẤT CẢ", command=self.queue_precheck_all).pack(side="left", padx=4)
        ttk.Button(top, text="CHẠY HÀNG ĐỢI", style="Accent.TButton",
                   command=self.queue_start).pack(side="left", padx=4)
        ttk.Button(top, text="RESET HÀNG ĐỢI", command=self.queue_reset_all).pack(side="left", padx=4)
        ttk.Button(top, text="Dừng sau dự án hiện tại",
                   command=self.queue_stop).pack(side="left", padx=4)
        self.queue_list = ttk.Treeview(self.queue_tab, columns=("name", "mode", "status", "time"),
                                       show="headings", height=12)
        for col, label, width in (("name", "Dự án", 250), ("mode", "Xuất", 90),
                                  ("status", "Trạng thái", 160), ("time", "Thời gian", 120)):
            self.queue_list.heading(col, text=label)
            self.queue_list.column(col, width=width)
        self.queue_list.pack(fill="both", expand=True, pady=8)
        self.queue_list.bind("<ButtonRelease-1>", self.queue_click)
        self.queue_list.bind("<Button-3>", self.queue_click)
        self.queue_menu = tk.Menu(self.root, tearoff=0)
        for label, action in (("Sửa dự án", self.queue_edit),
                              ("Xóa dự án", self.queue_delete),
                              ("Kiểm tra dự án", self.queue_check_selected),
                              ("Chạy lại", self.queue_retry),
                              ("Xem lỗi", self.queue_error)):
            self.queue_menu.add_command(label=label, command=action)
        controls = ttk.Frame(self.queue_tab)
        controls.pack(fill="x")
        ttk.Button(controls, text="Chạy lại dự án lỗi",
                   command=self.queue_retry).pack(side="left", padx=4)
        ttk.Button(controls, text="Sửa dự án đã chọn",
                   command=self.queue_edit).pack(side="left", padx=4)
        ttk.Button(controls, text="Xóa dự án đã chọn",
                   command=self.queue_delete).pack(side="left", padx=4)
        ttk.Button(controls, text="Reset dự án", command=self.queue_reset_selected).pack(side="left", padx=4)
        ttk.Button(controls, text="Xóa đã hoàn thành", command=self.queue_clear_completed).pack(side="left", padx=4)
        ttk.Button(controls, text="Xem lỗi",
                   command=self.queue_error).pack(side="left", padx=4)
        ttk.Checkbutton(self.queue_tab, text="Tắt Windows khi hàng đợi hoàn tất (tùy chọn)",
                        variable=self.queue_shutdown).pack(anchor="w", pady=10)
        self.queue_summary = ttk.Label(self.queue_tab, text="")
        self.queue_summary.pack(anchor="w")
        self.queue_refresh()
        self.root.after(1000, self.queue_tick)

    def queue_refresh(self):
        selected = self.queue_list.selection()
        for item in self.queue_list.get_children():
            self.queue_list.delete(item)
        names = {"pending": "Đang chờ", "running": "Đang chạy",
                 "success": "Hoàn thành", "failed": "LỖI",
                 "interrupted": "Bị gián đoạn", "ready": "ĐẠT", "warning": "CẢNH BÁO", "error": "LỖI KIỂM TRA"}
        for job in self.queue.jobs:
            elapsed = job.get("elapsed", 0)
            if job.get("status") == "running" and job.get("started"):
                elapsed = time.time() - job["started"]
            clock = f"{int(elapsed)//3600:02}:{int(elapsed)%3600//60:02}:{int(elapsed)%60:02}"
            self.queue_list.insert("", "end", iid=job["id"],
                values=(job["name"], job["mode"], names.get(job["status"], job["status"]), clock))
        for item in selected:
            if self.queue_list.exists(item): self.queue_list.selection_add(item)
        success = sum(j["status"] == "success" for j in self.queue.jobs)
        failed = sum(j["status"] in ("failed", "interrupted") for j in self.queue.jobs)
        pending = sum(j["status"] in ("pending", "ready", "warning") for j in self.queue.jobs)
        self.queue_summary.config(text=f"Tổng: {len(self.queue.jobs)} | Xong: {success} | Lỗi: {failed} | Chờ: {pending}")

    def queue_tick(self):
        self.queue_refresh()
        self.root.after(1000, self.queue_tick)

    def queue_selected(self):
        selection = self.queue_list.selection()
        return next((j for j in self.queue.jobs if selection and j["id"] == selection[0]), None)

    def queue_click(self, event):
        item = self.queue_list.identify_row(event.y)
        if item:
            self.queue_list.selection_set(item)
            self.queue_list.focus(item)
            if event.num == 3 or self.queue_list.identify_column(event.x) == "#1":
                self.queue_menu.tk_popup(event.x_root, event.y_root)

    def queue_check_job(self, job):
        config = dict(job["config"])
        config["_queue_id"] = job["id"]
        result = inspect_project(config, job["mode"], self.queue.jobs)
        job["precheck"] = result
        if job["status"] not in ("running", "success", "failed"):
            job["status"] = result["status"]
        self.queue.save()
        return result

    def queue_check_selected(self):
        job = self.queue_selected()
        if job and job["status"] != "running":
            self.queue_check_job(job)
            self.queue_refresh()
            self.queue_error()

    def queue_precheck_all(self):
        if self.busy:
            messagebox.showwarning("Đang chạy", "Đợi dự án hiện tại kết thúc.")
            return
        self.queue_check_all()
        counts = {key: sum(j["status"] == key for j in self.queue.jobs)
                  for key in ("ready", "warning", "error")}
        messagebox.showinfo("KIỂM TRA TẤT CẢ",
            "ĐẠT: {ready} | CẢNH BÁO: {warning} | LỖI: {error}\\n"
            "Dự án lỗi bị bỏ qua. Đây là kiểm tra nhanh, chưa render.".format(**counts))

    def queue_check_all(self):
        for job in self.queue.jobs:
            if job["status"] in ("pending", "ready", "warning", "error"):
                self.queue_check_job(job)
        self.queue_refresh()

    def queue_add(self, mode):
        config = self.get_config()
        try:
            self.validate(config)
        except Exception as error:
            messagebox.showerror("Dự án chưa hợp lệ", str(error))
            return
        if any(j["name"] == config["name"] and j["status"] in ("pending", "running")
               for j in self.queue.jobs):
            messagebox.showwarning("Trùng tên", "Dự án này đang chờ hoặc chạy.")
            return
        if self.editing_job_id:
            job = next((j for j in self.queue.jobs if j["id"] == self.editing_job_id), None)
            if job and job["status"] != "running":
                job.update(config=dict(config), name=config["name"], mode=mode,
                           status="pending", error="", precheck=None)
                self.queue.save()
            else:
                self.queue.add(config, mode)
            self.editing_job_id = None
        else:
            self.queue.add(config, mode)
        self.queue_refresh()
        self.tabs.select(self.queue_tab)

    def queue_edit(self):
        job = self.queue_selected()
        if not job or job["status"] == "running":
            return
        for key, value in job["config"].items():
            if key in self.vars:
                self.vars[key].set(str(value))
        for key, variable in (("gpu", self.gpu), ("ai", self.ai),
                              ("align", self.align), ("interview_enabled", self.interview_enabled)):
            variable.set(bool(job["config"].get(key, variable.get())))
        for key, variable in self.effects.items():
            variable.set(key in job["config"].get("effects", []))
        self.editing_job_id = job["id"]
        self.tabs.select(self.project_tab)
        messagebox.showinfo("Chỉnh sửa", "Sửa cấu hình rồi vào HÀNG ĐỢI bấm Thêm CapCut hoặc Thêm MP4 để lưu vào dự án cũ.")

    def queue_retry(self):
        job = self.queue_selected()
        if job and self.queue.retry(job):
            self.queue_refresh()
            if self.queue_running and not self.busy:
                self.root.after(50, self.queue_next)

    def queue_delete(self):
        job = self.queue_selected()
        if job and job["status"] != "running" and messagebox.askyesno(
                "Xóa dự án", "Xóa " + job["name"] + " khỏi hàng đợi? Không xóa file nguồn."):
            self.queue.jobs.remove(job)
            self.queue.save()
            self.queue_refresh()

    def queue_reset_allowed(self):
        if self.busy or self.queue_running or any(j.get("status") == "running" for j in self.queue.jobs):
            messagebox.showwarning("Hàng đợi đang chạy",
                                   "Hãy chờ dự án hiện tại kết thúc và dừng hàng đợi trước khi reset.")
            return False
        return True

    def queue_reset_job_state(self, job):
        job.update(status="pending", error="", precheck=None,
                   started=None, finished=None, elapsed=0)

    def queue_reset_all(self):
        if not self.queue_reset_allowed():
            return
        if not self.queue.jobs:
            messagebox.showinfo("RESET HÀNG ĐỢI", "Hàng đợi đang trống.")
            return
        if not messagebox.askyesno("RESET HÀNG ĐỢI",
                "Đặt lại trạng thái toàn bộ %d dự án về CHỜ?\\n"
                "Giữ nguyên danh sách, cấu hình và mọi file nguồn/đầu ra." % len(self.queue.jobs)):
            return
        for job in self.queue.jobs:
            self.queue_reset_job_state(job)
        self.queue.save()
        self.queue_refresh()
        self.log("Đã reset %d dự án về trạng thái CHỜ." % len(self.queue.jobs))

    def queue_reset_selected(self):
        if not self.queue_reset_allowed():
            return
        job = self.queue_selected()
        if not job:
            messagebox.showinfo("Reset dự án", "Hãy chọn một dự án trong bảng.")
            return
        if not messagebox.askyesno("Reset dự án",
                "Đặt lại dự án '%s' về CHỜ?\\nKhông xóa file nguồn hoặc file đã xuất." % job["name"]):
            return
        self.queue_reset_job_state(job)
        self.queue.save()
        self.queue_refresh()
        self.log("Đã reset dự án: " + job["name"])

    def queue_clear_completed(self):
        if not self.queue_reset_allowed():
            return
        completed = [j for j in self.queue.jobs if j.get("status") == "success"]
        if not completed:
            messagebox.showinfo("Dọn hàng đợi", "Không có dự án hoàn thành cần xóa.")
            return
        if not messagebox.askyesno("Xóa dự án đã hoàn thành",
                "Xóa %d dự án HOÀN THÀNH khỏi danh sách hàng đợi?\\n"
                "Không xóa file nguồn, bản CapCut hoặc MP4 đã xuất." % len(completed)):
            return
        ids = {j["id"] for j in completed}
        self.queue.jobs = [j for j in self.queue.jobs if j["id"] not in ids]
        if self.editing_job_id in ids:
            self.editing_job_id = None
        self.queue.save()
        self.queue_refresh()
        self.log("Đã dọn %d dự án hoàn thành khỏi hàng đợi." % len(completed))

    def queue_error(self):
        job = self.queue_selected()
        if job:
            check = job.get("precheck") or {}
            messages = check.get("errors", []) + check.get("warnings", [])
            messagebox.showinfo("Nhật ký dự án", (job.get("error") or "") +
                ("\\n".join(messages) if messages else "\\nKhông có lỗi được ghi nhận."))

    def queue_start(self):
        if self.queue_running:
            return
        if self.busy:
            messagebox.showwarning("Đang xử lý", "Hãy chờ tác vụ hiện tại kết thúc.")
            return
        self.queue_check_all()
        if not any(j["status"] in ("ready", "warning") for j in self.queue.jobs):
            messagebox.showinfo("Hàng đợi", "Không có dự án đạt kiểm tra để chạy.")
            return
        self.queue_shutdown_confirmed = False
        if self.queue_shutdown.get():
            if not messagebox.askyesno("Xác nhận tắt Windows",
                "Sau khi chạy hết hàng đợi, Windows sẽ tắt, kể cả khi có dự án lỗi. Bạn xác nhận?"):
                return
            self.queue_shutdown_confirmed = True
        self.queue_running = True
        self.queue_next()

    def queue_stop(self):
        self.queue_running = False
        self.queue_shutdown_confirmed = False
        self.log("Hàng đợi sẽ dừng sau dự án đang chạy.")

    def queue_next(self):
        if not self.queue_running or self.busy:
            return
        job = next((j for j in self.queue.jobs if j["status"] in ("ready", "warning")), None)
        if job is None:
            self.queue_running = False
            self.log("HÀNG ĐỢI HOÀN TẤT. Kiểm tra tab HÀNG ĐỢI để xem các dự án lỗi.")
            if self.queue_shutdown.get() and self.queue_shutdown_confirmed:
                self.queue_shutdown_confirmed = False
                import subprocess
                subprocess.Popen(["shutdown", "/s", "/t", "60"])
            return
        if self.queue_check_job(job)["status"] == "error":
            self.log("Bỏ qua dự án lỗi đầu vào: " + job["name"])
            self.root.after(100, self.queue_next)
            return
        self.active_job = job
        self.queue.update(job, "running")
        self.start(job["mode"], config_override=dict(job["config"]), from_queue=True)

    def open_safe_updater(self):
        import sys
        if getattr(sys, "frozen", False):
            messagebox.showinfo("Bản Portable", "Bản EXE không thể cập nhật bằng file Python từ GitHub.\\nHãy chạy build_portable.py trên máy tạo bản mới rồi sao chép lại thư mục Portable.")
            return
        if self.busy or self.queue_running:
            messagebox.showwarning("Cập nhật", "Hãy đợi dự án và hàng đợi hoàn thành trước khi cập nhật.")
            return
        import subprocess
        import sys
        updater = Path(__file__).resolve().parent / "khiem_auto_update.py"
        if not updater.is_file():
            messagebox.showerror("Cập nhật", "Không tìm thấy khiem_auto_update.py trong thư mục phần mềm.")
            return
        try:
            subprocess.Popen([sys.executable, str(updater)], cwd=str(updater.parent))
            self.log("Đã mở cửa sổ cập nhật GitHub. Không cần xác nhận thêm tại đây.")
        except OSError as exc:
            messagebox.showerror("Cập nhật", str(exc))

    def tick_run_timer(self):
        if not self.run_timer_active or self.run_started_at is None:
            return
        elapsed = max(0, int(time.monotonic() - self.run_started_at))
        self.run_elapsed.set(f"Thời gian chạy: {elapsed // 3600:02}:{elapsed // 60 % 60:02}:{elapsed % 60:02}")
        quiet = int(time.monotonic() - self.last_log_at)
        if quiet >= 5:
            prefix = "Chưa có tiến độ mới" if quiet >= 30 else "Đang chờ kết quả"
            self.run_stage.set(f"{prefix} ({quiet}s): {self.last_log_stage[:110]}")
        self.root.after(1000, self.tick_run_timer)

    def log(self, message):
        def update():
            message_text = str(message)
            self.last_log_at = time.monotonic()
            self.last_log_stage = message_text.strip().splitlines()[0] if message_text.strip() else ""
            if self.busy and self.last_log_stage and self.last_log_stage != getattr(self, "recovery_last_stage", ""):
                self.recovery_last_stage = self.last_log_stage
                self.recovery_write("running", self.last_log_stage)
            if self.busy and message_text.strip():
                self.run_stage.set("Đang xử lý: " + message_text.strip().splitlines()[0][:115])
            upper = message_text.upper()
            tag = ("warning" if "CẢNH BÁO" in upper else
                   "error" if "LỖI" in upper else
                   "success" if any(x in upper for x in ("HOÀN THÀNH", "THÀNH CÔNG", "HOÀN TẤT")) else "info")
            self.log_box.insert("end", time.strftime("[%H:%M:%S] ") + message_text + "\n", tag)
            self.log_box.see("end")

        self.root.after(0, update)

    def set_progress(self, value):
        self.root.after(
            0,
            lambda: self.progress.set(value)
        )

    def open_output(self):
        folder = Path(
            self.vars["out"].get()
        )

        if folder.is_dir():
            os.startfile(str(folder))
        else:
            messagebox.showwarning(
                "Thông báo",
                "Thư mục xuất không hợp lệ."
            )

    def validate(self, config):
        required = [
            "voice",
            "txt",
            "images",
            "videos",
            "out"
        ]

        if config.get("project_folder"):
            from auto_project_v11 import discover
            discover(config["project_folder"], config.get("interview_file"))
        for key in required:
            if not Path(config[key]).is_dir():
                raise ValueError(
                    "Thư mục không hợp lệ: " + key
                )

        if config.get("interview_enabled"):
            if not Path(config["interview_folder"]).is_dir():
                raise ValueError("Chọn thư mục video phỏng vấn")
            if not 1 <= float(config["interview_max_seconds"]) <= 30:
                raise ValueError("Giới hạn intro phải từ 1 đến 30 giây")

        name = config["name"]

        if not name or re.search(
            r'[<>:"/\\|?*]',
            name
        ):
            raise ValueError(
                "Tên dự án không hợp lệ."
            )

        if not 0 <= float(config["blur"]) <= 100:
            raise ValueError(
                "Độ mờ phải từ 0 đến 100."
            )

        for key in ("iz", "vz"):
            value = float(config[key])

            if not 100 <= value <= 150:
                raise ValueError(
                    "Zoom phải từ 100 đến 150%."
                )

        if not config["effects"]:
            config["effects"] = ["Tĩnh"]

    def start(self, mode, config_override=None, from_queue=False):
        if self.busy:
            return

        config = config_override if config_override is not None else self.get_config()

        try:
            self.validate(config)
        except Exception as error:
            if from_queue and self.active_job:
                self.queue.update(self.active_job, "failed", str(error))
                self.active_job = None
                self.root.after(50, self.queue_next)
            else:
                messagebox.showerror("Lỗi", str(error))
            return

        self.recovery_mode = mode
        self.recovery_project = str(config.get("name", "Dự án"))
        self.recovery_last_stage = "Chuẩn bị dự án"
        self.recovery_write("running", "Chuẩn bị dự án")
        self.busy = True
        self.progress.set(0)
        self.run_started_at = time.monotonic()
        self.run_timer_active = True
        self.last_log_at = time.monotonic()
        self.last_log_stage = "Chuẩn bị dự án"
        self.run_stage.set("Đang chuẩn bị dự án")
        self.tick_run_timer()

        for button in self.buttons:
            button.configure(
                state="disabled"
            )

        self.tabs.select(
            self.project_tab
        )

        self.log(
            "=== KHIÊM YOUTUBE V10.1 ULTRA AI ==="
        )
        self.log(
            "Chế độ: " + mode
        )

        threading.Thread(
            target=self.worker,
            args=(config, mode, from_queue),
            daemon=True
        ).start()

    def worker(self, config, mode, from_queue=False):
        success = False
        failure = ''
        def logger(message):
            self.log(message)

            try:
                logfile = (
                    Path(config["out"])
                    / "run_log.txt"
                )

                with logfile.open(
                    "a",
                    encoding="utf-8"
                ) as file:
                    file.write(
                        time.strftime("[%H:%M:%S] ") + str(message) + "\n"
                    )
            except OSError:
                pass

        try:
            # Sử dụng thuật toán V6.8.
            # Reuse a verified timeline when source files and editing settings
            # have not changed. The export mode is deliberately excluded.
            import hashlib
            fingerprint_fields = {
                key: value for key, value in config.items()
                if key not in ("draft_root", "sample", "interview_folder",
                               "interview_enabled", "interview_max_seconds")
                and not key.startswith("_")
            }
            logger("CACHE: Kiểm tra thay đổi các file nguồn.")
            source_manifest = []
            for field in ("voice", "txt", "images", "videos"):
                folder = Path(str(config.get(field, "")))
                if folder.is_dir():
                    for item in sorted(folder.rglob("*")):
                        if item.is_file():
                            stat = item.stat()
                            source_manifest.append((str(item.relative_to(folder)),
                                                    field, stat.st_size, stat.st_mtime_ns))
            # Invalidate old timelines once after script-first planner upgrade.
            fingerprint_fields["_planner_version"] = "smart_video_balance_v14"
            fingerprint = hashlib.sha256(json.dumps(
                [fingerprint_fields, source_manifest], ensure_ascii=False,
                sort_keys=True, default=str
            ).encode("utf-8")).hexdigest()
            cache_path = Path(config["out"]) / (config["name"] + ".timeline_cache.json")
            parts = None
            if cache_path.is_file():
                try:
                    cached = json.loads(cache_path.read_text(encoding="utf-8"))
                    if cached.get("fingerprint") == fingerprint:
                        parts = cached.get("parts")
                        if not isinstance(parts, list) or not parts:
                            parts = None
                        else:
                            logger("TURBO CACHE: Sử dụng timeline đã phân tích, bỏ qua CLIP và Whisper.")
                except (OSError, ValueError, TypeError):
                    parts = None
            if parts is None:
                logger("TIMELINE: Bắt đầu phân tích Voice, TXT và lựa chọn tư liệu.")
                parts = engine.plan(config, logger)
                logger("TIMELINE: Hoàn thành lập timeline.")
                try:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_text(json.dumps(
                        {"fingerprint": fingerprint, "parts": parts},
                        ensure_ascii=False
                    ), encoding="utf-8")
                except OSError as cache_error:
                    logger("Không lưu được timeline cache: " + str(cache_error))

            from pre_export_qa_v11 import validate as validate_timeline
            logger("QA: Bắt đầu kiểm tra timeline.")
            validate_timeline(parts, config, logger)
            total = sum(float(z["duration"]) for p in parts for z in p["clips"])
            video = sum(float(z["duration"]) for p in parts for z in p["clips"] if z["type"] == "video")
            percent = 100 * video / max(total, 0.001)
            vc = sum(z["type"] == "video" for p in parts for z in p["clips"])
            ac = sum(z["type"] == "image" for p in parts for z in p["clips"])
            self.root.after(0, lambda: self.balance_status.set(f"Video {percent:.1f}% | Ảnh {100-percent:.1f}%"))
            self.root.after(0, lambda: self.scene_status.set(f"{len(parts)} phần | {vc} video | {ac} ảnh"))

            config["_interview_intro"] = None
            if mode in ("render", "capcut") and config.get("interview_enabled"):
                from smart_interview_intro import choose_intro
                try:
                    logger("INTERVIEW: Bắt đầu phân tích video phỏng vấn.")
                    config["_interview_intro"] = choose_intro(config, logger)
                    logger("INTERVIEW: Hoàn tất lựa chọn intro.")
                except Exception as intro_error:
                    logger("CẢNH BÁO SMART INTERVIEW INTRO: " + str(intro_error))
                    logger("Bỏ qua intro và tiếp tục xuất video bình thường.")
                    config["_interview_intro"] = None

            if mode in ("render", "capcut") and config.get("_interview_intro"):
                from smart_interview_intro import insert_interview_cutaways
                logger("FOLDER LOCK: Bỏ cutaway interview từ nguồn chung để không lấy chéo thư mục.")

            timeline = (
                Path(config["out"])
                / (
                    config["name"]
                    + ".timeline.json"
                )
            )

            timeline.write_text(
                json.dumps(
                    parts,
                    ensure_ascii=False,
                    indent=2
                ),
                encoding="utf-8"
            )

            logger(
                "Kiểm tra tư liệu thành công."
            )
            self.set_progress(30)

            # CapCut Pro handles optional captions after opening the draft.
            # Do not run Whisper/Google Translate for subtitles during export.
            logger("TURBO: Bỏ qua Vietsub AI. Có thể tạo phụ đề tự động trong CapCut Pro sau khi mở dự án.")

            if mode == "capcut":
                from capcut import export

                logger("CAPCUT: Bắt đầu ghi dự án và các track.")
                project_path = export(
                    config,
                    parts,
                    logger
                )
                if config.get("_interview_intro"):
                    logger("Đã thêm interview đầu timeline CapCut: " + str(project_path))

            elif mode == "render":
                logger("MP4: Bắt đầu render.")
                engine.render(
                    config,
                    parts,
                    logger,
                    self.set_progress
                )
                if config.get("_interview_intro"):
                    from smart_interview_intro import prepend_mp4
                    prepend_mp4(config, config["_interview_intro"], logger)

            self.set_progress(100)
            logger("HOÀN THÀNH.")
            success = True

            if mode != "check":
                try:
                    import winsound
                    winsound.Beep(
                        1000, 200
                    )
                except Exception:
                    pass

        except Exception:
            failure = traceback.format_exc()
            logger("LỖI:\\n" + failure)

        finally:
            self.root.after(0, lambda: self.finish(success, failure, from_queue))

    def finish(self, success=True, failure="", from_queue=False):
        self.run_timer_active = False
        if self.run_started_at is not None:
            elapsed = max(0, int(time.monotonic() - self.run_started_at))
            self.run_elapsed.set(f"Tổng thời gian: {elapsed // 3600:02}:{elapsed // 60 % 60:02}:{elapsed % 60:02}")
        self.run_stage.set("Hoàn thành" if success else "Lỗi, xem nhật ký")
        self.recovery_write("completed" if success else "failed", failure)
        self.busy = False
        if from_queue and self.active_job:
            self.queue.update(self.active_job, "success" if success else "failed", failure)
            if not success:
                self.log("Dự án lỗi: " + self.active_job["name"] + ". Đã ghi nhật ký, tiếp tục dự án kế.")
            self.active_job = None
            self.queue_refresh()
            if self.queue_running:
                self.root.after(100, self.queue_next)

        for button in self.buttons:
            button.configure(
                state="normal"
            )

    def close(self):
        if self.busy:
            messagebox.showwarning(
                "Đang xử lý",
                "Hãy chờ xử lý hoàn tất."
            )
            return

        self.save_settings()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    KhiemYoutube().run()
