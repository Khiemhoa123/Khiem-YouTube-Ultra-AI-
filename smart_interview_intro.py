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
        log("Không đọc được TXT mở đầu; ưu tiên đoạn phỏng vấn có tiếng.")
    model = None
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
    except Exception as exc:
        log("Whisper không sẵn sàng, chuyển sang chọn interview dự phòng: " + str(exc))
    max_seconds = min(30.0, max(1.0, float(c.get("interview_max_seconds", 30))))
    candidates = []
    fallback = []
    for path in videos:
        try:
            info = _probe(path)
            if not any(s.get("codec_type") == "audio" for s in info["streams"]):
                log("Bỏ qua video không có tiếng: " + path.name)
                continue
            duration = float(info.get("format", {}).get("duration", 0) or 0)
            if duration > 0.5:
                fallback.append((str(path), duration))
            if model is None:
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
    if candidates:
        candidates.sort(reverse=True)
        best = candidates[0]
        log("Top đoạn phỏng vấn (điểm khớp từ ngữ, chưa xác minh khuôn mặt):")
        for score, path, start, dur, phrase in candidates[:3]:
            log(f"  {Path(path).name} | {start:.1f}s | {dur:.1f}s | {score:.2f} | {phrase[:100]}")
        if best[0] < 0.045:
            log("CẢNH BÁO: Không có đoạn khớp nội dung. Dùng đoạn phỏng vấn dự phòng có lời nói.")
        return {"source": best[1], "source_start": best[2],
                "duration": best[3], "transcript": best[4], "score": best[0]}
    if fallback:
        # No transcribed passage; use a valid source with original sound.
        # Keep the intro short and never exceed the configured 30-second cap.
        path, duration = sorted(fallback, key=lambda item: item[1], reverse=True)[0]
        seconds = min(max_seconds, 12.0, duration)
        if seconds > 0.5:
            log(f"CẢNH BÁO: Whisper không tìm thấy lời thoại. Dùng intro dự phòng {Path(path).name} ({seconds:.1f}s), giữ tiếng gốc.")
            return {"source": path, "source_start": 0.0,
                    "duration": seconds, "transcript": "", "score": 0.0}
    log("CẢNH BÁO: Không có video phỏng vấn kèm âm thanh hợp lệ. Bỏ qua intro, tiếp tục xuất bình thường.")
    return None

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


def insert_interview_cutaways(parts, intro, c, log):
    """Silent two-second interview cutaways with global spacing and source dedup.

    The manually selected interview is the only cutaway source. Identity cannot
    be verified automatically, so source identity must be checked by the editor.
    """
    import copy
    if not intro or not c.get("interview_enabled", False):
        return parts
    source = str(intro["source"])
    try:
        info = _probe(source)
        length = float(info.get("format", {}).get("duration", 0) or 0)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        log("CẢNH BÁO: Không phân tích được interview: " + str(exc))
        return parts
    if length < 2.0:
        return parts
    fps = max(1, int(round(float(c.get("fps", 30)))))
    cut_frames = 2 * fps
    gap = 45.0
    # Reserve the intro source interval; never use it as a cutaway.
    used_source = [(float(intro.get("source_start", 0)),
                    float(intro.get("source_start", 0)) + float(intro["duration"]))]
    global_cutaways = []
    count = 0

    def get_source():
        # Search disjoint two-second windows with safety padding on both sides.
        for n in range(int(max(0, length - 2) // 3) + 1):
            st = float(n * 3)
            if st + 2 > length:
                break
            if all(st >= end + 1 or st + 2 <= start - 1
                   for start, end in used_source):
                used_source.append((st, st + 2))
                return st
        return None

    # Work in absolute timeline coordinates. Re-evaluate candidates after
    # each insertion and do not rely on the order of Number processing.
    for p in sorted(parts, key=lambda part: float(part.get("clips", [{}])[0].get("start", 0))):
        clips = p.get("clips", [])
        duration = float(p.get("duration", 0))
        if not clips or duration < 35:
            continue
        part_start = min(float(x["start"]) for x in clips)
        part_end = part_start + duration
        target = min(4, max(1, int(duration / 55 + 0.5)))
        inserted = 0
        for k in range(target):
            desired = part_start + duration * (k + 1) / (target + 1)
            candidates = []
            for index, clip in enumerate(clips):
                frames = int(clip.get("frames", 0))
                if frames < cut_frames + 2 * fps:
                    continue
                before = (frames - cut_frames) // 2
                t = float(clip["start"]) + before / fps
                if t < part_start + 5 or t + 2 > part_end - 5:
                    continue
                if any(not (t >= other + 2 + gap or other >= t + 2 + gap)
                       for other in global_cutaways):
                    continue
                candidates.append((abs(t - desired), index, before, t))
            if not candidates:
                continue
            source_start = get_source()
            if source_start is None:
                log("CẢNH BÁO: Hết đoạn interview chưa sử dụng, không lặp cảnh.")
                break
            _, index, before, t = min(candidates)
            clip = clips[index]
            after = int(clip["frames"]) - before - cut_frames
            first = copy.deepcopy(clip)
            first["frames"] = before
            first["duration"] = before / fps
            cut = dict(part=clip.get("part", p.get("number")), type="video",
                       source=source, source_start=source_start,
                       start=t, frames=cut_frames, duration=2.0,
                       effect="Tĩnh", interview_cutaway=True)
            last = copy.deepcopy(clip)
            last["start"] = t + 2.0
            last["frames"] = after
            last["duration"] = after / fps
            if last["type"] == "video":
                last["source_start"] = float(clip["source_start"]) + (before + cut_frames) / fps
            clips = clips[:index] + [first, cut, last] + clips[index + 1:]
            global_cutaways.append(t)
            inserted += 1
            count += 1
        p["clips"] = clips
        log(f"Number {p.get('number', '?')}: {inserted} interview cutaway.")
    log(f"SMART INTERVIEW: {count} cảnh 2 giây, khoảng cách >= {gap:.0f}s, không trùng nguồn hoặc Opening.")
    return parts
