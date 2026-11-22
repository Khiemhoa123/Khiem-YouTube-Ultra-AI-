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
    # V8: fail-closed speaker verification. Unlike V5, do not silently
    # skip embedding checks, reuse local labels across windows, or export
    # multiple files containing the same speaker.
    import time
    import numpy as np
    import torch
    from collections import defaultdict
    from pyannote.audio import Model, Inference
    from pyannote.core import Segment

    # V8.2: use the published WeSpeaker LM model instead of the inaccessible
    # pyannote/embedding repository. Support both pyannote v3/v4 APIs.
    import inspect
    log("V8.2: kiểm tra mô hình xác minh giọng WeSpeaker-LM.")
    embedding_id = "pyannote/wespeaker-voxceleb-resnet34-LM"
    try:
        load_args = {}
        signature = inspect.signature(Model.from_pretrained)
        if "token" in signature.parameters:
            load_args["token"] = token.strip()
        elif "use_auth_token" in signature.parameters:
            load_args["use_auth_token"] = token.strip()
        try:
            embedding_model = Model.from_pretrained(embedding_id, **load_args)
        except TypeError as exc:
            if "token" not in str(exc) and "use_auth_token" not in str(exc):
                raise
            # A few older installations accept only positional model ID.
            embedding_model = Model.from_pretrained(embedding_id)
        if embedding_model is None:
            raise RuntimeError("Hugging Face không trả về mô hình.")
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        embedding_model.to(device)
        embedding_infer = Inference(embedding_model, window="whole")
        log(f"V8.2: mô hình xác minh giọng sẵn sàng trên {device}.")
    except Exception as exc:
        detail = str(exc)
        if token.strip():
            detail = detail.replace(token.strip(), "[TOKEN]")
        raise RuntimeError(
            "Không khởi tạo được WeSpeaker. Kiểm tra Internet, phiên bản "
            "pyannote.audio và quyền tải mô hình "
            + embedding_id + ". V8.1 sẽ KHÔNG xuất MP3 nếu thiếu "
            "xác minh giọng. Lỗi: " + detail) from exc

    def embedding(wav, left, right):
        """Compute verified speaker embedding for a clean turn."""
        if right - left < 2.3:
            return None
        try:
            with _PIPELINE_LOCK, torch.inference_mode():
                vector = np.asarray(embedding_infer.crop(
                    str(wav), Segment(float(left), float(right)))).reshape(-1)
            if not np.all(np.isfinite(vector)):
                return None
            norm = np.linalg.norm(vector)
            return vector / norm if norm > 1e-8 else None
        except Exception as exc:
            raise RuntimeError("Lỗi xác minh embedding, dừng để tránh xuất sai giọng: "
                               + str(exc)) from exc

    def clean_turns(rows, length):
        """Remove ALL diarized overlap and a margin at each speaker change."""
        grouped = defaultdict(list)
        for a, b, who in rows:
            a, b = max(0.0, a), min(length, b)
            if b - a < 2.8:
                continue
            pieces = [(a, b)]
            for x, y, other in rows:
                if other == who or y <= a or x >= b:
                    continue
                next_pieces = []
                for left, right in pieces:
                    if y <= left or x >= right:
                        next_pieces.append((left, right))
                    else:
                        if x > left:
                            next_pieces.append((left, min(x, right)))
                        if y < right:
                            next_pieces.append((max(y, left), right))
                pieces = next_pieces
            for left, right in pieces:
                left += 0.35
                right -= 0.35
                if right - left >= 2.3:
                    grouped[who].append((left, right))
        return grouped

    def stable_turn(wav, left, right, reference):
        """Reject turns containing a second voice or an abrupt speaker change.

        Whole-turn embeddings can average two voices into one plausible vector.
        Verify overlapping short windows independently, including the edges.
        This is conservative and may reject legitimate speech.
        """
        length = right - left
        if length < 2.3:
            return False
        if length <= 4.2:
            return True
        check_length = min(3.2, length * 0.55)
        checks = [(left, left + check_length),
                  (right - check_length, right)]
        if length > 8.0:
            mid = (left + right - check_length) / 2
            checks.append((mid, mid + check_length))
        for a, b in checks:
            vector = embedding(wav, a, b)
            if vector is None or float(np.dot(vector, reference)) < SAME:
                return False
        return True

    # Similarity is a conservative gate, not a guarantee of identity.
    # Ambiguous turns are rejected. Labels from different windows are
    # never assumed to represent the same person.
    SAME = 0.80
    MARGIN = 0.09
    # Scan up to 24 short windows, sampling across the entire video.
    # Long interviews must not be limited to their first few minutes.
    MAX_WINDOWS = 24
    WINDOW = 75.0
    results = {}
    with tempfile.TemporaryDirectory(prefix="khiem_voice_v8_") as temp_dir:
        temp = Path(temp_dir)
        clusters = []
        window_files = []
        # Avoid the opening sting and audience applause on long interviews.
        start_at = 60.0 if duration > 240.0 else (25.0 if duration > 85.0 else 0.0)
        available = max(0.0, duration - start_at)
        # Cover the whole recording without diarizing all of it.
        import math
        scan_count = min(MAX_WINDOWS, max(1, math.ceil(available / WINDOW)))
        last_start = max(start_at, duration - WINDOW)
        starts = ([start_at] if scan_count == 1 else
                  [start_at + (last_start - start_at) * i / (scan_count - 1)
                   for i in range(scan_count)])
        for part, start_at in enumerate(starts):
            length = min(WINDOW, duration - start_at)
            if length < 30:
                break
            wav = temp / f"window_{part:02}.wav"
            log(f"V9.1: quét đoạn {part+1}/{len(starts)}, "
                f"video {start_at:.0f}s đến {start_at+length:.0f}s.")
            _run(["ffmpeg", "-v", "error", "-y", "-ss", f"{start_at:.3f}",
                  "-i", str(video), "-t", f"{length:.3f}", "-vn",
                  "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])
            window_files.append(wav)
            t0 = time.monotonic()
            with _PIPELINE_LOCK:
                diarization = pipeline(str(wav))
            rows = _segments(diarization)
            groups = clean_turns(rows, length)
            log(f"AI xong đoạn {part+1} sau {time.monotonic()-t0:.0f}s: "
                f"{len(groups)} Speaker, {len(rows)} lượt nói.")
            # Verify local speaker reference using multiple independent turns.
            for local, spans in sorted(groups.items(),
                                       key=lambda item: item[1][0][0]):
                candidates = []
                for a, b in spans:
                    emb = embedding(wav, a, b)
                    if emb is not None:
                        candidates.append((a, b, emb))
                if not candidates:
                    continue
                # Reference is weighted by longest stable turn, not a random
                # 2-second greeting. Filter turns inconsistent with it.
                reference = max(candidates, key=lambda t: t[1]-t[0])[2]
                verified = [(a, b, emb) for a, b, emb in candidates
                            if float(np.dot(reference, emb)) >= SAME
                            and stable_turn(wav, a, b, reference)]
                if not verified:
                    continue
                center = np.mean([e for _, _, e in verified], axis=0)
                center /= max(np.linalg.norm(center), 1e-8)
                # Identify speaker across windows using verified centroids.
                scores = [float(np.dot(center, c["center"])) for c in clusters]
                best = int(np.argmax(scores)) if scores else None
                runner_up = sorted(scores, reverse=True)[1] if len(scores) > 1 else -1.0
                if best is not None and scores[best] >= SAME:
                    if scores[best] - runner_up < MARGIN:
                        log(f"Bỏ qua giọng mơ hồ ở đoạn {part+1}: "
                            "không phân biệt được hai Speaker.")
                        continue
                    idx = best
                else:
                    # New speaker must differ sufficiently from all existing ones.
                    if scores and max(scores) > SAME - MARGIN:
                        log(f"Bỏ qua giọng chưa chắc chắn ở đoạn {part+1}.")
                        continue
                    idx = len(clusters)
                    clusters.append({"center": center.copy(), "cuts": [],
                                     "weight": 0.0})
                c = clusters[idx]
                for a, b, emb in verified:
                    # Recheck against global identity to prevent local label
                    # leakage. Never assign one interval to two speakers.
                    all_scores = [float(np.dot(emb, other["center"]))
                                  for other in clusters]
                    if all_scores[idx] < SAME or not stable_turn(wav, a, b, c["center"]):
                        continue
                    competitors = [v for k, v in enumerate(all_scores) if k != idx]
                    if competitors and all_scores[idx] - max(competitors) < MARGIN:
                        continue
                    if any(w == part and not (b <= x or a >= y)
                           for other in clusters for w, x, y in other["cuts"]):
                        continue
                    c["cuts"].append((part, a, b))
                    c["weight"] += b - a
                # Update centroid cautiously, after validated additions.
                if c["weight"] > 0:
                    blended = c["center"] * 0.8 + center * 0.2
                    c["center"] = blended / max(np.linalg.norm(blended), 1e-8)
            log("V8: " + ", ".join(
                f"Speaker {i+1:02}: {sum(b-a for _,a,b in c['cuts']):.1f}s"
                for i, c in enumerate(clusters)))
            ready = [c for c in clusters if sum(b-a for _,a,b in c["cuts"]) >= target_seconds]
            # Do not assume two speakers. Count is determined by the clip.
            # Scan further when a speaker is still short of the target.
            if len(ready) >= 2 and part >= 3:
                log("Đã có ít nhất hai Speaker đủ thời lượng, kết thúc quét sớm.")
                break

        exported = 0
        for c in clusters:
            ordered = sorted(c["cuts"], key=lambda z: (z[0], z[1]))
            if sum(b-a for _, a, b in ordered) < target_seconds:
                log("BỎ QUA Speaker: dưới 30 giây đã xác minh.")
                continue
            selected = []
            remaining = float(target_seconds)
            for w, a, b in ordered:
                take = min(b-a, remaining)
                if take < 2.0:
                    continue
                selected.append((w, a, take))
                remaining -= take
                if remaining < 0.05:
                    break
            total = sum(take for _, _, take in selected)
            if total < target_seconds - 0.05:
                log(f"BỎ QUA Speaker: chỉ {total:.1f}s hợp lệ.")
                continue
            # Use individual input files for scanned windows, and trim at
            # exact local timestamps. No repeated audio from other speakers.
            used_windows = sorted({w for w, _, _ in selected})
            input_index = {w: i for i, w in enumerate(used_windows)}
            command = ["ffmpeg", "-v", "error", "-y"]
            for w in used_windows:
                command.extend(["-i", str(window_files[w])])
            filters = []
            for j, (w, a, take) in enumerate(selected):
                filters.append(
                    f"[{input_index[w]}:a]atrim=start={a:.5f}:duration={take:.5f},"
                    f"asetpts=PTS-STARTPTS,aresample=44100,"
                    f"aformat=sample_fmts=fltp:channel_layouts=mono[a{j}]")
            inputs = "".join(f"[a{j}]" for j in range(len(selected)))
            filters.append(
                f"{inputs}concat=n={len(selected)}:v=0:a=1,"
                "highpass=f=85,lowpass=f=7600,afftdn=nr=8:nf=-50,"
                "loudnorm=I=-18:TP=-2:LRA=10[out]")
            dest = temp / f"Speaker_{exported+1:02}.mp3"
            command.extend(["-filter_complex", ";".join(filters),
                            "-map", "[out]", "-c:a", "libmp3lame",
                            "-b:a", "192k", str(dest)])
            _run(command)
            if _duration(dest) < 29.8:
                log("BỎ QUA: MP3 thực tế dưới 30 giây.")
                dest.unlink(missing_ok=True)
                continue
            output.mkdir(parents=True, exist_ok=True)
            import shutil
            final = output / f"Speaker_{exported+1:02}.mp3"
            shutil.move(str(dest), str(final))
            exported += 1
            results[f"verified_speaker_{exported:02}"] = str(final)
            log(f"Đã xuất {dest.name}: {total:.1f}s, "
                f"{len(selected)} lượt nói đã xác minh.")
    if not results:
        raise ValueError(
            "Đã quét nhiều vị trí trong video nhưng không thu đủ "
            f"{target_seconds} giây giọng được xác minh cho một Speaker. "
            "Đây là thiếu dữ liệu ĐẠT NGƯỠNG AI, không khẳng định video "
            "thiếu lời nói. Hãy xem nhật ký số giây của từng Speaker.")
    log("V9.1 Stability hoàn tất. Phát hiện chồng giọng chỉ dựa trên diarization; "
        "không bảo đảm loại bỏ mọi tiếng cười hoặc giọng chen ngang.")
    return results
