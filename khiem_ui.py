
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import threading
import json
import os
import re
import traceback
import time
from project_queue_v11 import ProjectQueue
from queue_precheck_v11 import inspect as inspect_project

import app as engine


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

        if config.get("project_folder", "").strip():
            folder = config["project_folder"].strip()
            for key in ("voice", "txt", "images", "videos"):
                config[key] = folder
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
            padding=(28, 8),
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
            padding=4
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
            padding=(8, 4),
            font=("Segoe UI", 10)
        )

        style.configure(
            "Accent.TButton",
            background=c["accent"],
            foreground=c["bg"],
            padding=(8, 4),
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
            pady=8
        )
        header.pack(fill="x")

        ttk.Button(header, text="CẬP NHẬT GITHUB", style="Accent.TButton",
                   command=self.open_safe_updater).pack(side="right", anchor="n", padx=(12, 0))

        tk.Label(header, text="▣  KHIÊM YOUTUBE", bg=COLORS["bg"],
                 fg=COLORS["text"], font=("Segoe UI", 20, "bold")).pack(side="left")
        tk.Label(header, text="  |  ULTRA AI STUDIO v11.3", bg=COLORS["bg"],
                 fg=COLORS["accent"], font=("Segoe UI", 14, "bold")).pack(side="left")

        self.balance_status = tk.StringVar(value="Chưa có kết quả")
        self.scene_status = tk.StringVar(value="Chưa lập timeline")

        self.split = ttk.Panedwindow(self.root, orient="vertical")
        self.split.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.tabs = ttk.Notebook(self.split)
        self.split.add(self.tabs, weight=3)

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
            frame = tk.Frame(shell, bg=COLORS["panel"], highlightbackground="#334A60",
                             highlightthickness=1, padx=8, pady=6)
            frame.grid(row=0, column=col, sticky="nsew", padx=5, pady=5)
            tk.Label(frame, text=title, bg=COLORS["panel"], fg=COLORS["accent"],
                     font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 5))
            return frame

        left = panel(0, "DỰ ÁN HIỆN TẠI")
        ttk.Label(left, text="Tên dự án").pack(anchor="w")
        ttk.Entry(left, textvariable=self.vars["name"]).pack(fill="x", pady=(2, 6))
        for key, label in (
            ("project_folder", "Thư mục chung"),
            ("txt", "Kịch bản TXT"), ("voice", "Voice MP3"),
            ("images", "Thư mục ảnh"), ("videos", "Thư mục video"),
            ("interview_folder", "Interview (tùy chọn)"),
            ("out", "Nơi xuất kết quả"), ("draft_root", "Thư mục CapCut"),
            ("sample", "Mẫu CapCut tùy chọn")):
            line = ttk.Frame(left)
            line.pack(fill="x", pady=2)
            ttk.Label(line, text=label, width=23).pack(side="left")
            ttk.Entry(line, textvariable=self.vars[key], width=12).pack(side="left", fill="x", expand=True)
            def browse(k=key):
                folder = filedialog.askdirectory()
                if folder:
                    self.vars[k].set(folder)
            ttk.Button(line, text="…", width=3, command=browse).pack(side="right", padx=(4, 0))

        center = panel(1, "ULTRA AI STUDIO")
        banner = tk.Frame(center,bg="#0B1E32",highlightbackground="#176582",highlightthickness=1,padx=10,pady=7)
        banner.pack(fill="x",pady=(0,7))
        tk.Label(banner,text="Dựng video YouTube tự động bằng AI",bg="#0B1E32",fg="#F2F6FC",font=("Segoe UI",13,"bold")).pack(anchor="w")
        indicators = tk.Frame(banner,bg="#0B1E32")
        indicators.pack(anchor="w",pady=(4,0))
        for label,var in (("CLIP",self.ai),("Whisper",self.align),("NVENC",self.gpu),("Smart Timeline",self.vars["smart_timeline"])):
            status = tk.Label(indicators,bg="#0B1E32",font=("Segoe UI",9))
            status.pack(side="left",padx=(0,12))
            def refresh(*args, v=var, w=status, name=label):
                enabled = str(v.get()).lower() in ("1","true")
                w.configure(text=("✓ " if enabled else "○ ")+name,fg="#13D5F5" if enabled else "#AAB9CA")
            refresh()
            var.trace_add("write",refresh)
        ttk.Label(center,text="THAO TÁC NHANH",foreground=COLORS["accent"],font=("Segoe UI",11,"bold")).pack(anchor="w",pady=(1,4))
        actions = ttk.Frame(center)
        actions.pack(fill="x")
        for i in range(3):
            actions.columnconfigure(i,weight=1,uniform="actions")
        for i,(label,mode) in enumerate((("Xuất CapCut","capcut"),("Kiểm tra tư liệu","check"),("Xuất MP4","render"))):
            button=ttk.Button(actions,text=label,style="Accent.TButton" if mode=="capcut" else "TButton",command=lambda m=mode:self.start(m))
            button.grid(row=0,column=i,sticky="ew",padx=2,pady=2)
            self.buttons.append(button)
        for i,(label,mode) in enumerate((("+ Đợi CapCut","capcut"),("+ Đợi MP4","render"))):
            ttk.Button(actions,text=label,command=lambda m=mode:self.queue_add(m)).grid(row=1,column=i,sticky="ew",padx=2,pady=2)
        ttk.Button(actions,text="Mở thư mục xuất",command=self.open_output).grid(row=1,column=2,sticky="ew",padx=2,pady=2)
        status_frame=ttk.Frame(center)
        status_frame.pack(fill="x",pady=(8,0))
        ttk.Label(status_frame,textvariable=self.run_stage,wraplength=440).pack(side="left")
        ttk.Label(status_frame,textvariable=self.run_elapsed).pack(side="right")
        ttk.Progressbar(center,variable=self.progress,maximum=100).pack(fill="x",pady=4)
        for var in (self.scene_status,self.balance_status):
            ttk.Label(center,textvariable=var,wraplength=500).pack(anchor="w",pady=1)
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
        self.split.add(self.log_panel, weight=2)
        self.root.after(200, lambda: self.resize_log(0.60))
        header = ttk.Frame(self.log_panel)
        header.pack(fill="x")
        ttk.Label(header, text="NHẬT KÝ XỬ LÝ", foreground=COLORS["accent"], font=("Segoe UI", 11, "bold")).pack(side="left")
        for label, fn in (("Xóa", lambda: self.log_box.delete("1.0", "end")),
                          ("Phóng to", lambda: self.resize_log(.18)),
                          ("Thu nhỏ", lambda: self.resize_log(.88)),
                          ("Mặc định", lambda: self.resize_log(.60))):
            ttk.Button(header, text=label, command=fn).pack(side="right", padx=2)
        body = ttk.Frame(self.log_panel)
        body.pack(fill="both", expand=True)
        self.log_box = tk.Text(body, height=10, bg="#0D141E", fg="#DDE9F5",
                               insertbackground="white", font=("Consolas", 11), relief="flat", wrap="word")
        for tag, color in (("warning","#FBBF24"),("error","#F87171"),("success","#4ADE80"),("info","#DDE9F5")):
            self.log_box.tag_configure(tag, foreground=color)
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.log_box.yview)
        scroll.pack(side="right", fill="y")
        self.log_box.configure(yscrollcommand=scroll.set)
        self.log_box.pack(side="left", fill="both", expand=True)

    def resize_log(self, fraction):
        self.split.sashpos(0, int(self.split.winfo_height()*fraction))

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
