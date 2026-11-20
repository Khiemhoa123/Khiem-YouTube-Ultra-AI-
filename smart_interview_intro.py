"""Optional interview intro: speech matching, preview selection, MP4 prepend.
Requires ffmpeg/ffprobe and faster-whisper. Original interview sound is retained.
"""
from pathlib import Path
import json
import re
import subprocess
import tempfile
import os

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"}

def _run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

def _probe(path):
    return json.loads(_run(["ffprobe", "-v", "error", "-show_streams",
                            "-show_format", "-of", "json", str(path)]).stdout)

def _tokens(text):
    return set(re.findall(r"\w+", text.lower(), flags=re.UNICODE))

def _similarity(a, b):
    x, y = _tokens(a), _tokens(b)
    if not x or not y:
        return 0.0
    return len(x & y) / max(1, len(x | y))

def _script_text(folder):
    files = sorted(Path(folder).glob("*.txt"))
    if not files:
        return ""
    return files[0].read_text(encoding="utf-8-sig", errors="replace")[:6000]

def choose_intro(c, log):
    """Return optional intro dict. Never silently select a low-confidence passage."""
    folder = str(c.get("interview_folder", "")).strip()
    if not c.get("interview_enabled") or not folder:
        return None
    root = Path(folder)
    if not root.is_dir():
        raise ValueError("Thư mục phỏng vấn không tồn tại: " + folder)
    videos = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXT]
    if not videos:
        raise ValueError("Thư mục phỏng vấn không có video")
    script = _script_text(c["txt"])
    if not script.strip():
        raise ValueError("Không đọc được TXT mở đầu")
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError("Cài faster-whisper: py -m pip install faster-whisper") from exc
    model = WhisperModel("base", device="cpu", compute_type="int8")
    max_seconds = min(30.0, max(1.0, float(c.get("interview_max_seconds", 30))))
    candidates = []
    for path in videos:
        try:
            info = _probe(path)
            if not any(s.get("codec_type") == "audio" for s in info["streams"]):
                log("Bỏ qua video không có tiếng: " + path.name)
                continue
            segments, _ = model.transcribe(str(path), vad_filter=True, beam_size=3)
            rows = list(segments)
            # Sliding windows over complete Whisper segments. No mid-sentence cut.
            for i, first in enumerate(rows):
                for j in range(i, min(len(rows), i + 12)):
                    last = rows[j]
                    dur = float(last.end - first.start)
                    if dur > max_seconds:
                        break
                    if dur < 5:
                        continue
                    phrase = " ".join(s.text.strip() for s in rows[i:j + 1])
                    score = _similarity(script, phrase)
                    # Prefer coherent passages with complete ending punctuation.
                    if phrase.rstrip().endswith((".", "?", "!")):
                        score += 0.03
                    candidates.append((score, str(path), float(first.start), dur, phrase))
        except Exception as exc:
            log("Không phân tích được " + path.name + ": " + str(exc))
    if not candidates:
        raise ValueError("Không tìm thấy đoạn phỏng vấn có âm thanh hợp lệ")
    candidates.sort(reverse=True)
    best = candidates[0]
    log("Top đoạn phỏng vấn (điểm khớp từ ngữ, chưa xác minh khuôn mặt):")
    for score, path, start, dur, phrase in candidates[:3]:
        log(f"  {Path(path).name} | {start:.1f}s | {dur:.1f}s | {score:.2f} | {phrase[:100]}")
    if best[0] < 0.045:
        raise ValueError("Chưa có đoạn phỏng vấn đủ khớp TXT. Hãy chọn tư liệu khác hoặc tắt intro.")
    return {"source": best[1], "source_start": best[2],
            "duration": best[3], "transcript": best[4], "score": best[0]}

def prepend_mp4(c, intro, log):
    """Prepend interview with original sound. Re-encode for reliable A/V sync."""
    if not intro:
        return
    dest = Path(c["out"]) / (c["name"] + ".mp4")
    if not dest.is_file():
        raise FileNotFoundError(dest)
    w, h = map(int, c["res"].split("x"))
    fps = int(c["fps"])
    with tempfile.TemporaryDirectory() as td:
        output = Path(td) / "with_intro.mp4"
        fit = (f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
               f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p")
        graph = (f"[0:v]trim=start=0:duration={intro['duration']},setpts=PTS-STARTPTS,"
                 f"{fit}[v0];"
                 f"[1:v]setpts=PTS-STARTPTS,{fit}[v1];"
                 f"[0:a]atrim=start=0:duration={intro['duration']},asetpts=PTS-STARTPTS,"
                 "aresample=48000,aformat=channel_layouts=stereo[a0];"
                 "[1:a]asetpts=PTS-STARTPTS,aresample=48000,"
                 "aformat=channel_layouts=stereo[a1];"
                 "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]")
        # -ss before input ensures intro begins at the selected source offset.
        cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(intro["source_start"]),
               "-i", intro["source"], "-i", str(dest), "-filter_complex", graph,
               "-map", "[v]", "-map", "[a]", "-c:v", "libx264",
               "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
               "-movflags", "+faststart", str(output)]
        _run(cmd)
        os.replace(output, dest)
    log("Đã ghép phỏng vấn gốc vào đầu MP4: " + str(dest))
