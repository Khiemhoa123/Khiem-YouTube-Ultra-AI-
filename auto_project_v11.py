"""One-folder source discovery for Khiem YouTube V11.

No source files are moved or copied. Voice/TXT match by leading numeric ID.
Images/videos are shared pools for every narration section.
"""
from pathlib import Path
import re

AUDIO = {".mp3", ".wav", ".m4a", ".flac"}
TEXT = {".txt"}
IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VIDEOS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mts", ".mpeg", ".mpg"}

def _excluded(p):
    return any(x.lower() in {"__pycache__", ".git", "models", "cache", "exports", "output"}
               for x in p.parts)

def discover(root, interview=None):
    base = Path(root).expanduser().resolve()
    if not base.is_dir():
        raise ValueError("Thư mục dự án không tồn tại: " + str(base))
    interview_path = Path(interview).resolve() if interview and Path(interview).is_file() else None
    result = {"voice": {}, "txt": {}, "images": [], "videos": []}
    for p in sorted(base.rglob("*"), key=lambda p: str(p).casefold()):
        if not p.is_file() or _excluded(p.relative_to(base)):
            continue
        suffix = p.suffix.lower()
        if suffix in AUDIO or suffix in TEXT:
            m = re.match(r"^\s*(\d+)(?=\D|$)", p.stem)
            if not m:
                # Sidecars and unrelated text/audio are not narration sections.
                continue
            n = int(m.group(1))
            key = "voice" if suffix in AUDIO else "txt"
            if n in result[key]:
                raise ValueError("Trùng số phần %s: %s và %s" %
                                 (n, result[key][n], p))
            result[key][n] = p
        elif suffix in IMAGES:
            result["images"].append(p)
        elif suffix in VIDEOS and p.resolve() != interview_path:
            result["videos"].append(p)
    if not result["voice"]:
        raise ValueError("Không tìm thấy Voice có số thứ tự trong thư mục chung")
    if set(result["voice"]) != set(result["txt"]):
        missing_txt = sorted(set(result["voice"]) - set(result["txt"]))
        missing_voice = sorted(set(result["txt"]) - set(result["voice"]))
        raise ValueError("Voice/TXT không khớp. Thiếu TXT: %s; thiếu Voice: %s" %
                         (missing_txt, missing_voice))
    if not result["images"] and not result["videos"]:
        raise ValueError("Không tìm thấy ảnh hoặc video trong thư mục chung")
    return result
