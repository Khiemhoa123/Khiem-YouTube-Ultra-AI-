
"""
KHIEM YOUTUBE V8.0
AI QUALITY ENGINE

- Detect exact duplicate files
- Detect near-duplicate images
- Inspect image and video files
- Produce approved media list
- Preserve all original media
- Does not modify CapCut
"""

import csv
import hashlib
import json
import subprocess
import threading
import tkinter as tk

from pathlib import Path
from datetime import datetime
from tkinter import filedialog, messagebox

from PIL import Image, ImageOps, ImageFile

Image.MAX_IMAGE_PIXELS = 200_000_000

IMAGE_EXT = {
    ".jpg", ".jpeg", ".png",
    ".webp", ".bmp"
}

VIDEO_EXT = {
    ".mp4", ".mov", ".mkv",
    ".avi", ".webm"
}


def sha256_file(path):
    digest = hashlib.sha256()

    with open(path, "rb") as file:
        while True:
            chunk = file.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def image_hash(path):
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        image = image.convert("L")
        image = image.resize((9, 8))

        pixels = list(image.getdata())

    value = 0

    for y in range(8):
        for x in range(8):
            left = pixels[y * 9 + x]
            right = pixels[y * 9 + x + 1]

            value = (
                (value << 1)
                | int(left > right)
            )

    return value


def video_duration(path):
    process = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path)
        ],
        capture_output=True,
        text=True,
        timeout=40,
        creationflags=getattr(
            subprocess, "CREATE_NO_WINDOW", 0
        )
    )

    if process.returncode != 0:
        raise RuntimeError(
            process.stderr.strip()
            or "FFprobe failed"
        )

    value = float(process.stdout.strip())

    if not 0 < value < float("inf"):
        raise ValueError(
            "Invalid video duration"
        )

    return value


