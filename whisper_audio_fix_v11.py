"""Decode media with FFmpeg to NumPy so faster-whisper never calls PyAV.open.

This avoids incompatible PyAV versions raising:
open() got an unexpected keyword argument 'metadata_errors'.
Requires ffmpeg on PATH, numpy and faster-whisper.
"""
import subprocess
import numpy as np

_MODEL = None

def get_model():
    global _MODEL
    if _MODEL is None:
        from faster_whisper import WhisperModel
        _MODEL = WhisperModel("base", device="cpu", compute_type="int8")
    return _MODEL

def transcribe_media(path, model=None, **kwargs):
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error",
               "-i", str(path), "-vn", "-ac", "1", "-ar", "16000",
               "-f", "f32le", "-acodec", "pcm_f32le", "pipe:1"]
    process = subprocess.run(command, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if process.returncode != 0:
        raise RuntimeError("FFmpeg không giải mã được âm thanh: " +
                           process.stderr.decode("utf-8", errors="replace")[-1200:])
    audio = np.frombuffer(process.stdout, dtype=np.float32).copy()
    if len(audio) < 1600:
        raise ValueError("Không tìm thấy âm thanh hợp lệ trong: " + str(path))
    # Passing ndarray bypasses faster-whisper's PyAV decode_audio entirely.
    return (model or get_model()).transcribe(audio, **kwargs)
