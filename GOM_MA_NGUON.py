
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox
from pathlib import Path
from datetime import datetime

SKIP = {
    ".git", ".venv", "venv", "__pycache__",
    "models", "cache", "caches", "temp", "tmp",
    "video", "videos", "ảnh", "images", "audio",
    "voice", "voices", "output", "outputs",
    "dist", "build", "node_modules"
}

CONFIG_FILES = {
    "requirements.txt", "pyproject.toml",
    "config.json", "settings.json",
    "config.ini", "config.yaml", "config.yml",
    "run.bat", "start.bat"
}

SECRET = re.compile(
    r"api[_-]?key|password|passwd|secret|"
    r"access[_-]?token|refresh[_-]?token|"
    r"authorization|private[_-]?key",
    re.IGNORECASE
)

MAX_FILE = 300000
MAX_TOTAL = 2500000


def main():
    window = tk.Tk()
    window.withdraw()
    window.attributes("-topmost", True)

    folder = filedialog.askdirectory(
        title="Chon thu muc KHIEM YOUTUBE"
    )

    if not folder:
        return

    root = Path(folder)
    collected = []
    skipped = []
    total = 0
    warnings = 0

    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(
            d for d in dirs
            if d.lower() not in SKIP
            and not d.startswith(".")
        )

        for name in sorted(files):
            path = Path(current) / name

            if (
                path.suffix.lower() != ".py"
                and name.lower() not in CONFIG_FILES
            ):
                continue

            try:
                size = path.stat().st_size

                if size > MAX_FILE or total + size > MAX_TOTAL:
                    skipped.append(str(path.relative_to(root)))
                    continue

                content = path.read_text(
                    encoding="utf-8-sig",
                    errors="replace"
                )

                clean_lines = []

                for line in content.splitlines():
                    if SECRET.search(line):
                        warnings += 1
                        clean_lines.append(
                            "[REDACTED: POSSIBLE SECRET]"
                        )
                    else:
                        clean_lines.append(line)

                collected.append((
                    str(path.relative_to(root)),
                    "\n".join(clean_lines)
                ))

                total += size

            except Exception as error:
                skipped.append(f"{name}: {error}")

    output = Path.home() / "Desktop"
    if not output.is_dir():
        output = Path.home()

    destination = output / "KHIEM_SOURCE_REVIEW.txt"

    if destination.exists():
        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
        destination = output / (
            f"KHIEM_SOURCE_REVIEW_{timestamp}.txt"
        )

    with destination.open(
        "w", encoding="utf-8"
    ) as f:

        f.write("KHIEM YOUTUBE SOURCE COLLECTOR\n")
        f.write(f"Folder: {root}\n")
        f.write(f"Files: {len(collected)}\n")
        f.write(f"Secret warnings: {warnings}\n\n")

        f.write("FILE LIST\n")
        for name, _ in collected:
            f.write(name + "\n")

        f.write("\nSKIPPED FILES\n")
        for name in skipped:
            f.write(name + "\n")

        for name, content in collected:
            f.write("\n" + "=" * 65 + "\n")
            f.write("FILE: " + name + "\n")
            f.write("=" * 65 + "\n")
            f.write(content + "\n")

    messagebox.showinfo(
        "KHIEM YOUTUBE",
        "DA GOM MA NGUON THANH CONG!\n\n"
        f"So file: {len(collected)}\n"
        f"Canh bao: {warnings}\n\n"
        f"File: {destination}\n\n"
        "Kiem tra noi dung truoc khi chia se."
    )

    print("HOAN THANH:", destination)


if __name__ == "__main__":
    main()
