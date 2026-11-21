# -*- coding: utf-8 -*-
"""Build a Windows folder-based portable distribution of Khiem YouTube.

Run on Windows in the same Python environment that runs khiem_ui.py:
    python build_portable.py

Requires: python -m pip install pyinstaller
"""
from pathlib import Path
import importlib.util
import os
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist_portable"
WORK = ROOT / "build_portable_work"
NAME = "KhiemYoutube"

def main():
    if os.name != "nt":
        raise SystemExit("Portable Windows must be built on Windows.")
    if importlib.util.find_spec("PyInstaller") is None:
        raise SystemExit("Chua co PyInstaller. Chay: python -m pip install pyinstaller")
    if not (ROOT / "khiem_ui.py").is_file():
        raise SystemExit("Khong tim thay khiem_ui.py")
    DIST.mkdir(exist_ok=True)
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onedir", "--windowed", "--name", NAME,
        "--distpath", str(DIST), "--workpath", str(WORK),
        "--specpath", str(WORK),
        "--paths", str(ROOT),
        "--collect-submodules", "faster_whisper",
        "--collect-submodules", "ctranslate2",
        "--collect-submodules", "tokenizers",
        str(ROOT / "khiem_ui.py"),
    ]
    # Include only small application resources, never personal project folders.
    for folder in ("template",):
        path = ROOT / folder
        if path.is_dir():
            command[command.index(str(ROOT / "khiem_ui.py")):command.index(str(ROOT / "khiem_ui.py"))] = [
                "--add-data", str(path) + os.pathsep + folder
            ]
    for filename in ("capcut_v11_reference.json",):
        path = ROOT / filename
        if path.is_file():
            command[command.index(str(ROOT / "khiem_ui.py")):command.index(str(ROOT / "khiem_ui.py"))] = [
                "--add-data", str(path) + os.pathsep + filename
            ]
    print("Building portable folder... This may take several minutes.")
    subprocess.run(command, cwd=ROOT, check=True)
    output = DIST / NAME
    (output / "README_PORTABLE.txt").write_text(
        "KHIEM YOUTUBE PORTABLE\\n\\n"
        "1. Copy the ENTIRE KhiemYoutube folder to another Windows PC.\\n"
        "2. Run KhiemYoutube.exe. Do not move the EXE outside its folder.\\n"
        "3. Install CapCut separately if using CapCut exports.\\n"
        "4. Install FFmpeg and ensure ffmpeg/ffprobe are on PATH for MP4 features.\\n"
        "5. AI models may need separate installation or download.\\n"
        "6. Re-select project folders and CapCut draft folder on the new PC.\\n"
        "7. This packaged EXE does NOT update itself from Python source updates.\\n"
        "   Rebuild the portable folder when a new software version is released.\\n"
        "8. Keep channel media and private settings outside the package when possible.\\n",
        encoding="utf-8"
    )
    print("DONE:", output)
    print("Copy the WHOLE folder. The source GitHub updater cannot patch the packaged EXE.")

if __name__ == "__main__":
    main()
