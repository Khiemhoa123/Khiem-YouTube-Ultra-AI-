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

def _sample_rows(path, duration, model, log):
    from whisper_audio_fix_v11 import transcribe_media
    # Bounded sampling: at most three 25-second windows per source.
    offsets = sorted(set(round(max(0, duration-25)*f, 2) for f in (0.12, 0.48, 0.78)))
    rows = []
    from types import SimpleNamespace
    with tempfile.TemporaryDirectory() as td:
        for offset in offsets:
            wav = Path(td)/"sample.wav"
            _run(["ffmpeg","-v","error","-y","-ss",str(offset),"-i",str(path),"-t","25","-vn","-ac","1","-ar","16000",str(wav)])
            segments, _ = transcribe_media(wav, model=model, vad_filter=True, beam_size=1)
            for seg in segments:
                rows.append(SimpleNamespace(start=float(seg.start)+offset,end=float(seg.end)+offset,text=seg.text))
    return rows

def choose_intro(c, log):
    """Return optional intro dict. Never silently select a low-confidence passage."""
    folder = str(c.get("interview_folder", "")).strip()
    if not c.get("interview_enabled") or not folder:
        return None
    root = Path(folder)
    if not root.is_dir():
        log("Bỏ Interview: thư mục không tồn tại."); return None
    videos = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in VIDEO_EXT]
    if not videos:
        log("Bỏ Interview: không có video."); return None
    script = _script_text(c["txt"])
    if not script.strip():
        log("Bỏ Interview: thiếu TXT mở đầu."); return None
    model = None
    try:
        from whisper_audio_fix_v11 import get_model, transcribe_media
        log("WHISPER: Đang nạp mô hình nhận diện tiếng nói.")
        model = get_model()
        log("WHISPER: Mô hình sẵn sàng.")
    except Exception as exc:
        log("Whisper không sẵn sàng, chuyển sang chọn interview dự phòng: " + str(exc))
    if model is None: return None
    max_seconds = min(8.0, max(5.0, float(c.get("interview_max_seconds", 8))))
    sampled = {}
    candidates = []
    fallback = []
    log(f"INTERVIEW: Tìm thấy {len(videos)} video.")
    for index, path in enumerate(sorted(videos)[:5], 1):
        try:
            log(f"INTERVIEW {index}/{len(videos)}: Kiểm tra {path.name}")
            info = _probe(path)
            if not any(s.get("codec_type") == "audio" for s in info["streams"]):
                log("Bỏ qua video không có tiếng: " + path.name)
                continue
            duration = float(info.get("format", {}).get("duration", 0) or 0)
            if duration > 0.5:
                fallback.append((str(path), duration))
            if model is None:
                continue
            log(f"WHISPER: Giải mã âm thanh {path.name} ({duration:.1f}s).")
            rows = _sample_rows(path, duration, model, log)
            sampled[str(path)] = rows
            log(f"INTERVIEW: {len(rows)} đoạn mẫu.")
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
        if best[0] < 0.12 or _similarity(script, best[4]) < 0.09:
            log("Bỏ Interview: không có đoạn đủ phù hợp.")
            return None
        c["_interview_sample_rows"] = [(r.start,r.end,r.text) for r in sampled[best[1]]]
        return {"source": best[1], "source_start": best[2],
                "duration": best[3], "transcript": best[4], "score": best[0]}
    log("Bỏ Interview: không có đoạn phù hợp.")
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
    """Story-first cutaways. Never insert solely to satisfy a scene quota.

    Uses transcript overlap as a conservative relevance gate, not a claim of
    face identification or automatic lip synchronization.
    """
    import copy
    if not intro or not c.get("interview_enabled", False):
        return parts
    source = str(intro["source"])
    try:
        length = float(_probe(source).get("format", {}).get("duration", 0) or 0)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        log("SMART STORY: Không đọc được interview: " + str(exc))
        return parts
    if length < 2:
        return parts

    # Only use spoken interview passages we can actually understand.
    try:
        from types import SimpleNamespace
        rows = [SimpleNamespace(start=a,end=b,text=t) for a,b,t in c.get("_interview_sample_rows", [])]
        if not rows: return parts
    except Exception as exc:
        log("SMART STORY: Không xác minh được nội dung interview, bỏ qua cutaway: " + str(exc))
        return parts

    # Read numbered scripts using the same naming/index rules as the main editor.
    try:
        import app as engine
        if c.get("project_folder"):
            from auto_project_v11 import discover
            scripts = discover(c["project_folder"], c.get("interview_file"))["txt"]
        else:
            scripts = engine.indexed(c["txt"], {".txt"})
    except Exception as exc:
        log("SMART STORY: Không đọc được kịch bản Number: " + str(exc))
        return parts

    stop = set("the a an and or but is are was were it i you we they he she to of in on for with at from that this those these my your his her our their have has had do did not so as by be been can could would should when what who where how just very about then than there here".split())
    def keywords(value):
        return {w for w in re.findall(r"[a-z]{3,}", value.lower()) if w not in stop}

    source_segments = []
    reserved = [(float(intro.get("source_start", 0)),
                 float(intro.get("source_start", 0)) + float(intro["duration"]))]
    for row in rows:
        start = max(0.0, float(row.start))
        end = min(length, float(row.end))
        if end - start < 1.5:
            continue
        for t in (start, max(start, (start + end - 2) / 2)):
            if t + 2 > length:
                continue
            if any(not (t + 2 <= a - 1 or t >= b + 1) for a, b in reserved):
                continue
            source_segments.append((t, keywords(row.text), row.text.strip()))
    if not source_segments:
        log("SMART STORY: Không có câu phỏng vấn hợp lệ ngoài Opening.")
        return parts

    fps = max(1, int(round(float(c.get("fps", 30)))))
    cut_frames = 2 * fps
    min_gap = 45.0
    timeline_ends = []
    inserted_total = 0
    for p in sorted(parts, key=lambda x: min((float(z["start"]) for z in x.get("clips", [])), default=0)):
        number = int(p.get("number", 0))
        if number <= 1 or number not in scripts:
            continue
        clips = p.get("clips", [])
        if not clips:
            continue
        script = scripts[number].read_text(encoding="utf-8-sig", errors="replace")
        script_words = script.split()
        if not script_words:
            continue
        part_start = min(float(x["start"]) for x in clips)
        duration = float(p.get("duration", 0))
        part_end = part_start + duration
        if duration < 35:
            continue

        # Match each possible insertion to the script spoken around that time.
        ranked = []
        for index, clip in enumerate(clips):
            frames = int(clip.get("frames", 0))
            if frames < cut_frames + 2 * fps:
                continue
            before = (frames - cut_frames) // 2
            t = float(clip["start"]) + before / fps
            if t < part_start + 5 or t + 2 > part_end - 5:
                continue
            fraction = max(0.0, min(1.0, (t - part_start) / duration))
            mid = int(fraction * len(script_words))
            context = keywords(" ".join(script_words[max(0, mid - 35):mid + 35]))
            if not context:
                continue
            for source_t, source_words, spoken in source_segments:
                common = context & source_words
                # At least two informative matching words. No match = no cutaway.
                if len(common) < 2:
                    continue
                score = len(common) / max(1, len(source_words))
                ranked.append((score, t, index, before, source_t, spoken, common))
        ranked.sort(key=lambda item: item[0], reverse=True)
        placed = 0
        # Re-evaluate positions after each insertion, preserving original scene time.
        selected_times = []
        for score, t, index, before, source_t, spoken, common in ranked:
            if placed >= 4:
                break
            if any(not (t >= end + min_gap or t + 2 + min_gap <= end - 2)
                   for end in timeline_ends):
                continue
            if any(abs(t - existing) < min_gap + 2 for existing in selected_times):
                continue
            if any(not (source_t + 2 <= a - 1 or source_t >= b + 1)
                   for a, b in reserved):
                continue
            # Locate original clip by its stable timeline position after splits.
            actual_index = next((i for i, cl in enumerate(clips)
                                 if float(cl["start"]) <= t + 0.0001
                                 and float(cl["start"]) + float(cl["duration"]) >= t + 2 - 0.0001
                                 and int(cl["frames"]) >= cut_frames + 2), None)
            if actual_index is None:
                continue
            original = clips[actual_index]
            before_frames = round((t - float(original["start"])) * fps)
            after_frames = int(original["frames"]) - before_frames - cut_frames
            if before_frames < 1 or after_frames < 1:
                continue
            first = copy.deepcopy(original)
            first["frames"] = before_frames
            first["duration"] = before_frames / fps
            cut = dict(part=number, type="video", source=source,
                       source_start=source_t, start=t, frames=cut_frames,
                       duration=2.0, effect="Tĩnh", interview_cutaway=True)
            last = copy.deepcopy(original)
            last["start"] = t + 2
            last["frames"] = after_frames
            last["duration"] = after_frames / fps
            if last["type"] == "video":
                last["source_start"] = float(original["source_start"]) + (before_frames + cut_frames) / fps
            clips = clips[:actual_index] + [first, cut, last] + clips[actual_index + 1:]
            reserved.append((source_t, source_t + 2))
            timeline_ends.append(t + 2)
            selected_times.append(t)
            placed += 1
            inserted_total += 1
            log(f"SMART STORY Number {number}: {t:.1f}s, interview {source_t:.1f}s, khớp: {', '.join(sorted(common))[:90]}")
        p["clips"] = clips
        if not placed:
            log(f"SMART STORY Number {number}: Không có interview đủ liên quan, không chèn.")
    log(f"SMART STORY: {inserted_total} interview cutaway có đối chiếu nội dung, không ép số lượng.")
    return parts
