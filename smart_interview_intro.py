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
    max_seconds = min(30.0, max(1.0, float(c.get("interview_max_seconds", 30))))
    sampled = {}
    candidates = []
    fallback = []
    audio_sources = []
    log(f"INTERVIEW: Tìm thấy {len(videos)} video.")
    for index, path in enumerate(sorted(videos)[:5], 1):
        try:
            log(f"INTERVIEW {index}/{len(videos)}: Kiểm tra {path.name}")
            info = _probe(path)
            if not any(s.get("codec_type") == "audio" for s in info["streams"]):
                log("Bỏ qua video không có tiếng: " + path.name)
                continue
            duration = float(info.get("format", {}).get("duration", 0) or 0)
            if not any(st.get("codec_type") == "video" for st in info["streams"]) or duration < 4:
                log("Bỏ qua nguồn Interview quá ngắn hoặc thiếu hình: " + path.name)
                continue
            audio_sources.append((str(path), duration))
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
                    if dur < min(10.0, max_seconds) or dur > max_seconds:
                        continue
                    if not last.text.rstrip().endswith((".", "?", "!")):
                        continue
                    phrase = " ".join(s.text.strip() for s in rows[i:j + 1])
                    if len(_tokens(phrase)) < 18:
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
            return (2 if '?' in phrase else 1 if '!' in phrase else 0) + min(len(_tokens(phrase)), 36)/36
        ranked = sorted(fallback, key=lambda item: (curiosity(item), min(item[3], 24)), reverse=True)
        score, path, start, dur, phrase = random.SystemRandom().choice(ranked[:5])
        c['_interview_sample_rows'] = [(r.start,r.end,r.text) for r in sampled[path]]
        log(f'INTERVIEW: Chon cau noi tron ven {dur:.1f}s trong {Path(path).name}.')
        return {'source':path, 'source_start':start, 'duration':dur,
                'transcript':phrase, 'score':score, 'selection_mode':'spoken_fallback'}
    # Do not substitute an arbitrary audio segment: it can end mid-sentence.
    # Fail explicitly rather than create a misleading, abruptly cut interview.
    raise RuntimeError(
        'Khong tim duoc doan hoi thoai tron ven trong gioi han thoi luong. '
        'Hay them video Interview co loi noi ro rang hoac kiem tra Whisper.')
    log('INTERVIEW: Khong co video hop le co ca hinh va am thanh trong 5 file dau.')
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
    """Insert one unique silent two-second Interview visual per Number.

    Do not reuse the opening interview footage or repeat cutaway intervals.
    The voice track and each section's total duration remain unchanged.
    """
    import copy
    if not intro or not c.get("interview_enabled", False):
        return parts
    root = Path(str(c.get("interview_folder", "")).strip())
    sources = []
    for path in sorted(root.rglob("*")) if root.is_dir() else []:
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXT:
            continue
        try:
            info = _probe(path)
            length = float(info.get("format", {}).get("duration", 0) or 0)
            if length >= 2.0 and any(st.get("codec_type") == "video" for st in info.get("streams", [])):
                sources.append((str(path), length))
        except Exception as exc:
            log("INTERVIEW: Bo qua nguon khong doc duoc " + path.name + ": " + str(exc))
    if not sources:
        raise RuntimeError("Khong co video Interview hop le de chen cutaway 2 giay.")

    fps = max(1, int(c.get("fps", 30)))
    frames2 = 2 * fps
    intro_source = str(Path(intro["source"]).resolve())
    intro_start = float(intro.get("source_start", 0))
    intro_end = intro_start + float(intro.get("duration", 0))
    reserved = {intro_source: [(intro_start, intro_end)]}
    number_parts = [p for p in parts if re.search(r"\\bnumber\\b", str(p.get("title", p.get("name", ""))), re.I)]
    # If the renderer doesn't carry titles, use every section except Opening/Hook/Ending.
    if not number_parts:
        number_parts = [p for p in parts if not re.search(
            r"opening|ending|hook", str(p.get("title", p.get("name", ""))), re.I)]
    if not number_parts:
        raise RuntimeError("Khong tim thay Number de chen Interview.")

    def unique_candidates():
        result = []
        for src, length in sources:
            intervals = reserved.get(str(Path(src).resolve()), [])
            # Grid sampling with 0.5 second padding to avoid near-duplicate shots.
            t = 0.0
            while t + 2.0 <= length + 0.0001:
                if not any(t < end + .5 and t + 2 > start - .5 for start, end in intervals):
                    result.append((src, round(t, 3)))
                t += 2.5
        return result

    def splice(clips, t, src, src_t, number):
        """Replace exactly two seconds of consecutive still images, keeping timing."""
        end = t + 2.0
        result = []
        inserted_here = False
        for old in clips:
            a = float(old["start"])
            b = a + float(old["frames"]) / fps
            if b <= t + 1e-5 or a >= end - 1e-5:
                result.append(old)
                continue
            if old["type"] != "image":
                return None
            if a < t - 1e-5:
                before = copy.deepcopy(old)
                before["frames"] = int(round((t - a) * fps))
                before["duration"] = before["frames"] / fps
                if before["frames"]:
                    result.append(before)
            if not inserted_here:
                result.append(dict(part=number, type="video", source=src,
                                   source_start=src_t, start=t, frames=frames2,
                                   duration=2.0, effect="Tĩnh", interview_cutaway=True))
                inserted_here = True
            if b > end + 1e-5:
                after = copy.deepcopy(old)
                after["start"] = end
                after["frames"] = int(round((b - end) * fps))
                after["duration"] = after["frames"] / fps
                if after["frames"]:
                    result.append(after)
        return result if inserted_here else None

    inserted = 0
    for p in number_parts:
        number = int(p.get("number", 0))
        clips = p.get("clips", [])
        if not clips or float(p.get("duration", 0)) < 2:
            raise RuntimeError(f"Number {number}: khong du 2 giay de chen Interview.")
        # Place the interview INSIDE a still image, not at the Number boundary
        # or directly next to another video. Keep at least one second of the
        # original image on both sides whenever the clip allows it.
        start = min(float(cl["start"]) for cl in clips)
        finish = start + float(p.get("duration", 0))
        positions = []
        min_gap = 3.0
        video_ranges = [(float(x["start"]), float(x["start"]) + float(x.get("duration", 0)))
                        for x in clips if x.get("type") == "video"]
        # Search frame-aligned two-second windows across consecutive images.
        # Three seconds of still imagery must separate any two video scenes.
        image_ranges = sorted((float(x["start"]), float(x["start"]) + float(x["frames"]) / fps)
                              for x in clips if x.get("type") == "image")
        runs = []
        for a, b in image_ranges:
            if runs and a <= runs[-1][1] + 1.0 / fps:
                runs[-1][1] = max(runs[-1][1], b)
            else:
                runs.append([a, b])
        for a, b in runs:
            low = max(a, start + min_gap)
            high = min(b - 2.0, finish - min_gap - 2.0)
            for vs, ve in video_ranges:
                if ve <= a and ve + min_gap > low:
                    low = max(low, ve + min_gap)
                if vs >= b and vs - min_gap - 2.0 < high:
                    high = min(high, vs - min_gap - 2.0)
            if high < low - 1.0 / fps:
                continue
            # A video inside a candidate run is always forbidden.
            t = round(((low + high) / 2.0) * fps) / fps
            if any(t < ve + min_gap and t + 2.0 > vs - min_gap
                   for vs, ve in video_ranges):
                continue
            positions.append(t)
        # Prefer a location around the middle of the Number to avoid
        # repeated back-to-back interview shots at section boundaries.
        midpoint = (start + finish) / 2.0
        positions.sort(key=lambda t: abs((t + 1.0) - midpoint))
        if not positions:
            raise RuntimeError(
                f"Number {number}: khong co khoang anh lien tuc du 2 giay va cach video khac it nhat 3 giay. "
                "Hay them anh hoac dieu chinh thoi luong canh.")
        choices = unique_candidates()
        if not choices:
            raise RuntimeError(f"Number {number}: da het canh Interview khong trung lap. Hay bo sung video vao thu muc Interview.")
        updated = None
        chosen = None
        for src, src_t in choices:
            for t in positions:
                updated = splice(clips, t, src, src_t, number)
                if updated is not None:
                    chosen = (src, src_t)
                    break
            if updated is not None:
                break
        if updated is None:
            raise RuntimeError(f"Number {number}: khong the chen cutaway 2 giay vao timeline.")
        p["clips"] = updated
        src, src_t = chosen
        reserved.setdefault(str(Path(src).resolve()), []).append((src_t, src_t + 2))
        inserted += 1
        log(f"INTERVIEW Number {number}: 1 canh rieng 2 giay tu {Path(src).name} tai {src_t:.1f}s.")
    log(f"INTERVIEW: Da chen {inserted} canh rieng, khong lap nguon thoi gian va khong thay doi voice.")
    return parts
