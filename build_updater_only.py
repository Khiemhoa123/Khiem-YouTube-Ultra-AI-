# -*- coding: utf-8 -*-
"""Build only KhiemUpdater.exe. Does not rebuild the 4 GB main application."""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
source = root / "portable_updater.py"
destination = root / "dist_portable" / "KhiemYoutube"
if not source.is_file() or not (destination / "KhiemYoutube.exe").is_file():
    raise SystemExit("LOI: Thieu portable_updater.py hoac dist_portable/KhiemYoutube/KhiemYoutube.exe")
try:
    import PyInstaller  # noqa
except ImportError:
    raise SystemExit("LOI: Chua cai PyInstaller vao Python dang su dung")
print("Dang build rieng KhiemUpdater.exe...", flush=True)
command = [
    sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
    "--onefile", "--windowed", "--name", "KhiemUpdater",
    "--distpath", str(destination),
    "--workpath", str(root / "build_portable_work" / "updater_only"),
    "--specpath", str(root / "build_portable_work"),
    str(source),
]
result = subprocess.run(command, cwd=root)
if result.returncode:
    raise SystemExit("LOI: Build updater that bai")
updater = destination / "KhiemUpdater.exe"
if not updater.is_file():
    raise SystemExit("LOI: Khong tim thay KhiemUpdater.exe")
print("THANH CONG:", updater, flush=True)
print("Luu y: Phai copy KhiemUpdater.exe moi sang ban sao Portable tren may nhan truoc khi thu multipart.", flush=True)
