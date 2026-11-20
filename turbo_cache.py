
"""
Khiem Youtube V7.0
ULTRA TURBO CACHE

Cache SHA-256 and FFprobe duration.
No changes to CapCut export logic.
"""

from pathlib import Path
import hashlib
import sqlite3
import subprocess
import threading
import math

ROOT = Path(__file__).resolve().parent
DB = ROOT / "turbo_cache.sqlite3"

_local = threading.local()


def connection():
    db = getattr(_local, "db", None)

    if db is None:
        db = sqlite3.connect(
            str(DB),
            timeout=30
        )

        db.execute("PRAGMA busy_timeout=30000")

        db.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                path TEXT NOT NULL,
                kind TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                result TEXT NOT NULL,
                PRIMARY KEY (path, kind)
            )
        """)

        db.commit()
        _local.db = db

    return db


def fingerprint(path):
    p = Path(path).resolve()
    stat = p.stat()

    return (
        str(p),
        stat.st_size,
        stat.st_mtime_ns
    )


def get_cached(path, kind):
    name, size, modified = fingerprint(path)

    row = connection().execute(
        """
        SELECT result
        FROM cache
        WHERE path = ?
          AND kind = ?
          AND size = ?
          AND mtime_ns = ?
        """,
        (name, kind, size, modified)
    ).fetchone()

    return row[0] if row else None


def save_cached(path, kind, result):
    name, size, modified = fingerprint(path)

    db = connection()

    db.execute(
        """
        INSERT OR REPLACE INTO cache
        (path, kind, size, mtime_ns, result)
        VALUES (?, ?, ?, ?, ?)
        """,
        (name, kind, size, modified, str(result))
    )

    db.commit()


def digest_cached(path):
    cached = get_cached(path, "sha256")

    if cached is not None:
        return cached

    before = fingerprint(path)

    sha = hashlib.sha256()

    with open(path, "rb") as file:
        while True:
            block = file.read(4 * 1024 * 1024)

            if not block:
                break

            sha.update(block)

    result = sha.hexdigest()

    # Avoid storing a result if the source
    # changed during the calculation.
    if before == fingerprint(path):
        save_cached(path, "sha256", result)

    return result


def duration_cached(path):
    cached = get_cached(path, "duration")

    if cached is not None:
        value = float(cached)

        if math.isfinite(value) and value > 0:
            return value

    before = fingerprint(path)

    command = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=nw=1:nk=1",
        str(path)
    ]

    flags = getattr(
        subprocess,
        "CREATE_NO_WINDOW",
        0
    )

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=flags
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.decode(
                errors="replace"
            )[-2000:]
        )

    value = float(
        result.stdout.decode().strip()
    )

    if not math.isfinite(value) or value <= 0:
        raise ValueError(
            "Thời lượng file không hợp lệ: "
            + str(path)
        )

    if before == fingerprint(path):
        save_cached(path, "duration", value)

    return value


def cache_stats():
    db = connection()

    rows = db.execute(
        """
        SELECT kind, COUNT(*)
        FROM cache
        GROUP BY kind
        """
    ).fetchall()

    return dict(rows)


if __name__ == "__main__":
    print("KHIEM YOUTUBE TURBO CACHE")
    print("Cache:", DB)
    print("Thong ke:", cache_stats())
    print("SAN SANG")
