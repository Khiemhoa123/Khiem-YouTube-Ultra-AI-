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
import threading

_PIPELINES = {}
_PIPELINE_LOCK = threading.Lock()

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
    target_seconds = max(30, min(45, int(target_seconds)))
    # Automatically infer the number of speakers from the recording.
    from pyannote.audio import Pipeline
    log("Đang tải mô hình phân biệt người nói (lần đầu có thể mất thời gian).")
    # Reuse the loaded model across videos in the same app session.
    # Serial execution avoids racing the shared model on GPU.
    with _PIPELINE_LOCK:
        key = token.strip()
        pipeline = _PIPELINES.get(key)
        if pipeline is None:
            pipeline = Pipeline.from_pretrained(MODEL_ID, use_auth_token=key)
            if pipeline is None:
                raise RuntimeError("Không tải được model. Kiểm tra token và quyền truy cập.")
            try:
                import torch
                if torch.cuda.is_available():
                    pipeline.to(torch.device("cuda"))
                    log("AI sử dụng GPU NVIDIA CUDA.")
                else:
                    log("Không có CUDA khả dụng, AI sử dụng CPU.")
            except (ImportError, RuntimeError, AssertionError) as exc:
                log(f"Không chuyển được sang GPU, tiếp tục với CPU: {exc}")
            _PIPELINES[key] = pipeline
        else:
            log("Đã dùng lại mô hình AI trong bộ nhớ, không cần tải lại.")
    duration = _duration(video)
    log(f"Video dài {duration:.1f} giây.")
    with tempfile.TemporaryDirectory() as temp:
        wav = Path(temp) / "source.wav"
        # Incremental prefix scanning preserves speaker identities across scans:
        # diarization is rerun on the growing prefix, never concatenating labels
        # from independent windows (which would misidentify speakers).
        # Stop as soon as every speaker detected so far has enough clean speech.
        scan_end = min(duration, 90.0)
        while True:
            log(f"Đang chuẩn bị audio 16 kHz: quét 0 đến {scan_end:.0f}/{duration:.0f} giây.")
            _run(["ffmpeg", "-v", "error", "-y", "-i", str(video),
                  "-t", f"{scan_end:.3f}", "-vn", "-ac", "1", "-ar", "16000",
                  "-c:a", "pcm_s16le", str(wav)])
            log(f"AI đang xác định người nói trong {scan_end:.0f} giây đầu.")
            with _PIPELINE_LOCK:
                try:
                    diarization = pipeline(str(wav))
                except TypeError:
                    diarization = pipeline({"audio": str(wav)})
            rows = _segments(diarization)
            log(f"Đã nhận diện {len(set(sp for _, _, sp in rows))} người nói, {len(rows)} lượt nói.")
            if rows:
                # Calculate non-overlapping usable speech before deciding to stop.
                usable = {}
                for i, (a, b, speaker) in enumerate(rows):
                    if b <= a:
                        continue
                    spans = [(max(0.0, a), min(scan_end, b))]
                    conflicts = [(max(a, x), min(b, y))
                                 for j, (x, y, other) in enumerate(rows)
                                 if j != i and other != speaker and x < b and y > a]
                    for x, y in sorted(conflicts):
                        spans = [(u, v) for l, r in spans
                                 for u, v in ((l, min(r, x)), (max(l, y), r))
                                 if v-u >= .45]
                    usable[speaker] = usable.get(speaker, 0.0) + sum(
                        v-u for u, v in spans if v-u >= .45)
                if usable and all(value >= target_seconds + 0.2 for value in usable.values()):
                    log("Đủ thời lượng cho các người nói đã phát hiện, dừng quét sớm.")
                    break
            if scan_end >= duration - .01:
                log("Đã quét đến cuối video.")
                break
            # Extend progressively; each scan includes previous audio so speaker
            # labels are recalculated consistently instead of merged incorrectly.
            scan_end = min(duration, scan_end + 90.0)
            log("Chưa đủ lời nói hợp lệ, tự động quét thêm 90 giây.")
        duration = scan_end
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
        log("Bật lọc tiếng ù, giảm nhiễu và cân bằng âm lượng giọng nói.")
        results = {}
        for index, speaker in enumerate(ordered, 1):
            available = sum(b-a for a, b in groups[speaker])
            if available < 30:
                log(f"LỖI Speaker {index:02}: KHÔNG ĐỦ THỜI LƯỢNG ({available:.1f}s), bỏ qua.")
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
            filters.append(
                f"{concat}concat=n={len(cuts)}:v=0:a=1,"
                "highpass=f=85,lowpass=f=7600,"
                "afftdn=nr=10:nf=-45,"
                "acompressor=threshold=0.12:ratio=2:attack=15:release=180,"
                "loudnorm=I=-18:TP=-2:LRA=9[out]"
            )
            dest = output / f"Speaker_{index:02}.mp3"
            # Decode the prepared WAV rather than the original video for every speaker.
            _run(["ffmpeg", "-v", "error", "-y", "-i", str(wav),
                  "-filter_complex", ";".join(filters), "-map", "[out]",
                  "-c:a", "libmp3lame", "-b:a", "192k", str(dest)])
            results[speaker] = str(dest)
            log(f"Speaker {index:02}: {sum(t for _, t in cuts):.1f}s -> {dest.name}")
        if not results:
            raise ValueError("Không speaker nào đủ 30 giây lời nói riêng biệt.")
        return results
