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
    root = Path(folder)
    files = sorted(root.glob("*.txt")) if root.is_dir() else ([root] if root.is_file() else [])
    pieces = []
    for p in files:
        try:
            pieces.append(p.read_text(encoding="utf-8-sig", errors="replace"))
        except OSError:
            continue
    return "\n".join(pieces)

def _transcribe_full(path, duration, model, log):
    """Transcribe the complete interview in short, nonoverlapping windows."""
    from whisper_audio_fix_v11 import transcribe_media
    from types import SimpleNamespace
    rows = []
    window = 28.0
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "speech.wav"
        for index in range(int((duration + window - 0.001) // window)):
            offset = index * window
            remaining = min(window, duration - offset)
            if remaining < 0.5:
                continue
            try:
                _run(["ffmpeg", "-v", "error", "-y", "-ss", str(offset),
                      "-i", str(path), "-t", str(remaining), "-vn",
                      "-ac", "1", "-ar", "16000", str(wav)])
                segments, _ = transcribe_media(
                    wav, model=model, vad_filter=False, beam_size=3,
                    word_timestamps=True, condition_on_previous_text=False)
                count = 0
                for seg in segments:
                    words = getattr(seg, "words", None) or []
                    if words:
                        for w in words:
                            if w.start is None or w.end is None:
                                continue
                            text = str(w.word or "").strip()
                            if text:
                                rows.append(SimpleNamespace(
                                    start=max(0.0, offset + float(w.start)),
                                    end=min(duration, offset + float(w.end)), text=text))
                                count += 1
                    elif str(seg.text).strip():
                        rows.append(SimpleNamespace(
                            start=offset + float(seg.start),
                            end=min(duration, offset + float(seg.end)),
                            text=str(seg.text).strip()))
                        count += 1
                log(f"WHISPER: {Path(path).name} {offset:.0f}-{offset+remaining:.0f}s: {count} tu/doan")
            except Exception as exc:
                log(f"WHISPER: Loi {Path(path).name} tai {offset:.0f}s: {exc}")
    return sorted(rows, key=lambda r: (r.start, r.end))

def _cached_rows(path, duration, model, cache_dir, log):
    from types import SimpleNamespace
    import hashlib
    stat = Path(path).stat()
    key = hashlib.sha256((str(Path(path).resolve()) + "|" + str(stat.st_size) +
                          "|" + str(stat.st_mtime_ns) + "|full-v2").encode("utf-8")).hexdigest()
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / (key + ".json")
    if dest.exists():
        try:
            raw = json.loads(dest.read_text(encoding="utf-8"))
            rows = [SimpleNamespace(start=float(x[0]), end=float(x[1]), text=str(x[2]))
                    for x in raw]
            log(f"WHISPER CACHE: {Path(path).name}: {len(rows)} tu/doan")
            return rows
        except (OSError, ValueError, TypeError, IndexError):
            pass
    rows = _transcribe_full(path, duration, model, log)
    if rows:
        tmp = dest.with_suffix(".tmp")
        tmp.write_text(json.dumps([[r.start, r.end, r.text] for r in rows],
                                  ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, dest)
    return rows

def _speech_candidates(rows, script, max_seconds):
    """Score natural sentence or pause boundaries; never stitch separated windows."""
    if not rows:
        return []
    minimum = min(6.0, max_seconds)
    candidates = []
    for i, first in enumerate(rows):
        if i:
            prev = rows[i - 1]
            gap = first.start - prev.end
            if gap < 0.28 and not prev.text.rstrip().endswith((".", "?", "!")):
                continue
        words = []
        for j in range(i, min(len(rows), i + 165)):
            cur = rows[j]
            if j > i and cur.start - rows[j - 1].end > 1.5:
                break
            dur = cur.end - first.start
            if dur > max_seconds:
                break
            words.append(cur.text.strip())
            if dur < minimum or len(words) < 9:
                continue
            punctuation = cur.text.rstrip().endswith((".", "?", "!"))
            pause = (rows[j + 1].start - cur.end) if j + 1 < len(rows) else 0.0
            if not punctuation and pause < 0.45:
                continue
            phrase = " ".join(words)
            similarity = _similarity(script, phrase)
            score = similarity * 3 + min(dur, 24) / 100 + (0.15 if punctuation else 0.10)
            candidates.append((score, float(first.start), float(dur), phrase))
    return candidates

def choose_intro(c, log):
    """Scan all interviews, compare against all script TXT, select complete speech."""
    folder = str(c.get("interview_folder", "")).strip()
    if not c.get("interview_enabled") or not folder:
        return None
    root = Path(folder)
    if not root.is_dir():
        raise RuntimeError("Thu muc Interview khong ton tai: " + folder)
    videos = sorted(p for p in root.rglob("*")
                    if p.is_file() and p.suffix.lower() in VIDEO_EXT)
    if not videos:
        raise RuntimeError("Thu muc Interview khong co video.")
    script = _script_text(c.get("txt", ""))
    log(f"INTERVIEW: Da doc {len(script.split())} tu tu toan bo TXT kich ban.")
    # Voice files are used to validate the project's audio structure.
    voice_root = Path(str(c.get("voice", "")))
    if voice_root.is_dir():
        voice_files = [p for p in voice_root.rglob("*")
                       if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".flac")]
        log(f"INTERVIEW: Phat hien {len(voice_files)} file voice kich ban.")
    try:
        from whisper_audio_fix_v11 import get_model
        log("WHISPER: Dang nap mo hinh nhan dien tieng noi.")
        model = get_model()
        log("WHISPER: Mo hinh san sang.")
    except Exception as exc:
        raise RuntimeError("Khong the nap Whisper: " + str(exc)) from exc
    max_seconds = min(30.0, max(1.0, float(c.get("interview_max_seconds", 30))))
    # Store cache outside the export directory so repeated exports can reuse it.
    cache_dir = Path.home() / ".khiem_youtube" / "interview_transcripts"
    all_candidates = []
    sampled = {}
    log(f"INTERVIEW: Quet TOAN BO {len(videos)} video; lan dau co the mat nhieu thoi gian.")
    for index, path in enumerate(videos, 1):
        try:
            info = _probe(path)
            if not any(st.get("codec_type") == "audio" for st in info.get("streams", [])):
                log(f"INTERVIEW {index}: Bo qua video khong co audio: {path.name}")
                continue
            if not any(st.get("codec_type") == "video" for st in info.get("streams", [])):
                log(f"INTERVIEW {index}: Bo qua video khong co hinh: {path.name}")
                continue
            duration = float(info.get("format", {}).get("duration", 0) or 0)
            if duration < 6:
                log(f"INTERVIEW {index}: Bo qua video ngan hon 6s: {path.name}")
                continue
            log(f"INTERVIEW {index}/{len(videos)}: {path.name} ({duration:.1f}s)")
            rows = _cached_rows(path, duration, model, cache_dir, log)
            sampled[str(path)] = rows
            matches = _speech_candidates(rows, script, max_seconds)
            log(f"INTERVIEW: {path.name}: {len(rows)} tu/doan, {len(matches)} ung vien.")
            all_candidates.extend((score, str(path), start, length, phrase)
                                  for score, start, length, phrase in matches)
        except Exception as exc:
            log(f"INTERVIEW: Khong phan tich duoc {path.name}: {exc}")
    if not all_candidates:
        raise RuntimeError(
            "Da quet toan bo Interview nhung khong tim duoc doan loi noi co diem "
            "bat dau/ket thuc tu nhien trong 30s. Kiem tra log WHISPER.")
    all_candidates.sort(key=lambda item: item[0], reverse=True)
    score, path, start, duration, phrase = all_candidates[0]
    c["_interview_sample_rows"] = [(r.start, r.end, r.text) for r in sampled[path]]
    log(f"INTERVIEW DA CHON: {Path(path).name} | {start:.2f}s -> "
        f"{start+duration:.2f}s | {duration:.2f}s | diem {score:.3f}")
    log("INTERVIEW NOI DUNG: " + phrase[:600])
    return {"source": path, "source_start": start, "duration": duration,
            "transcript": phrase, "score": score, "selection_mode": "full_scan"}

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
    # app.py stores section IDs as numeric 'number' fields; filenames may
    # be "02 - Name.mp3" without the literal word Number.
    def section_label(part):
        return (str(part.get("title") or part.get("name") or "") + " " +
                Path(str(part.get("voice") or "")).stem).lower()
    ordered_parts = sorted(parts, key=lambda p: int(p.get("number", 0)))
    number_parts = [p for p in ordered_parts if
                    not re.search(r"opening|ending|hook|outro|intro", section_label(p), re.I)
                    and re.search(r"\\bnumber\\b", section_label(p), re.I)]
    if not number_parts:
        # The common naming convention is 01 Opening, 02... Number, last Ending.
        # When no labels are available, exclude the first and last sections
        # rather than treating all sections as Numbers.
        number_parts = [p for p in ordered_parts[1:-1]
                        if not re.search(r"opening|ending|hook|outro|intro", section_label(p), re.I)]
    if not number_parts:
        log("INTERVIEW: Khong co Number duoc xac nhan; bo qua cutaway, tiep tuc xuat.")
        return parts

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
