# -*- coding: utf-8 -*-
"""Khiem Youtube Portable Full Offline builder.
Run: python build_portable.py
Logs: build_portable.log and build_error.txt (on failure).
"""
from __future__ import annotations
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist_portable"
WORK = ROOT / "build_portable_work"
NAME = "KhiemYoutube"
LOG = ROOT / "build_portable.log"
ERROR = ROOT / "build_error.txt"
REQUIRED_CLIP = ("config.json", "preprocessor_config.json")
REQUIRED_WHISPER = ("config.json", "model.bin")

def say(message):
    line = str(message)
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")

def find_models():
    candidates = [ROOT / "models"]
    env = os.environ.get("CAPCUT_AI_MODELS")
    if env:
        candidates.insert(0, Path(env))
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    found = {}
    for kind, repo in (("clip", "models--openai--clip-vit-base-patch32"),
                       ("whisper", "models--Systran--faster-whisper-base")):
        paths = [base / kind for base in candidates]
        paths += list((hub / repo / "snapshots").glob("*"))
        for p in paths:
            if kind == "clip":
                ok = all((p / n).is_file() for n in REQUIRED_CLIP) and (
                    (p / "model.safetensors").is_file() or (p / "pytorch_model.bin").is_file()
                ) and ((p / "tokenizer.json").is_file() or
                       ((p / "vocab.json").is_file() and (p / "merges.txt").is_file()))
            else:
                ok = all((p / n).is_file() for n in REQUIRED_WHISPER)
            if ok:
                found[kind] = p.resolve()
                break
    return found

def locate_binary(name):
    for p in (ROOT / "tools" / "ffmpeg" / name,
              ROOT / "ffmpeg" / "bin" / name,
              ROOT / name):
        if p.is_file():
            return p.resolve()
    result = shutil.which(name)
    return Path(result).resolve() if result else None

