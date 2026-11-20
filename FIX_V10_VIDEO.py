
# -*- coding: utf-8 -*-
from pathlib import Path
import shutil
import ast

root = Path(__file__).resolve().parent
target = root / "smart_selector_v81.py"
backup = root / "smart_selector_v81_before_fix.py"

source = target.read_text(encoding="utf-8-sig")

start = source.index("def is_export(")
end = source.index("\ndef save_timeline_report(", start)

replacement = '''
def is_export(path, config):
    """
    Only exclude media physically inside
    the configured output directory.
    Never reject source video by filename alone.
    """
    try:
        p = Path(path).resolve()
        out = Path(config["out"]).resolve()

        if p == out or out in p.parents:
            return True

    except (OSError, ValueError):
        pass

    return False

'''

updated = source[:start] + replacement + source[end:]
ast.parse(updated)

if not backup.exists():
    shutil.copy2(target, backup)

target.write_text(updated, encoding="utf-8")

print("DA SUA XONG LOI LOAI NHAM VIDEO")
print("Backup:", backup.name)
print("Chay lai: python app.py")
