"""Store Hugging Face token encrypted for the current Windows user.

Uses Windows DPAPI (CryptProtectData), not plaintext JSON or GitHub.
Never logs or prints the token. Non-Windows platforms do not persist it.
"""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data):
    buf = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))), buf


def _crypt(data, decrypt=False):
    if os.name != "nt":
        raise OSError("Windows DPAPI is required for local token storage")
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    source, buffer = _blob(data)
    result = DATA_BLOB()
    flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN
    if decrypt:
        ok = crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None,
                                         None, flags, ctypes.byref(result))
    else:
        ok = crypt32.CryptProtectData(ctypes.byref(source), None, None, None,
                                       None, flags, ctypes.byref(result))
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(result.pbData, ctypes.c_void_p))


def _path():
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "KhiemYoutube" / "hf_token.dpapi"


def load_token():
    try:
        return _crypt(_path().read_bytes(), decrypt=True).decode("utf-8")
    except (OSError, ValueError, UnicodeError):
        return ""


def save_token(token):
    """Save encrypted token, or delete it if the input is empty."""
    if os.name != "nt":
        return
    path = _path()
    try:
        if not token:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        encrypted = _crypt(token.encode("utf-8"))
        temp = path.with_suffix(".tmp")
        temp.write_bytes(encrypted)
        temp.replace(path)
    except OSError:
        # A failed save never exposes the token in logs or plaintext.
        pass
