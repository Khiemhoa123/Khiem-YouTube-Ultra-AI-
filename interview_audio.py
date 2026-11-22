"""Interview Audio: diarize speakers and export per-speaker speech MP3s.

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
    """Export 30-45s of chronological, non-overlapping speech per speaker.

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
    # V5: bounded incremental scans. Keep the earliest reliable speaker
    # labels within each chunk; speaker labels across chunks are NOT stable.
    # Therefore chunks are kept separate unless verified by an embedding model.
    import time
    from collections import defaultdict
    import wave
    import numpy as np

    def voice_embedding(wav_path, a, b):
        """Optional verification using the diarization pipeline embedding model.
        Return None when the installed pyannote version lacks this interface."""
        try:
            import soundfile as sf
            from pyannote.audio import Inference
            model = getattr(pipeline, "embedding", None)
            if model is None:
                return None
            audio, rate = sf.read(str(wav_path), dtype="float32")
            piece = audio[int(a * rate):int(b * rate)]
            if len(piece) < rate * 1.5:
                return None
            import torch
            with torch.inference_mode():
                emb = model(torch.tensor(piece, dtype=torch.float32).unsqueeze(0).unsqueeze(0))
            vec = np.asarray(emb).reshape(-1)
            norm = np.linalg.norm(vec)
            return vec / norm if norm > 0 else None
        except Exception:
            return None

    def clean_turns(rows, length):
        groups = defaultdict(list)
        for a, b, speaker in rows:
            a, b = max(0.0, a), min(length, b)
            if b - a < 2.2:
                continue
            spans = [(a, b)]
            for x, y, other in rows:
                if other == speaker or x >= b or y <= a:
                    continue
                next_spans = []
                for left, right in spans:
                    if y <= left or x >= right:
                        next_spans.append((left, right))
                    else:
                        if x > left:
                            next_spans.append((left, x))
                        if y < right:
                            next_spans.append((y, right))
                spans = next_spans
            for left, right in spans:
                left += .22
                right -= .22
                if right - left >= 2.0:
                    groups[speaker].append((left, right))
        return groups

    # Scan up to six 90-second windows, never decode the entire long video.
    # Keep chunks independent to avoid merging different voices assigned the
    # same local label in different diarization passes.
    results = {}
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        scan_start = 0.0
        window = 90.0
        max_windows = 6
        exported = 0
        for part in range(max_windows):
            length = min(window, duration - scan_start)
            if length < 30:
                break
            wav = temp / f"scan_{part:02}.wav"
            log(f"V5: quét đoạn {part+1}/{max_windows}, "
                f"video {scan_start:.0f}s đến {scan_start+length:.0f}s.")
            _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{scan_start:.3f}",
                  "-i", str(video), "-t", f"{length:.3f}", "-vn",
                  "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])
            t0 = time.monotonic()
            with _PIPELINE_LOCK:
                diarization = pipeline(str(wav))
            rows = _segments(diarization)
            log(f"AI xong đoạn {part+1} sau {time.monotonic()-t0:.0f}s: "
                f"{len(set(sp for _, _, sp in rows))} Speaker, {len(rows)} lượt nói.")
            groups = clean_turns(rows, length)
            # Speaker identity is only valid within this scan window.
            for speaker in sorted(groups, key=lambda sp: groups[sp][0][0]):
                spans = sorted(groups[speaker])
                # Build a reference from longest turns. Check each candidate
                # against the reference if embeddings are available.
                reference = None
                for a, b in sorted(spans, key=lambda z: z[1]-z[0], reverse=True)[:3]:
                    reference = voice_embedding(wav, a, b)
                    if reference is not None:
                        break
                selected = []
                for a, b in spans:
                    if reference is not None:
                        embedding = voice_embedding(wav, a, b)
                        if embedding is None or embedding.shape != reference.shape:
                            continue
                        if float(np.dot(reference, embedding)) < .72:
                            continue
                    selected.append((a, b))
                # Favor long speech but allow natural shorter sentences.
                selected = [(a, b) for a, b in selected if b-a >= 2.0]
                available = sum(b-a for a, b in selected)
                if available < 30:
                    log(f"Đoạn {part+1}, {speaker}: chỉ {available:.1f}s sạch, chưa đủ 30s.")
                    continue
                cuts = []
                remain = float(target_seconds)
                for a, b in selected:
                    take = min(b-a, remain)
                    if take < 1.9:
                        continue
                    cuts.append((a, take))
                    remain -= take
                    if remain <= .05:
                        break
                total = sum(t for _, t in cuts)
                if total < 29.95:
                    continue
                filters = []
                for j, (a, take) in enumerate(cuts):
                    filters.append(
                        f"[0:a]atrim=start={a:.5f}:duration={take:.5f},"
                        f"asetpts=PTS-STARTPTS,aresample=44100,"
                        f"aformat=sample_fmts=fltp:channel_layouts=mono[a{j}]")
                concat = "".join(f"[a{j}]" for j in range(len(cuts)))
                filters.append(
                    f"{concat}concat=n={len(cuts)}:v=0:a=1,"
                    "highpass=f=90,lowpass=f=7200,afftdn=nr=12:nf=-48,"
                    "acompressor=threshold=0.12:ratio=2:attack=15:release=180,"
                    "loudnorm=I=-18:TP=-2:LRA=9[out]")
                output.mkdir(parents=True, exist_ok=True)
                exported += 1
                dest = output / f"Speaker_{exported:02}.mp3"
                _run(["ffmpeg", "-v", "error", "-y", "-i", str(wav),
                      "-filter_complex", ";".join(filters), "-map", "[out]",
                      "-c:a", "libmp3lame", "-b:a", "192k", str(dest)])
                results[f"window_{part+1}_{speaker}"] = str(dest)
                log(f"Đã xuất {dest.name}: {total:.1f}s, {len(cuts)} đoạn "
                    f"trong cửa sổ {part+1}.")
            if results:
                # Fast mode stops at first window producing usable speech.
                log("V5 dừng quét sau khi tìm được MP3 hợp lệ. "
                    "Các Speaker ở phần sau video có thể chưa được phát hiện.")
                break
            scan_start += window
    if not results:
        raise ValueError("Không tìm được 30 giây giọng nói đủ sạch trong phạm vi quét.")
    log("V5: nhãn Speaker chỉ có giá trị trong từng đoạn quét; "
        "giảm nhiễu không đảm bảo loại bỏ giọng chồng nhau.")
    return results
