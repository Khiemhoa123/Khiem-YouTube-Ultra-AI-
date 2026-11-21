"""Fast, non-rendering preflight for sequential project jobs."""
from pathlib import Path
import shutil
import re

MEDIA = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}
IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
AUDIO = {".mp3", ".wav", ".m4a", ".flac"}

def _files(path, extensions):
    root = Path(str(path or ""))
    if not root.is_dir():
        return []
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in extensions]

def inspect(config, mode, other_jobs=()):
    errors, warnings = [], []
    name = str(config.get("name", "")).strip()
    if not name or re.search(r'[<>:"/\\|?*]', name):
        errors.append("Tên dự án trống hoặc chứa ký tự không hợp lệ")
    for field, label in (("voice", "Voice"), ("txt", "TXT"), ("images", "Ảnh"),
                         ("videos", "Video"), ("out", "Đầu ra")):
        if not Path(str(config.get(field) or "")).is_dir():
            errors.append("Thiếu thư mục " + label)
    if config.get("project_folder"):
        try:
            from auto_project_v11 import discover
            found = discover(config["project_folder"], config.get("interview_file"))
            voice, txt = list(found["voice"].values()), list(found["txt"].values())
            images, videos = found["images"], found["videos"]
        except (ValueError, OSError) as exc:
            errors.append(str(exc))
            voice, txt, images, videos = [], [], [], []
    else:
        voice = _files(config.get("voice"), AUDIO)
        txt = _files(config.get("txt"), {".txt"})
        images = _files(config.get("images"), IMAGES)
        videos = _files(config.get("videos"), MEDIA)
    if not voice: errors.append("Không có file Voice hợp lệ")
    if not txt: errors.append("Không có file TXT hợp lệ")
    if not images and not videos: errors.append("Không có ảnh hoặc video nguồn")
    if not images: warnings.append("Không có ảnh, sẽ chỉ dùng video nếu phần dựng hỗ trợ")
    if not videos: warnings.append("Không có video, không thể đạt tỉ lệ video tối thiểu")
    if voice and txt and len(voice) != len(txt):
        errors.append("Số file Voice (%d) khác TXT (%d)" % (len(voice), len(txt)))
    def index(path):
        m = re.match(r"^\s*(\d+)(?=\D|$)", path.stem)
        return int(m.group(1)) if m else None
    for label, files in (("Voice", voice), ("TXT", txt)):
        numbers = [index(p) for p in files]
        if len(numbers) != len(set(numbers)) and None not in numbers:
            errors.append(label + " có số thứ tự bị trùng")
        if None in numbers and files:
            warnings.append(label + " có file không bắt đầu bằng số thứ tự")
    if voice and txt and all(index(p) is not None for p in voice + txt):
        if {index(p) for p in voice} != {index(p) for p in txt}:
            errors.append("Số thứ tự Voice và TXT không khớp")
    for p in voice + txt + images + videos:
        try:
            if p.stat().st_size == 0:
                errors.append("File rỗng: " + p.name)
        except OSError:
            errors.append("Không đọc được: " + p.name)
    if config.get("interview_enabled"):
        interviews = _files(config.get("interview_folder"), MEDIA)
        if not interviews:
            warnings.append("Không có video interview, chương trình sẽ bỏ qua intro")
        try:
            if not 1 <= float(config.get("interview_max_seconds", 30)) <= 30:
                errors.append("Intro phải từ một đến ba mươi giây")
        except (TypeError, ValueError):
            errors.append("Thời lượng intro không hợp lệ")
    if mode == "render" and not shutil.which("ffmpeg"):
        warnings.append("Không tìm thấy FFmpeg trong PATH, kiểm tra bản FFmpeg đi kèm")
    if mode == "capcut":
        draft = Path(str(config.get("draft_root") or ""))
        if not draft.is_dir():
            errors.append("Không tìm thấy thư mục dự án CapCut")
    output = Path(str(config.get("out") or ""))
    if output.is_dir():
        try:
            free = shutil.disk_usage(output).free
            if free < 2 * 1024**3:
                warnings.append("Ổ đĩa còn dưới 2 GB trống")
        except OSError:
            warnings.append("Không kiểm tra được dung lượng ổ đĩa")
    for other in other_jobs:
        if other.get("id") == config.get("_queue_id"):
            continue
        if other.get("status") not in ("pending", "running", "ready", "warning"):
            continue
        c = other.get("config", {})
        if c.get("name") == name and c.get("out") == config.get("out"):
            errors.append("Trùng tên và thư mục xuất với dự án " + str(other.get("name")))
            break
    return {"status": "error" if errors else ("warning" if warnings else "ready"),
            "errors": errors, "warnings": warnings,
            "counts": {"voice": len(voice), "txt": len(txt),
                       "images": len(images), "videos": len(videos)}}
