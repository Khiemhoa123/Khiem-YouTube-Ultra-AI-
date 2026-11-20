
import csv
import hashlib
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from datetime import datetime
from collections import defaultdict

IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VIDEOS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".flac"}


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1048576), b""):
            h.update(chunk)
    return h.hexdigest()


def picture_hash(path):
    from PIL import Image, ImageOps

    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im = im.convert("L").resize((9, 8))
        pixels = list(im.getdata())

    result = 0
    for y in range(8):
        for x in range(8):
            a = pixels[y * 9 + x]
            b = pixels[y * 9 + x + 1]
            result = (result << 1) | int(a > b)
    return result


def duration(path):
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1",
            str(path)
        ],
        capture_output=True,
        text=True,
        timeout=30,
        creationflags=getattr(
            subprocess, "CREATE_NO_WINDOW", 0
        )
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip())
    return float(result.stdout.strip())


def inspect(folder, output, notify):
    root = Path(folder)
    files = sorted(
        p for p in root.rglob("*")
        if p.is_file()
        and p.suffix.lower() in IMAGES | VIDEOS | AUDIO
    )

    results = []
    hashes = defaultdict(list)
    pictures = []

    for index, path in enumerate(files, 1):
        name = str(path.relative_to(root))
        notify(f"Kiểm tra {index}/{len(files)}: {name}")

        try:
            if path.stat().st_size == 0:
                results.append(("LỖI", name, "File rỗng"))
                continue

            hashes[file_hash(path)].append(name)

            if path.suffix.lower() in IMAGES:
                try:
                    pictures.append(
                        (name, picture_hash(path))
                    )
                except Exception as exc:
                    results.append((
                        "LỖI ẢNH", name, str(exc)
                    ))

            if path.suffix.lower() in VIDEOS | AUDIO:
                try:
                    seconds = duration(path)
                    if seconds <= 0:
                        results.append((
                            "LỖI", name,
                            "Thời lượng không hợp lệ"
                        ))
                except Exception as exc:
                    results.append((
                        "CẢNH BÁO", name,
                        "Không đọc được thời lượng: "
                        + str(exc)[:180]
                    ))

        except Exception as exc:
            results.append((
                "LỖI", name, str(exc)[:180]
            ))

    for group in hashes.values():
        if len(group) > 1:
            results.append((
                "TRÙNG CHÍNH XÁC",
                group[0],
                "Trùng với: " + ", ".join(group[1:])
            ))

    # dHash: phát hiện ảnh có bố cục gần giống.
    # So sánh toàn bộ cặp ảnh, phù hợp bộ tư liệu nhỏ.
    for i in range(len(pictures)):
        name_a, hash_a = pictures[i]

        for j in range(i + 1, len(pictures)):
            name_b, hash_b = pictures[j]
            distance = (hash_a ^ hash_b).bit_count()

            if distance <= 5:
                results.append((
                    "ẢNH GẦN GIỐNG",
                    name_a,
                    f"{name_b} | dHash={distance}"
                ))

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = output / f"QUALITY_V72_{stamp}.csv"

    with report.open(
        "w", encoding="utf-8-sig", newline=""
    ) as f:
        writer = csv.writer(f)
        writer.writerow([
            "Mức độ", "File", "Chi tiết"
        ])
        writer.writerows(results)

    return len(files), len(results), report


class QualityApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(
            "KHIÊM YOUTUBE V7.2 QUALITY CONTROL"
        )
        self.root.geometry("780x480")
        self.root.configure(bg="#101722")

        self.folder = tk.StringVar()
        self.output = tk.StringVar(
            value=str(
                Path.home() / "Desktop"
                / "KHIEM_QUALITY_REPORTS"
            )
        )

        self.build()

    def choose(self, variable):
        selected = filedialog.askdirectory()
        if selected:
            variable.set(selected)

    def build(self):
        panel = tk.Frame(
            self.root, bg="#1b2635",
            padx=20, pady=20
        )
        panel.pack(
            fill="both", expand=True,
            padx=20, pady=20
        )

        tk.Label(
            panel, text="KHIÊM YOUTUBE",
            bg="#1b2635", fg="white",
            font=("Segoe UI", 21, "bold")
        ).pack(anchor="w")

        tk.Label(
            panel, text="V7.2 QUALITY CONTROL",
            bg="#1b2635", fg="#23c7b7"
        ).pack(anchor="w", pady=(0, 18))

        for title, variable in [
            ("Thư mục ảnh / video / voice", self.folder),
            ("Thư mục xuất báo cáo", self.output)
        ]:
            tk.Label(
                panel, text=title,
                bg="#1b2635", fg="white"
            ).pack(anchor="w")

            row = tk.Frame(panel, bg="#1b2635")
            row.pack(fill="x", pady=(5, 12))

            tk.Entry(
                row, textvariable=variable
            ).pack(
                side="left", fill="x", expand=True
            )

            tk.Button(
                row, text="CHỌN",
                command=lambda v=variable: self.choose(v),
                bg="#23c7b7"
            ).pack(side="left", padx=6)

        tk.Button(
            panel,
            text="KIỂM TRA CHẤT LƯỢNG",
            command=self.run_check,
            bg="#23c7b7",
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", pady=12)

        self.log = tk.Text(
            panel, height=9,
            bg="#0e1724", fg="white"
        )
        self.log.pack(fill="both", expand=True)

    def run_check(self):
        source = Path(self.folder.get())
        output = Path(self.output.get())

        if not source.is_dir():
            messagebox.showerror(
                "Lỗi", "Chọn thư mục tư liệu"
            )
            return

        self.log.delete("1.0", "end")
        self.root.update_idletasks()

        def notify(text):
            self.log.insert("end", text + "\n")
            self.log.see("end")
            self.root.update_idletasks()

        try:
            total, issues, report = inspect(
                source, output, notify
            )
            notify(
                f"\nHOÀN THÀNH: {total} file, "
                f"{issues} mục cần xem."
            )
            notify(f"Báo cáo: {report}")

            messagebox.showinfo(
                "Hoàn thành",
                f"Đã kiểm tra {total} file.\n"
                f"Phát hiện {issues} mục cần xem.\n\n"
                f"{report}"
            )

        except Exception as exc:
            messagebox.showerror(
                "Lỗi kiểm tra", str(exc)
            )

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    QualityApp().run()
