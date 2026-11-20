"""Pre-export checks for planned video timelines. No third-party dependencies."""
from pathlib import Path
import json
import math

def validate(parts, config, log):
    errors, warnings = [], []
    if not parts:
        errors.append("Timeline rỗng.")
    fps = float(config.get("fps", 30) or 30)
    for part in parts:
        number = part.get("number", "?")
        voice = Path(str(part.get("voice", "")))
        if not voice.is_file():
            errors.append(f"Phần {number}: thiếu voice {voice}")
        clips = part.get("clips") or []
        if not clips:
            errors.append(f"Phần {number}: không có cảnh.")
            continue
        total = 0.0
        video_time = 0.0
        for index, clip in enumerate(clips, 1):
            src = Path(str(clip.get("source", "")))
            if not src.is_file():
                errors.append(f"Phần {number}, cảnh {index}: thiếu {src}")
            duration = float(clip.get("duration", 0) or 0)
            if not math.isfinite(duration) or duration <= 0:
                errors.append(f"Phần {number}, cảnh {index}: thời lượng không hợp lệ.")
                continue
            total += duration
            if clip.get("type") == "video":
                video_time += duration
        voice_duration = float(part.get("duration", 0) or 0)
        tolerance = max(0.2, 2.0 / max(1, fps))
        if abs(total - voice_duration) > tolerance:
            warnings.append(f"Phần {number}: cảnh {total:.2f}s, voice {voice_duration:.2f}s.")
        min_ratio = max(0, min(100, float(config.get("min_video_percent", 0) or 0)))
        actual = video_time / max(total, 0.001) * 100
        if actual + 0.01 < min_ratio:
            warnings.append(f"Phần {number}: video {actual:.1f}% dưới mức {min_ratio:.1f}%.")
    for message in errors:
        log("QA LỖI: " + message)
    for message in warnings:
        log("QA CẢNH BÁO: " + message)
    if errors:
        raise RuntimeError(f"QA phát hiện {len(errors)} lỗi. Dừng xuất để tránh dự án hỏng.")
    log(f"QA hoàn tất: {len(parts)} phần, {len(warnings)} cảnh báo.")
    return {"errors": errors, "warnings": warnings}