def scan_media(folder, output):
    source = Path(folder).resolve()
    destination = Path(output).resolve()

    if not source.is_dir():
        raise ValueError(
            "Media folder does not exist"
        )

    files = sorted(
        path for path in source.rglob("*")
        if path.is_file()
        and path.suffix.lower()
        in IMAGE_EXT | VIDEO_EXT
        and destination not in path.parents
    )

    records = []
    seen_sha = {}
    seen_images = []

    for index, path in enumerate(files, 1):
        record = {
            "file": str(path),
            "type": (
                "image"
                if path.suffix.lower() in IMAGE_EXT
                else "video"
            ),
            "status": "APPROVED",
            "reason": "",
            "duplicate_of": "",
            "duration": "",
        }

        try:
            if path.stat().st_size == 0:
                raise ValueError("Empty file")

            checksum = sha256_file(path)

            if checksum in seen_sha:
                record["status"] = "DUPLICATE"
                record["reason"] = "Exact SHA256 match"
                record["duplicate_of"] = (
                    seen_sha[checksum]
                )
            else:
                seen_sha[checksum] = str(path)

                if record["type"] == "image":
                    perceptual = image_hash(path)

                    closest = None
                    best_distance = 65

                    for old_hash, old_path in seen_images:
                        distance = (
                            perceptual ^ old_hash
                        ).bit_count()

                        if distance < best_distance:
                            best_distance = distance
                            closest = old_path

                    if (
                        closest is not None
                        and best_distance <= 5
                    ):
                        record["status"] = "REVIEW"
                        record["reason"] = (
                            "Similar image, dHash="
                            + str(best_distance)
                        )
                        record["duplicate_of"] = closest

                    # Keep the first representative.
                    # Review images do not become
                    # additional representatives.
                    if record["status"] == "APPROVED":
                        seen_images.append(
                            (perceptual, str(path))
                        )

                else:
                    record["duration"] = round(
                        video_duration(path), 3
                    )

        except Exception as error:
            record["status"] = "ERROR"
            record["reason"] = str(error)[:300]

        records.append(record)

    destination.mkdir(
        parents=True,
        exist_ok=True
    )

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    report_path = (
        destination
        / f"V8_QUALITY_{stamp}.csv"
    )

    approved_path = (
        destination
        / f"V8_APPROVED_{stamp}.json"
    )

    fields = [
        "file",
        "type",
        "status",
        "reason",
        "duplicate_of",
        "duration"
    ]

    with report_path.open(
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:
        writer = csv.DictWriter(
            file, fieldnames=fields
        )
        writer.writeheader()
        writer.writerows(records)

    approved = [
        item for item in records
        if item["status"] == "APPROVED"
    ]

    approved_path.write_text(
        json.dumps(
            {
                "version": "8.0",
                "created": datetime.now().isoformat(),
                "source_folder": str(source),
                "approved_media": approved,
            },
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    summary = {
        "total": len(records),
        "approved": len(approved),
        "duplicate": sum(
            r["status"] == "DUPLICATE"
            for r in records
        ),
        "review": sum(
            r["status"] == "REVIEW"
            for r in records
        ),
        "error": sum(
            r["status"] == "ERROR"
            for r in records
        ),
        "report": str(report_path),
        "approved_file": str(approved_path),
    }

    return summary


class QualityWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(
            "KHIEM YOUTUBE V8.0 AI QUALITY"
        )
        self.root.geometry("800x480")
        self.root.configure(bg="#111a27")

        self.folder = tk.StringVar()
        self.output = tk.StringVar(
            value=str(
                Path(__file__).resolve().parent
                / "V8_REPORTS"
            )
        )

        self.running = False
        self.build()

    def add_path(self, parent, title, variable):
        tk.Label(
            parent,
            text=title,
            fg="white",
            bg="#1c2a3b",
            anchor="w"
        ).pack(fill="x", pady=(12, 4))

        row = tk.Frame(
            parent, bg="#1c2a3b"
        )
        row.pack(fill="x")

        tk.Entry(
            row,
            textvariable=variable,
            font=("Segoe UI", 10)
        ).pack(
            side="left",
            fill="x",
            expand=True
        )

        tk.Button(
            row,
            text="CHON",
            command=lambda: self.choose(variable),
            bg="#23c8bc"
        ).pack(side="left", padx=8)

    def choose(self, variable):
        folder = filedialog.askdirectory()

        if folder:
            variable.set(folder)

    def build(self):
        panel = tk.Frame(
            self.root,
            bg="#1c2a3b",
            padx=22,
            pady=20
        )
        panel.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=20
        )

        tk.Label(
            panel,
            text="KHIEM YOUTUBE",
            font=("Segoe UI", 22, "bold"),
            fg="white",
            bg="#1c2a3b"
        ).pack(anchor="w")

        tk.Label(
            panel,
            text="V8.0 AI QUALITY ENGINE",
            fg="#23c8bc",
            bg="#1c2a3b"
        ).pack(anchor="w")

        self.add_path(
            panel,
            "Thu muc anh va video",
            self.folder
        )

        self.add_path(
            panel,
            "Thu muc bao cao",
            self.output
        )

        self.button = tk.Button(
            panel,
            text="QUET VA LOC TU LIEU",
            command=self.start,
            bg="#23c8bc",
            font=("Segoe UI", 11, "bold")
        )
        self.button.pack(
            fill="x",
            pady=18
        )

        self.status = tk.Label(
            panel,
            text="San sang",
            fg="white",
            bg="#1c2a3b",
            justify="left",
            anchor="nw"
        )
        self.status.pack(
            fill="both",
            expand=True
        )

    def start(self):
        if self.running:
            return

        folder = self.folder.get().strip()
        output = self.output.get().strip()

        if not Path(folder).is_dir():
            messagebox.showerror(
                "Loi",
                "Hay chon thu muc tu lieu"
            )
            return

        if not output:
            messagebox.showerror(
                "Loi",
                "Hay chon thu muc bao cao"
            )
            return

        self.running = True
        self.button.config(state="disabled")
        self.status.config(
            text="Dang phan tich tu lieu..."
        )

        threading.Thread(
            target=self.worker,
            args=(folder, output),
            daemon=True
        ).start()

    def worker(self, folder, output):
        try:
            result = scan_media(
                folder, output
            )
            self.root.after(
                0,
                lambda r=result: self.finished(r)
            )
        except Exception as error:
            message = str(error)
            self.root.after(
                0,
                lambda m=message: self.failed(m)
            )

    def finished(self, result):
        self.running = False
        self.button.config(state="normal")

        text = (
            f"Tong: {result['total']}\n"
            f"Hop le: {result['approved']}\n"
            f"Trung: {result['duplicate']}\n"
            f"Gan giong: {result['review']}\n"
            f"Loi: {result['error']}\n\n"
            f"Bao cao:\n{result['report']}\n\n"
            f"Danh sach duoc duyet:\n"
            f"{result['approved_file']}"
        )

        self.status.config(text=text)
        messagebox.showinfo(
            "Hoan thanh",
            text
        )

    def failed(self, message):
        self.running = False
        self.button.config(state="normal")
        self.status.config(
            text="Loi: " + message
        )
        messagebox.showerror(
            "Loi kiem tra",
            message
        )

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    QualityWindow().run()