def main():
    LOG.write_text("", encoding="utf-8")
    ERROR.write_text("", encoding="utf-8")
    if os.name != "nt":
        raise RuntimeError("Chỉ hỗ trợ đóng gói trên Windows.")
    if not (ROOT / "khiem_ui.py").is_file():
        raise RuntimeError("Thiếu khiem_ui.py trong thư mục nguồn.")
    for package in ("PyInstaller", "torch", "transformers", "faster_whisper", "ctranslate2"):
        if importlib.util.find_spec(package) is None:
            raise RuntimeError("Thiếu thư viện " + package + ". Cài vào đúng Python đang build.")
    import torch
    say("PyTorch: " + torch.__version__ + " | CUDA: " + str(torch.cuda.is_available()))
    if tuple(int(x) for x in torch.__version__.split("+")[0].split(".")[:2]) < (2, 6):
        raise RuntimeError("PyTorch phải từ 2.6 để đọc CLIP pytorch_model.bin an toàn.")
    models = find_models()
    missing = [x for x in ("clip", "whisper") if x not in models]
    if missing:
        raise RuntimeError("Thiếu mô hình offline: " + ", ".join(missing) +
                           ". Hãy đặt trong models/ hoặc tải mô hình vào Hugging Face cache trước khi build.")
    ffmpeg = locate_binary("ffmpeg.exe")
    ffprobe = locate_binary("ffprobe.exe")
    if not ffmpeg or not ffprobe:
        raise RuntimeError("Thiếu ffmpeg.exe hoặc ffprobe.exe. Cài FFmpeg trên máy chính rồi build lại.")
    for kind, path in models.items():
        say("Model " + kind + ": " + str(path))
    say("FFmpeg: " + str(ffmpeg))
    say("FFprobe: " + str(ffprobe))
    DIST.mkdir(exist_ok=True)
    WORK.mkdir(exist_ok=True)

    # Frozen modules resolve __file__ under _internal; models are packaged there.
    # Runtime hook makes FFmpeg available to all subprocess calls, without PATH setup.
    hook = WORK / "khiem_portable_runtime.py"
    hook.write_text(
        "import os, sys\n"
        "from pathlib import Path\n"
        "base = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))\n"
        "binpath = base / 'tools' / 'ffmpeg'\n"
        "os.environ['PATH'] = str(binpath) + os.pathsep + os.environ.get('PATH', '')\n"
        "os.environ['CAPCUT_AI_MODELS'] = str(base / 'models')\n",
        encoding="utf-8"
    )
    command = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onedir", "--windowed", "--name", NAME,
        "--distpath", str(DIST), "--workpath", str(WORK),
        "--specpath", str(WORK), "--paths", str(ROOT),
        "--runtime-hook", str(hook),
        "--collect-submodules", "faster_whisper",
        "--collect-submodules", "ctranslate2",
        "--collect-submodules", "tokenizers",
        "--collect-submodules", "transformers.models.clip",
        "--module-collection-mode", "asyncio:py",
        "--module-collection-mode", "unittest:py",
        "--collect-data", "transformers",
        "--collect-data", "tokenizers",
    ]
    def add_data(source, target):
        command.extend(["--add-data", str(source) + os.pathsep + target])
    for kind, path in models.items():
        add_data(path, "models/" + kind)
    add_data(ffmpeg, "tools/ffmpeg")
    add_data(ffprobe, "tools/ffmpeg")
    for folder in ("template",):
        if (ROOT / folder).is_dir():
            add_data(ROOT / folder, folder)
    for filename in ("capcut_v11_reference.json",):
        if (ROOT / filename).is_file():
            add_data(ROOT / filename, filename)
    command.append(str(ROOT / "khiem_ui.py"))
    say("Đang đóng gói Full Offline, có thể mất nhiều thời gian...")
    with LOG.open("a", encoding="utf-8") as logfile:
        process = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True,
                                   errors="replace", bufsize=1)
        for line in process.stdout:
            print(line, end="", flush=True)
            logfile.write(line)
            logfile.flush()
        code = process.wait()
    if code:
        raise RuntimeError("PyInstaller thất bại, mã lỗi " + str(code) +
                           ". Xem build_portable.log và build_error.txt.")
    output = DIST / NAME
    exe = output / (NAME + ".exe")
    internal = output / "_internal"
    checks = [exe, internal / "models" / "clip" / "config.json",
              internal / "models" / "whisper" / "model.bin",
              internal / "tools" / "ffmpeg" / "ffmpeg.exe",
              internal / "tools" / "ffmpeg" / "ffprobe.exe"]
    missing_files = [str(x) for x in checks if not x.is_file()]
    if missing_files:
        raise RuntimeError("Đóng gói thiếu file: " + "; ".join(missing_files))
    # Build a small independent updater EXE, separate from the frozen main application.
    updater_cmd = [
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--onefile", "--windowed", "--name", "KhiemUpdater",
        "--distpath", str(output), "--workpath", str(WORK / "updater"),
        "--specpath", str(WORK), str(ROOT / "portable_updater.py")
    ]
    say("Đang tạo KhiemUpdater.exe...")
    updater_result = subprocess.run(updater_cmd, cwd=ROOT, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, errors="replace")
    with LOG.open("a", encoding="utf-8") as logfile:
        logfile.write(updater_result.stdout)
    if updater_result.returncode or not (output / "KhiemUpdater.exe").is_file():
        raise RuntimeError("Không tạo được KhiemUpdater.exe. Xem build_portable.log.")
    (output / "README_PORTABLE.txt").write_text(
        "KHIEM YOUTUBE PORTABLE FULL OFFLINE\n"
        "Chép toàn bộ thư mục KhiemYoutube sang máy khác, chạy KhiemYoutube.exe.\n"
        "Đã kèm CLIP, Whisper, FFmpeg, FFprobe và thư viện Python được PyInstaller thu thập.\n"
        "GPU NVIDIA cần driver tương thích; CapCut cần cài riêng nếu xuất dự án CapCut.\n"
        "Các mô hình AI khác dùng bởi Tab 05 có thể cần kiểm tra riêng.\n"
        "Không tự cập nhật EXE từ GitHub. Build lại khi cập nhật mã nguồn.\n",
        encoding="utf-8"
    )
    say("DONE: " + str(output))
    say("Hãy thử EXE và CLIP trên máy chính trước khi ZIP gửi máy khác.")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        error = traceback.format_exc()
        print(error, flush=True)
        with ERROR.open("w", encoding="utf-8") as fh:
            fh.write(error)
            fh.write("\nNhật ký chi tiết: " + str(LOG) + "\n")
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(error)
        sys.exit(1)
