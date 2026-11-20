
"""
Khiem Youtube V7.0
Safe cache upgrade installer.
"""

from pathlib import Path
import shutil
import py_compile
import sys

ROOT = Path(__file__).resolve().parent

APP = ROOT / "app.py"
CACHE = ROOT / "turbo_cache.py"
BACKUP = ROOT / "app_before_turbo.py.bak"

IMPORT_LINE = (
    "from turbo_cache import "
    "digest_cached, duration_cached"
)

REPLACEMENTS = [
    (
        "dur=duration(p)",
        "dur=duration_cached(p)"
    ),
    (
        "h=hashes.setdefault(src,digest(src))",
        "h=hashes.setdefault(src,digest_cached(src))"
    ),
    (
        "lens[h]=duration(src)",
        "lens[h]=duration_cached(src)"
    )
]


def main():
    print("=" * 48)
    print("KHIEM YOUTUBE V7.0 ULTRA TURBO")
    print("CAI DAT CACHE TANG TOC")
    print("=" * 48)

    if not APP.is_file():
        print("LOI: Khong tim thay app.py")
        return 1

    if not CACHE.is_file():
        print("LOI: Khong tim thay turbo_cache.py")
        return 1

    try:
        py_compile.compile(
            str(CACHE),
            doraise=True
        )
    except Exception as error:
        print("LOI CU PHAP CACHE:", error)
        return 1

    original = APP.read_text(
        encoding="utf-8-sig"
    )

    if IMPORT_LINE in original:
        print("Ban Turbo da duoc cai truoc do.")
        print("Khong can cai lai.")
        return 0

    updated = original

    for old, new in REPLACEMENTS:
        count = updated.count(old)

        if count != 1:
            print(
                "KHONG SUA APP.PY:",
                repr(old),
                "so lan xuat hien:",
                count
            )
            print(
                "Ma nguon khac du kien."
            )
            return 1

        updated = updated.replace(
            old, new, 1
        )

    # Insert new import after the existing imports.
    marker = "A={'.mp3'"

    if marker not in updated:
        print(
            "LOI: Khong tim thay vi tri import."
        )
        return 1

    updated = updated.replace(
        marker,
        IMPORT_LINE + "\n" + marker,
        1
    )

    if BACKUP.exists():
        print(
            "Da co file sao luu:",
            BACKUP.name
        )
        print(
            "Dung cai dat de tranh ghi de backup."
        )
        return 1

    shutil.copy2(APP, BACKUP)

    try:
        APP.write_text(
            updated,
            encoding="utf-8"
        )

        py_compile.compile(
            str(APP),
            doraise=True
        )

        print("CAI DAT THANH CONG")
        print("Da tao:", BACKUP.name)
        print("Da cap nhat: app.py")
        print("Khong sua: capcut.py")
        print("Khong sua: semantic.py")

        return 0

    except Exception as error:
        print("LOI:", error)
        print("Dang khoi phuc app.py")

        shutil.copy2(BACKUP, APP)

        print("Da khoi phuc app.py")
        return 1


if __name__ == "__main__":
    sys.exit(main())
