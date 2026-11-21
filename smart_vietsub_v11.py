"""SMART VIETSUB: Vietnamese review subtitles, never burned into MP4.

Optional: pip install faster-whisper deep-translator
Translation requires internet. If translation fails, leave original text in a
separate diagnostic file, never mislabel original speech as Vietnamese.
"""
import json
import re
from pathlib import Path

def _srt_time(seconds):
    ms = max(0, int(round(float(seconds) * 1000)))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"

def _write_srt(path, cues):
    lines = []
    for n, (start, end, text) in enumerate(cues, 1):
        if end <= start or not text.strip():
            continue
        lines.extend([str(n), f"{_srt_time(start)} --> {_srt_time(end)}",
                      text.strip(), ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8-sig")

def _voice_rows(voice, log):
    from faster_whisper import WhisperModel
    # Accurate timestamps are obtained from the actual audio, not text length.
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(voice), vad_filter=True, beam_size=3)
    rows = [(float(s.start), float(s.end), s.text.strip())
            for s in segments if s.text.strip() and s.end > s.start]
    return rows, getattr(info, "language", None)

def _translate(rows, language, log):
    if language == "vi":
        return rows
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        log("VIETSUB: Thiếu deep-translator. Cài: pip install deep-translator")
        return None
    try:
        translator = GoogleTranslator(source="auto", target="vi")
        result = []
        # Translate individually to keep timing and speech alignment stable.
        for start, end, original in rows:
            translated = translator.translate(original)
            if not translated:
                raise ValueError("Bản dịch rỗng")
            result.append((start, end, translated))
        return result
    except Exception as exc:
        log("VIETSUB: Dịch thất bại, không ghi phụ đề sai ngôn ngữ: " + str(exc))
        return None

def create(c, parts, log):
    """Create a Vietnamese SRT for review and return its path or None.

    Timeline includes original-audio interview first. No subtitles are added
    to the MP4 rendering path.
    """
    root = Path(c["out"]) / "_vietsub_review"
    root.mkdir(parents=True, exist_ok=True)
    intro = c.get("_interview_intro")
    offset = float(intro["duration"]) if intro else 0.0
    all_rows = []
    original_rows = []
    if intro:
        source = intro["source"]
        source_start = float(intro.get("source_start", 0))
        source_end = source_start + offset
        try:
            rows, lang = _voice_rows(source, log)
            sliced = [(max(0.0, a-source_start), min(offset, b-source_start), text)
                      for a,b,text in rows if b > source_start and a < source_end]
            original_rows.extend(sliced)
            translated = _translate(sliced, lang, log)
            if translated:
                all_rows.extend(translated)
        except Exception as exc:
            log("VIETSUB: Không nhận diện được lời interview: " + str(exc))
    elapsed = offset
    for part in parts:
        voice = part["voice"]
        duration = float(part["duration"])
        try:
            rows, lang = _voice_rows(voice, log)
            shifted = [(elapsed+a, min(elapsed+duration, elapsed+b), text)
                       for a,b,text in rows if a < duration]
            original_rows.extend(shifted)
            translated = _translate(shifted, lang, log)
            if translated:
                all_rows.extend(translated)
        except Exception as exc:
            log("VIETSUB: Lỗi nhận diện Voice " + Path(voice).name + ": " + str(exc))
        elapsed += duration
    # Keep the originals for comparison even if translation is unavailable.
    original = root / (c["name"] + ".original.srt")
    _write_srt(original, sorted(original_rows))
    if not all_rows:
        log("VIETSUB: Chưa tạo được bản dịch tiếng Việt. Đã lưu lời gốc: " + str(original))
        return None
    output = root / (c["name"] + ".vi.srt")
    _write_srt(output, sorted(all_rows))
    log("VIETSUB: Đã tạo " + str(output) + ". MP4 không có phụ đề.")
    return output

def attach_to_capcut(draft_folder, srt_path, log):
    """Copy SRT beside the CapCut draft for safe manual import.

    Do not forge an unverified native text track in CapCut JSON. Import the
    SRT using CapCut's captions/subtitles import, then remove before export.
    """
    import shutil
    if not srt_path:
        return None
    dest = Path(draft_folder) / "VIETSUB_KIEM_TRA.srt"
    shutil.copy2(srt_path, dest)
    log("VIETSUB: Đã đặt phụ đề cạnh dự án: " + str(dest))
    log("CapCut: nhập VIETSUB_KIEM_TRA.srt vào phụ đề. Track chữ tự động chưa được xác minh tương thích.")
    return dest
