"""Interview Audio: diarize 2-3 speakers and export per-speaker speech MP3s.

Requires ffmpeg, torch and pyannote.audio with access to the chosen
Hugging Face diarization model. Diarization labels speakers; it does not
separate voices that overlap in the original recording.
"""
from pathlib import Path
import json
import os
import subprocess
import tempfile

MODEL_ID = "pyannote/speaker-diarization-3.1"


def _run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _duration(path):
    data = json.loads(_run(["ffprobe", "-v", "error", "-show_format",
                            "-of", "json", str(path)]).stdout)
    return float(data["format"]["duration"])


def _segments(diarization):
    annotation = getattr(diarization, "speaker_diarization", diarization)
    return sorted((float(segment.start), float(segment.end), str(speaker))
                  for segment, _, speaker in annotation.itertracks(yield_label=True))


def export_speakers(video, output, token, target_seconds=35, speakers=None, log=print):
    """Export 30-40s of chronological, non-overlapping speech per speaker.

    Returns a mapping of speaker label to output path. Speakers with less than
    30s of usable speech are skipped, not padded with another person's voice.
    """
    video = Path(video).expanduser().resolve()
    output = Path(output).expanduser().resolve()
    if not video.is_file():
        raise FileNotFoundError(video)
    if not token or not token.strip():
        raise ValueError("Cần Hugging Face token có quyền truy cập model pyannote.")
    target_seconds = max(30, min(40, int(target_seconds)))
    # Automatically infer the number of speakers from the recording.
    from pyannote.audio import Pipeline
    log("Đang tải mô hình phân biệt người nói (lần đầu có thể mất thời gian).")
    pipeline = Pipeline.from_pretrained(MODEL_ID, use_auth_token=token.strip())
    if pipeline is None:
        raise RuntimeError("Không tải được model. Kiểm tra token và quyền truy cập.")
    duration = _duration(video)
    log(f"Video dài {duration:.1f} giây.")
    with tempfile.TemporaryDirectory() as temp:
        wav = Path(temp) / "source.wav"
        log("Đang chuẩn bị audio 16 kHz từ video.")
        _run(["ffmpeg", "-v", "error", "-y", "-i", str(video),
              "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])
        log("AI đang xác định thời gian nói của từng người.")
        try:
            diarization = pipeline(str(wav))
        except TypeError:
            diarization = pipeline({"audio": str(wav)})
        rows = _segments(diarization)
        log(f"Đã nhận diện {len(set(sp for _, _, sp in rows))} người nói, {len(rows)} lượt nói.")
        if not rows:
            raise ValueError("Không phát hiện được người nói.")
        # Exclude overlap: diarization alone cannot isolate simultaneous voices.
        clean = []
        for i, (a, b, speaker) in enumerate(rows):
            if b <= a or a >= duration:
                continue
            a, b = max(0, a), min(duration, b)
            conflicts = [(max(a, x), min(b, y)) for j, (x, y, other) in enumerate(rows)
                         if i != j and other != speaker and x < b and y > a]
            spans = [(a, b)]
            for x, y in sorted(conflicts):
                spans = [(u, v) for l, r in spans
                         for u, v in ((l, min(r, x)), (max(l, y), r)) if v-u >= .45]
            clean.extend((u, v, speaker) for u, v in spans if v-u >= .45)
        groups = {}
        for a, b, speaker in sorted(clean):
            groups.setdefault(speaker, []).append((a, b))
        # Stable speaker numbering based on first appearance.
        ordered = sorted(groups, key=lambda sp: groups[sp][0][0])
        output.mkdir(parents=True, exist_ok=True)
        log(f"Đang xuất MP3 cho {len(ordered)} người nói được nhận diện.")
        results = {}
        for index, speaker in enumerate(ordered, 1):
            available = sum(b-a for a, b in groups[speaker])
            if available < 30:
                log(f"Speaker {index:02}: chỉ có {available:.1f}s, bỏ qua (cần 30s).")
                continue
            remaining = min(target_seconds, available)
            cuts = []
            for a, b in groups[speaker]:
                if remaining <= .01:
                    break
                length = min(b-a, remaining)
                if length < .1:
                    continue
                cuts.append((a, length))
                remaining -= length
            if sum(t for _, t in cuts) < 29.95:
                log(f"Speaker {index:02}: không đủ thời lượng hợp lệ.")
                continue
            # One filtergraph, continuous MP3, no generated/fake speech.
            filters = []
            for j, (start, length) in enumerate(cuts):
                filters.append(f"[0:a]atrim=start={start:.5f}:duration={length:.5f},"
                               f"asetpts=PTS-STARTPTS,aresample=44100,"
                               f"aformat=sample_fmts=fltp:channel_layouts=mono[a{j}]")
            concat = "".join(f"[a{j}]" for j in range(len(cuts)))
            filters.append(f"{concat}concat=n={len(cuts)}:v=0:a=1[out]")
            dest = output / f"Speaker_{index:02}.mp3"
            _run(["ffmpeg", "-v", "error", "-y", "-i", str(video),
                  "-filter_complex", ";".join(filters), "-map", "[out]",
                  "-c:a", "libmp3lame", "-b:a", "192k", str(dest)])
            results[speaker] = str(dest)
            log(f"Speaker {index:02}: {sum(t for _, t in cuts):.1f}s -> {dest.name}")
        if not results:
            raise ValueError("Không speaker nào đủ 30 giây lời nói riêng biệt.")
        return results
