"""Optional interview intro: speech matching, preview selection, MP4 prepend.
Requires ffmpeg/ffprobe and faster-whisper. Original interview sound is retained.
"""
from pathlib import Path
import json
import re
import subprocess
import tempfile
import os
import random

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
        log("INTERVIEW: TXT mở đầu trống, tìm câu chuyện hoàn chỉnh không cần khớp kịch bản.")
    model = None
    try:
        from whisper_audio_fix_v11 import get_model, transcribe_media
        log("WHISPER: Đang nạp mô hình nhận diện tiếng nói.")
        model = get_model()
        log("WHISPER: Mô hình sẵn sàng.")
    except Exception as exc:
        log("Whisper không sẵn sàng, chuyển sang chọn interview dự phòng: " + str(exc))
    if model is None:
        log("Bỏ Interview: không có Whisper để xác nhận lời nói.")
        return None
    max_seconds = min(30.0, max(1.0, float(c.get("interview_max_seconds", 30))))
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
            if model is None:
                continue
            log(f"WHISPER: Giải mã âm thanh {path.name} ({duration:.1f}s).")
            rows = _sample_rows(path, duration, model, log)
            sampled[str(path)] = rows
            log(f"INTERVIEW: {len(rows)} đoạn mẫu.")
            # One continuous thought: start after a sentence boundary, end at punctuation.
            for i, first in enumerate(rows):
                if i and rows[i-1].text.strip() and not rows[i-1].text.rstrip().endswith((".", "?", "!")):
                    continue
                for j in range(i, min(len(rows), i + 30)):
                    last = rows[j]
                    dur = float(last.end - first.start)
                    if dur > max_seconds:
                        break
                    if dur < 5 or dur > max_seconds:
                        continue
                    if not last.text.rstrip().endswith((".", "?", "!")):
                        continue
                    phrase = " ".join(s.text.strip() for s in rows[i:j + 1])
                    if len(_tokens(phrase)) < 12:
                        continue
                    score = _similarity(script, phrase)
                    # Prefer coherent passages with complete ending punctuation.
                    if phrase.rstrip().endswith((".", "?", "!")):
                        score += 0.03
                    item = (score, str(path), float(first.start), dur, phrase)
                    candidates.append(item)
                    fallback.append(item)
        except Exception as exc:
            log("Không phân tích được " + path.name + ": " + str(exc))
    if candidates:
        candidates.sort(reverse=True)
        best = candidates[0]
        log("Top đoạn phỏng vấn (điểm khớp từ ngữ, chưa xác minh khuôn mặt):")
        for score, path, start, dur, phrase in candidates[:3]:
            log(f"  {Path(path).name} | {start:.1f}s | {dur:.1f}s | {score:.2f} | {phrase[:100]}")
        if best[0] >= 0.12 and _similarity(script, best[4]) >= 0.09:
            c['_interview_sample_rows'] = [(r.start,r.end,r.text) for r in sampled[best[1]]]
            return {'source':best[1], 'source_start':best[2], 'duration':best[3], 'transcript':best[4], 'score':best[0], 'selection_mode':'matched'}
    if fallback:
        def curiosity(item):
            phrase = item[4]
            return (2 if '?' in phrase else 1 if '!' in phrase else 0) + (1 if phrase.rstrip().endswith(('.', '?', '!')) else 0) + min(len(_tokens(phrase)), 24)/24
        ranked = sorted(fallback, key=lambda item: (curiosity(item), min(item[3], 24)), reverse=True)
        score, path, start, dur, phrase = random.SystemRandom().choice(ranked[:5])
        c['_interview_sample_rows'] = [(r.start,r.end,r.text) for r in sampled[path]]
        log(f'INTERVIEW DU PHONG: {Path(path).name} | {start:.1f}s | {dur:.1f}s | co loi noi, chua xac minh khuon mat.')
        return {'source':path, 'source_start':start, 'duration':dur, 'transcript':phrase, 'score':score, 'selection_mode':'spoken_fallback'}
    log('Bỏ Interview: không tìm được câu chuyện liền mạch, kết thúc trọn câu trong giới hạn thời lượng.')
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
    """Two-second silent visual cutaways; preserve narration and section durations.

    Only reuse footage from the selected interview source. This does NOT verify
    speaker identity, so the operator must ensure the source features the subject.
    """
    import copy
    if not intro or not c.get("interview_enabled", False):
        return parts
    source = str(intro["source"])
    try:
        info = _probe(source)
        length = float(info.get("format", {}).get("duration", 0) or 0)
        if length < 4 or not any(st.get("codec_type") == "video" for st in info.get("streams", [])):
            log("INTERVIEW CUTAWAY: Nguồn không đủ video.")
            return parts
    except Exception as exc:
        log("INTERVIEW CUTAWAY: Không kiểm tra được video: " + str(exc))
        return parts

    fps = max(1, int(c.get("fps", 30)))
    frames2 = 2 * fps
    rows = c.get("_interview_sample_rows", [])
    opening_start = float(intro.get("source_start", 0))
    reserved = [(opening_start, opening_start + float(intro.get("duration", 0)))]
    samples = []
    for a, b, phrase in rows:
        a, b = float(a), float(b)
        if b - a < 2.0:
            continue
        for t in (a, max(a, (a + b - 2) / 2)):
            if t + 2 <= length and not any(t < y + 1 and t + 2 > x - 1 for x, y in reserved):
                samples.append(t)
    samples = sorted(set(samples))
    if not samples:
        raise RuntimeError("Không đủ đoạn video Interview 2 giây ngoài Opening.")

    def splice(clips, t, src_t, number):
        for index, old in enumerate(clips):
            left = int(round((t - float(old["start"])) * fps))
            total = int(old["frames"])
            right = total - left - frames2
            if left < 0 or right < 0:
                continue
            if t + 2 > float(old["start"]) + total / fps + 0.001:
                continue
            result = []
            if left:
                before = copy.deepcopy(old)
                before["frames"] = left
                before["duration"] = left / fps
                result.append(before)
            result.append(dict(part=number, type="video", source=source,
                               source_start=src_t, start=t, frames=frames2,
                               duration=2.0, effect="Tĩnh", interview_cutaway=True))
            if right:
                after = copy.deepcopy(old)
                after["start"] = t + 2
                after["frames"] = right
                after["duration"] = right / fps
                if after["type"] == "video":
                    after["source_start"] = float(old["source_start"]) + (left + frames2) / fps
                result.append(after)
            return clips[:index] + result + clips[index + 1:]
        return None

    inserted = 0
    for p in sorted(parts, key=lambda x: x.get("number", 0)):
        number = int(p.get("number", 0))
        if number < 1:
            continue
        clips = p.get("clips", [])
        if not clips:
            continue
        part_start = min(float(cl["start"]) for cl in clips)
        duration = float(p.get("duration", 0))
        if duration < 2:
            raise RuntimeError(f"Number {number} ngắn hơn 2 giây, không thể chèn Interview.")
        # Exactly one opening visual, plus two or three evenly spaced cutaways.
        extra = 3 if duration >= 120 else 2
        positions = [part_start] + [part_start + round((duration - 2) * i / (extra + 1) * fps) / fps for i in range(1, extra + 1)]
        placed = 0
        for t in positions:
            available = [x for x in samples if not any(x < b + 1 and x + 2 > a - 1 for a, b in reserved)]
            if not available:
                log(f"INTERVIEW Number {number}: Thiếu đoạn nguồn không trùng, đã chèn {placed}/{len(positions)}.")
                break
            # Prefer a deterministic variety of source positions, never repeat.
            source_t = available[(number + placed * 7) % len(available)]
            updated = splice(clips, t, source_t, number)
            if updated is None:
                log(f"INTERVIEW Number {number}: Không thể đặt cutaway tại {t:.2f}s.")
                continue
            clips = updated
            reserved.append((source_t, source_t + 2))
            placed += 1
            inserted += 1
        if placed < 1:
            raise RuntimeError(f"Number {number}: không thể chèn đoạn Interview 2 giây. Hãy bổ sung video Interview.")
        p["clips"] = clips
        log(f"INTERVIEW Number {number}: Đã chèn {placed}/{len(positions)} đoạn hình ảnh, mỗi đoạn 2 giây.")
    log(f"INTERVIEW: Tổng {inserted} cutaway 2 giây, không thay đổi độ dài voice.")
    return parts
