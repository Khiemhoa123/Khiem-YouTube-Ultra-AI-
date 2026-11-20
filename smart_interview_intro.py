# -*- coding: utf-8 -*-
"""Khiem YouTube: find a coherent interview intro, maximum 30 seconds.

Standalone first release. No changes to app.py, render, or CapCut timeline.
Requires ffmpeg, ffprobe and faster-whisper (pip install faster-whisper).
"""
from pathlib import Path
import json
import math
import re
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
MAX_SECONDS = 30.0
WINDOW = 30.0
STOPWORDS = set("the and with from that this have were they their about when what would there into your you are for but not who was she his her him its then been one two three most ever great greatest people loved".split())


def words(s):
    return [w for w in re.findall(r"[\w']+", s.casefold()) if len(w) > 2 and w not in STOPWORDS]


def similarity(a, b):
    x, y = set(words(a)), set(words(b))
    return len(x & y) / math.sqrt(len(x) * len(y)) if x and y else 0.0


def ffprobe(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                       capture_output=True, text=True, timeout=45)
    if p.returncode:
        raise RuntimeError(p.stderr.strip() or "ffprobe failed")
    return float(p.stdout.strip())


def collect(folder):
    return sorted(p for p in Path(folder).rglob("*")
                  if p.is_file() and p.suffix.lower() in VIDEO)


def scan(folder, script, log, model_size="base", language="en"):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg and FFprobe must be on PATH")
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Install dependency: pip install faster-whisper") from exc
    files = collect(folder)
    if not files:
        raise ValueError("No interview videos found")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    ranked = []
    for path in files:
        log("Transcribing " + path.name)
        try:
            duration = ffprobe(path)
            segments, info = model.transcribe(str(path), language=language or None,
                                              vad_filter=True, beam_size=3)
            chunks = [(float(s.start), float(s.end), s.text.strip())
                      for s in segments if s.text.strip()]
            for i in range(len(chunks)):
                start = chunks[i][0]
                if start >= duration:
                    continue
                selected = []
                end = start
                for a, b, t in chunks[i:]:
                    if b - start > MAX_SECONDS:
                        break
                    if a - end > 2.5 and selected:
                        break
                    selected.append(t)
                    end = b
                if end - start < 5.0:
                    continue
                transcript = " ".join(selected)
                score = similarity(script, transcript)
                # A short, coherent passage with natural speech boundaries.
                quality = min((end - start) / 12.0, 1.0)
                ranked.append({"file": str(path), "start": round(start, 2),
                               "end": round(end, 2), "duration": round(end-start, 2),
                               "score": round(score * 0.85 + quality * 0.15, 4),
                               "relevance": round(score, 4),
                               "transcript": transcript})
        except Exception as exc:
            log("SKIP " + path.name + ": " + str(exc))
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:20]


def export_clip(candidate, output):
    """Preserve original interview sound. Reencode for accurate cut."""
    src = Path(candidate["file"])
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.resolve() == src.resolve():
        raise ValueError("Output must differ from source")
    length = min(MAX_SECONDS, float(candidate["end"]) - float(candidate["start"]))
    if length <= 0:
        raise ValueError("Invalid selection")
    cmd = ["ffmpeg", "-hide_banner", "-y", "-ss", str(candidate["start"]),
           "-i", str(src), "-t", str(length), "-map", "0:v:0",
           "-map", "0:a:0", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "19", "-pix_fmt", "yuv420p", "-c:a", "aac",
           "-b:a", "192k", "-movflags", "+faststart", str(output)]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if p.returncode:
        raise RuntimeError(p.stderr[-1800:])
    output.with_suffix(".json").write_text(json.dumps(candidate, ensure_ascii=False, indent=2), encoding="utf-8")
    return output


class Window:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Khiem YouTube | SMART INTERVIEW INTRO")
        self.root.geometry("900x680")
        self.folder = tk.StringVar()
        self.script = tk.StringVar()
        self.results = []
        self.busy = False
        for label, var, choose in [
            ("Interview videos folder", self.folder, self.choose_folder),
            ("Opening TXT", self.script, self.choose_script),
        ]:
            row = tk.Frame(self.root)
            row.pack(fill="x", padx=12, pady=5)
            tk.Label(row, text=label, width=22, anchor="w").pack(side="left")
            tk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)
            tk.Button(row, text="Browse", command=choose).pack(side="left")
        tk.Label(self.root, text="Top candidates. Original video + original audio. Maximum 30 seconds.").pack()
        self.listbox = tk.Listbox(self.root, height=8, exportselection=False)
        self.listbox.pack(fill="x", padx=12)
        tk.Button(self.root, text="Analyze interviews", command=self.analyze).pack(pady=5)
        tk.Button(self.root, text="Export selected interview MP4", command=self.export).pack(pady=5)
        self.logbox = scrolledtext.ScrolledText(self.root)
        self.logbox.pack(fill="both", expand=True, padx=12, pady=10)
        self.log("First release: selects speech by transcript relevance, not face identity or automatic logo removal.")
        self.log("Review selected interview for correct speaker and usage rights before publishing.")

    def log(self, text):
        self.root.after(0, lambda: (self.logbox.insert("end", str(text) + "\n"),
                                    self.logbox.see("end")))

    def choose_folder(self):
        value = filedialog.askdirectory()
        if value:
            self.folder.set(value)

    def choose_script(self):
        value = filedialog.askopenfilename(filetypes=[("Text", "*.txt")])
        if value:
            self.script.set(value)

    def worker(self, job):
        if self.busy:
            return
        self.busy = True
        def run():
            try:
                job()
            except Exception as exc:
                self.log("ERROR: " + str(exc))
            finally:
                self.busy = False
        threading.Thread(target=run, daemon=True).start()

    def analyze(self):
        folder, script_path = self.folder.get(), self.script.get()
        if not Path(folder).is_dir() or not Path(script_path).is_file():
            messagebox.showwarning("Missing input", "Select interview folder and opening TXT")
            return
        def job():
            script = Path(script_path).read_text(encoding="utf-8-sig")
            results = scan(folder, script, self.log)
            self.root.after(0, lambda: self.show_results(results))
        self.worker(job)

    def show_results(self, results):
        self.results = results
        self.listbox.delete(0, tk.END)
        for item in results:
            self.listbox.insert(tk.END, f'{Path(item["file"]).name} | {item["start"]:.1f}s | {item["duration"]:.1f}s | score {item["score"]:.3f}')
        if results:
            self.listbox.selection_set(0)
            self.log("Best transcript: " + results[0]["transcript"])
        else:
            self.log("No coherent 5-30 second candidate found.")

    def export(self):
        selected = self.listbox.curselection()
        if not selected:
            messagebox.showwarning("Select clip", "Analyze and select a candidate")
            return
        candidate = self.results[selected[0]]
        output = filedialog.asksaveasfilename(defaultextension=".mp4",
                                             initialfile="interview_intro.mp4",
                                             filetypes=[("MP4", "*.mp4")])
        if output:
            self.worker(lambda: self.log("Saved: " + str(export_clip(candidate, output))))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    Window().run()
