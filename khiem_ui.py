
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import threading
import json
import os
import re
import traceback

import app as engine


COLORS = {
    "bg": "#101722",
    "panel": "#1B2635",
    "input": "#29384B",
    "text": "#F2F6FC",
    "muted": "#AAB9CA",
    "accent": "#22C8B8"
}

DEFAULTS = {
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
        self.root.title("KHIEM YOUTUBE V10.1 | SMART INTERVIEW INTRO")
        self.root.geometry("1120x800")
        self.root.minsize(950, 650)
        self.root.configure(bg=COLORS["bg"])

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
        self.progress = tk.DoubleVar(value=0)
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

        self.root.protocol(
            "WM_DELETE_WINDOW", self.close
        )

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
        try:
            self.settings_file.write_text(
                json.dumps(
                    self.get_config(),
                    ensure_ascii=False,
                    indent=2
                ),
                encoding="utf-8"
            )
        except OSError:
            pass

    def configure_style(self):
        c = COLORS
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure(
            "TNotebook",
            background=c["bg"],
            borderwidth=0
        )
        style.configure(
            "TNotebook.Tab",
            background=c["panel"],
            foreground=c["muted"],
            padding=(24, 12),
            font=("Segoe UI", 11, "bold")
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
            font=("Segoe UI", 10)
        )
        style.configure(
            "TCheckbutton",
            background=c["panel"],
            foreground=c["text"],
            font=("Segoe UI", 10)
        )
        style.map(
            "TCheckbutton",
            background=[("active", c["panel"])]
        )

        style.configure(
            "TEntry",
            fieldbackground=c["input"],
            foreground=c["text"],
            padding=7
        )
        style.configure(
            "TCombobox",
            fieldbackground=c["input"],
            background=c["input"],
            foreground=c["text"],
            padding=7
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
            padding=10,
            font=("Segoe UI", 10)
        )

        style.configure(
            "Accent.TButton",
            background=c["accent"],
            foreground=c["bg"],
            padding=12,
            font=("Segoe UI", 10, "bold")
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
            pady=16
        )
        header.pack(fill="x")

        tk.Label(
            header,
            text="KHIÊM YOUTUBE",
            bg=COLORS["bg"],
            fg=COLORS["text"],
            font=("Segoe UI", 23, "bold")
        ).pack(anchor="w")

        tk.Label(
            header,
            text="V10.1 ULTRA AI  |  SMART INTERVIEW",
            bg=COLORS["bg"],
            fg=COLORS["accent"],
            font=("Segoe UI", 10)
        ).pack(anchor="w")

        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=(0, 15)
        )

        self.project_tab = ttk.Frame(
            self.tabs, padding=22
        )
        self.editor_tab = ttk.Frame(
            self.tabs, padding=22
        )
        self.export_tab = ttk.Frame(
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
        self.tabs.add(
            self.export_tab,
            text="03  XUẤT CAPCUT"
        )

        self.build_project()
        self.build_editor()
        self.build_export()

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
        row.pack(fill="x", pady=5)

        ttk.Label(
            row,
            text=label,
            width=25
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
        row.pack(fill="x", pady=6)

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

    def build_project(self):
        self.heading(
            self.project_tab,
            "Thiết lập dự án"
        )

        self.field(
            self.project_tab,
            "name",
            "Tên dự án"
        )

        folders = [
            ("voice", "Thư mục Voice MP3"),
            ("interview_folder", "Thư mục video phỏng vấn"),
            ("txt", "Thư mục TXT"),
            ("images", "Thư mục ảnh"),
            ("videos", "Thư mục video"),
            ("out", "Nơi xuất kết quả"),
            ("draft_root", "Thư mục CapCut"),
            ("sample", "Mẫu CapCut tùy chọn")
        ]

        ttk.Checkbutton(self.project_tab, text="Bật SMART INTERVIEW INTRO (giữ tiếng gốc)", variable=self.interview_enabled).pack(anchor="w", pady=5)
        self.field(self.project_tab, "interview_max_seconds", "Intro tối đa (giây)")

        for key, label in folders:
            self.folder_field(
                self.project_tab,
                key,
                label
            )

        ttk.Label(
            self.project_tab,
            text=(
                "Giữ nguyên cách tổ chức "
                "thư mục tư liệu của V6.8."
            ),
            foreground=COLORS["muted"]
        ).pack(
            anchor="w",
            pady=20
        )

    def build_editor(self):
        self.heading(
            self.editor_tab,
            "Cài đặt biên tập"
        )

        fields = [
            (
                "speed", "Chế độ AI",
                ["Fast", "Smart", "Deep"]
            ),
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
                ["Nền đen", "Nền mờ"]
            ),
            ("blur", "Độ mờ nền", None),
            (
                "transition", "Chuyển cảnh",
                [
                    "Không",
                    "Dissolve",
                    "Fade",
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

        for key, label, options in fields:
            self.field(
                self.editor_tab,
                key,
                label,
                options
            )

        options_frame = ttk.Frame(
            self.editor_tab
        )
        options_frame.pack(
            fill="x",
            pady=(14, 6)
        )

        for label, variable in [
            ("NVIDIA NVENC", self.gpu),
            ("AI CLIP offline", self.ai),
            ("Whisper voice", self.align)
        ]:
            ttk.Checkbutton(
                options_frame,
                text=label,
                variable=variable
            ).pack(
                side="left",
                padx=(0, 18)
            )

        effect_frame = ttk.Frame(
            self.editor_tab
        )
        effect_frame.pack(
            fill="x",
            pady=5
        )

        for label, variable in self.effects.items():
            ttk.Checkbutton(
                effect_frame,
                text=label,
                variable=variable
            ).pack(
                side="left",
                padx=(0, 18)
            )

    def build_export(self):
        self.heading(
            self.export_tab,
            "Kiểm tra và xuất"
        )

        ttk.Label(
            self.export_tab,
            text=(
                "Xuất CapCut sử dụng bộ xử lý V6.8. "
                "MP4 là tùy chọn riêng."
            ),
            foreground=COLORS["muted"]
        ).pack(
            anchor="w",
            pady=(0, 15)
        )

        actions = ttk.Frame(
            self.export_tab
        )
        actions.pack(
            fill="x",
            pady=8
        )

        for label, mode in [
            ("KIỂM TRA TƯ LIỆU", "check"),
            ("XUẤT CAPCUT", "capcut"),
            ("XUẤT MP4", "render")
        ]:
            button = ttk.Button(
                actions,
                text=label,
                style=(
                    "Accent.TButton"
                    if mode == "capcut"
                    else "TButton"
                ),
                command=lambda m=mode: self.start(m)
            )
            button.pack(
                side="left",
                padx=(0, 10)
            )
            self.buttons.append(button)

        ttk.Progressbar(
            self.export_tab,
            variable=self.progress,
            maximum=100
        ).pack(
            fill="x",
            pady=14
        )

        ttk.Label(
            self.export_tab,
            text="Nhật ký hoạt động"
        ).pack(
            anchor="w",
            pady=(8, 5)
        )

        self.log_box = tk.Text(
            self.export_tab,
            bg="#0D141E",
            fg="#DDE9F5",
            insertbackground="white",
            font=("Consolas", 10),
            relief="flat",
            wrap="word"
        )
        self.log_box.pack(
            fill="both",
            expand=True
        )

        ttk.Button(
            self.export_tab,
            text="Mở thư mục xuất",
            command=self.open_output
        ).pack(
            anchor="e",
            pady=12
        )

    def log(self, message):
        def update():
            self.log_box.insert(
                "end",
                str(message) + "\n"
            )
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

    def start(self, mode):
        if self.busy:
            return

        config = self.get_config()

        try:
            self.validate(config)
        except Exception as error:
            messagebox.showerror(
                "Lỗi",
                str(error)
            )
            return

        self.busy = True
        self.progress.set(0)

        for button in self.buttons:
            button.configure(
                state="disabled"
            )

        self.tabs.select(
            self.export_tab
        )

        self.log(
            "=== KHIÊM YOUTUBE V10.1 ULTRA AI ==="
        )
        self.log(
            "Chế độ: " + mode
        )

        threading.Thread(
            target=self.worker,
            args=(config, mode),
            daemon=True
        ).start()

    def worker(self, config, mode):
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
                        str(message) + "\n"
                    )
            except OSError:
                pass

        try:
            # Sử dụng thuật toán V6.8.
            parts = engine.plan(
                config,
                logger
            )

            config["_interview_intro"] = None
            if mode in ("render", "capcut") and config.get("interview_enabled"):
                from smart_interview_intro import choose_intro
                try:
                    config["_interview_intro"] = choose_intro(config, logger)
                except Exception as intro_error:
                    logger("CẢNH BÁO SMART INTERVIEW INTRO: " + str(intro_error))
                    logger("Bỏ qua intro và tiếp tục xuất video bình thường.")
                    config["_interview_intro"] = None

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

            if mode == "capcut":
                from capcut import export

                project_path = export(
                    config,
                    parts,
                    logger
                )
                if config.get("_interview_intro"):
                    logger("Đã thêm interview đầu timeline CapCut: " + str(project_path))

            elif mode == "render":
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

            if mode != "check":
                try:
                    import winsound
                    winsound.Beep(
                        1000, 200
                    )
                except Exception:
                    pass

        except Exception:
            logger(
                "LỖI:\n"
                + traceback.format_exc()
            )

        finally:
            self.root.after(
                0,
                self.finish
            )

    def finish(self):
        self.busy = False

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
