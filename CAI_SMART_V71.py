
"""
Safe installer for Khiem Youtube V7.1.
"""

from pathlib import Path
import shutil
import py_compile
import sys

ROOT = Path(__file__).resolve().parent

SEMANTIC = ROOT / "semantic.py"
SMART = ROOT / "smart_v71.py"
BACKUP = ROOT / "semantic_before_v71.py.bak"

MARKER = "# KHIEM_V71_SMART_RANKING"

PATCH = """

# KHIEM_V71_SMART_RANKING
from smart_v71 import install_smart_ranking
install_smart_ranking(Semantic)
"""


def main():
    print("=" * 50)
    print("KHIEM YOUTUBE V7.1 AI SMART EDITOR")
    print("=" * 50)

    if not SEMANTIC.is_file():
        print("LOI: Thieu semantic.py")
        return 1

    if not SMART.is_file():
        print("LOI: Thieu smart_v71.py")
        return 1

    try:
        py_compile.compile(
            str(SMART),
            doraise=True
        )
        py_compile.compile(
            str(SEMANTIC),
            doraise=True
        )
    except Exception as error:
        print("LOI CU PHAP:", error)
        return 1

    original = SEMANTIC.read_text(
        encoding="utf-8-sig"
    )

    if MARKER in original:
        print("V7.1 da duoc cai truoc do.")
        print("Khong can cai lai.")
        return 0

    if BACKUP.exists():
        print(
            "DA CO BACKUP CU.",
            "Dung lai de tranh ghi de."
        )
        return 1

    if "class Semantic:" not in original:
        print(
            "Ma nguon khong dung phien ban.",
            "Khong thay doi file."
        )
        return 1

    shutil.copy2(
        SEMANTIC,
        BACKUP
    )

    try:
        updated = original.rstrip() + PATCH

        SEMANTIC.write_text(
            updated,
            encoding="utf-8"
        )

        py_compile.compile(
            str(SEMANTIC),
            doraise=True
        )

        # Verify the patch can be imported.
        # This does not load CLIP weights.
        sys.path.insert(0, str(ROOT))

        import smart_v71

        assert callable(
            smart_v71.install_smart_ranking
        )

        print()
        print("CAI DAT THANH CONG")
        print("Da nang cap: semantic.py")
        print("Da sao luu:", BACKUP.name)
        print("Giu nguyen: app.py")
        print("Giu nguyen: capcut.py")
        print("Giu nguyen: turbo_cache.py")

        return 0

    except Exception as error:
        shutil.copy2(
            BACKUP,
            SEMANTIC
        )

        print("LOI:", error)
        print("Da khoi phuc semantic.py")
        return 1


if __name__ == "__main__":
    sys.exit(main())
