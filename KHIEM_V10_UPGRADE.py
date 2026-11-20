
# -*- coding: utf-8 -*-
"""
KHIEM YOUTUBE V10.0
SAFE CORE UPGRADE

Run once:
    python KHIEM_V10_UPGRADE.py

Keeps the original CapCut exporter and AI modules.
Creates a backup before modifying app.py.
"""

from pathlib import Path
import ast
import shutil
import sys

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app.py"
BACKUP = ROOT / "app_before_v10.py"


def replace_once(source, old, new, title):
    count = source.count(old)

    if count != 1:
        raise RuntimeError(
            f"{title}: expected 1 match, found {count}. "
            "Original file has not been changed."
        )

    return source.replace(old, new, 1)


def upgrade():
    print("=" * 55)
    print("KHIEM YOUTUBE V10.0 CORE UPGRADE")
    print("=" * 55)

    if not APP.is_file():
        raise FileNotFoundError(
            "Cannot find app.py in this folder."
        )

    original = APP.read_text(encoding="utf-8-sig")

    if "V10.0 CORE" in original:
        print("This app.py has already been upgraded.")
        return

    code = original

    # 1. Update version labels.
    code = replace_once(
        code,
        'VERSION = "KHIEM YOUTUBE V8.2 SMART CONTENT MATCHING"',
        'VERSION = "KHIEM YOUTUBE V10.0 CORE"',
        "Version"
    )

    code = replace_once(
        code,
        "text='KHIÊM YOUTUBE V8.2',",
        "text='KHIÊM YOUTUBE V10.0 CORE',",
        "Window heading"
    )

    # 2. Exclude previously exported MP4 files.
    old = """                            if v81_is_export(src, c):
                                log(
                                    'V8.2: Giữ video nguồn: '
                                    + str(src)
                                )

                        pools[kind].append(src)"""

    new = """                            if v81_is_export(src, c):
                                log(
                                    'V10: Bỏ video đã xuất: '
                                    + str(src)
                                )
                                continue

                        pools[kind].append(src)"""

    code = replace_once(
        code, old, new,
        "Exclude exported videos"
    )

    # 3. Disable unsafe timeline reuse.
    # A new timeline is built on every operation.
    old = """                if (
                    key in cached
                    and mode != 'check'
                ):
                    parts = cached[key]
                    log(
                        'Dùng timeline đã kiểm tra'
                    )
                else:
                    parts = plan(c, log)
                    cached.clear()
                    cached[key] = parts"""

    new = """                # V10: Rebuild timeline to reflect current files.
                # Avoid stale media selections.
                parts = plan(c, log)
                cached.clear()
                cached[key] = parts
                log('V10: Timeline được cập nhật từ tư liệu hiện tại')"""

    code = replace_once(
        code, old, new,
        "Timeline refresh"
    )

    # 4. Skip unreadable CLIP candidates.
    old = """                        score = (
                            score * 0.12
                            + best[0]
                        )
                        start = best[1]"""

    new = """                        if best[0] <= -1:
                            log(
                                'V10: Bỏ tư liệu AI không đọc được: '
                                + str(src)
                            )
                            continue

                        score = (
                            score * 0.12
                            + best[0]
                        )
                        start = best[1]"""

    code = replace_once(
        code, old, new,
        "CLIP invalid frame handling"
    )

    # 5. Check source video boundaries.
    old = """                candidates.append((
                    score,
                    gap,
                    rng.random(),
                    src,
                    h,
                    start
                ))"""

    new = """                if kind == 'video':
                    if (
                        not math.isfinite(start)
                        or start < 0
                        or start + t > lens[h] + 0.001
                    ):
                        continue

                    overlap = any(
                        start < right - 0.001
                        and start + t > left + 0.001
                        for left, right in intervals.get(h, [])
                    )

                    if overlap:
                        continue

                candidates.append((
                    score,
                    gap,
                    rng.random(),
                    src,
                    h,
                    start
                ))"""

    code = replace_once(
        code, old, new,
        "Video overlap protection"
    )

    # 6. Ensure output MP4 can be overwritten
    # after the user confirms in the interface.
    old = """        run([
            'ffmpeg',
            '-v', 'error',
            '-y',
            '-i', str(visual),"""

    if old not in code:
        raise RuntimeError(
            "Final MP4 command not found."
        )

    # Already includes -y, so preserve it.
    print("MP4 overwrite: existing implementation retained.")

    # 7. Update operation log.
    code = replace_once(
        code,
        "'=== KHIÊM YOUTUBE V8.2 ==='",
        "'=== KHIÊM YOUTUBE V10.0 CORE ==='",
        "Log heading"
    )

    # Validate syntax before writing.
    ast.parse(code, filename=str(APP))

    if not BACKUP.exists():
        shutil.copy2(APP, BACKUP)
        print("Backup:", BACKUP.name)
    else:
        print("Existing backup preserved:", BACKUP.name)

    temporary = ROOT / "app_v10_pending.tmp"

    try:
        temporary.write_text(
            code,
            encoding="utf-8"
        )
        ast.parse(
            temporary.read_text(encoding="utf-8"),
            filename=str(temporary)
        )
        temporary.replace(APP)
    finally:
        if temporary.exists():
            temporary.unlink()

    print()
    print("UPGRADE COMPLETED")
    print("Updated:", APP.name)
    print("CapCut exporter: unchanged")
    print("AI modules: unchanged")
    print()
    print("Next command:")
    print("python app.py")


if __name__ == "__main__":
    try:
        upgrade()
    except Exception as error:
        print()
        print("UPGRADE FAILED:", error)
        print("Check that app.py is the original V8.2 file.")
        sys.exit(1)

    input("\nPress Enter to close...")
