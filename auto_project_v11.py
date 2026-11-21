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
    result = {"voice": {}, "txt": {}, "images": [], "videos": [], "duplicates": []}
    candidates = {"voice": {}, "txt": {}}
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
            candidates[key].setdefault(n, []).append(p)
        elif suffix in IMAGES:
            result["images"].append(p)
        elif suffix in VIDEOS and p.resolve() != interview_path:
            result["videos"].append(p)
    def _name_key(path):
        stem = re.sub(r"^\s*\d+\s*[-_. ]*", "", path.stem.lower())
        stem = re.sub(r"(?:[-_. ]+(?:full|final|voice|audio|copy|backup|bak|v\d+))+$", "", stem)
        return re.sub(r"[^a-z0-9]+", "", stem)

    def _rank(path, opposite):
        name = path.stem.lower()
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        paired = any(_name_key(path) == _name_key(other) for other in opposite)
        bad = bool(re.search(r"(?:backup|bak|copy|old|test|draft)", name))
        final = bool(re.search(r"(?:^|[-_. ])(?:full|final)(?:$|[-_. ])", name))
        return (int(size > 0), int(paired), int(not bad), int(final), size, str(path).casefold())

    # Reject empty/unreadable candidates before ranking. An unusable duplicate
    # must not win just because it has a better filename.
    for kind in ("voice", "txt"):
        for n, files in list(candidates[kind].items()):
            usable = []
            for p in files:
                try:
                    with p.open("rb") as handle:
                        head = handle.read(16)
                    if not head:
                        raise ValueError("empty file")
                    if kind == "txt":
                        p.read_text(encoding="utf-8-sig")
                    usable.append(p)
                except (OSError, UnicodeError, ValueError) as exc:
                    result["duplicates"].append({
                        "kind": kind, "number": n, "selected": None,
                        "ignored": [str(p)], "reason": str(exc)
                    })
            candidates[kind][n] = usable

    for kind in ("voice", "txt"):
        other = "txt" if kind == "voice" else "voice"
        for n, files in candidates[kind].items():
            ranked = sorted(files, key=lambda p: _rank(p, candidates[other].get(n, [])), reverse=True)
            if not ranked:
                continue
            result[kind][n] = ranked[0]
            if len(ranked) > 1:
                result["duplicates"].append({
                    "kind": kind, "number": n, "selected": str(ranked[0]),
                    "ignored": [str(p) for p in ranked[1:]]
                })
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
