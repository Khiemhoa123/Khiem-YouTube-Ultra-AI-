
# KHIEM YOUTUBE V8.1
# SMART SELECTOR - SAFE INSTALLER
# Compatible with supplied V8.0 app.py

import ast
import os
import re
import sys
import shutil
import tokenize
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
APP = ROOT / "app.py"
MODULE = ROOT / "smart_selector_v81.py"
MARKER = "# KHIEM_SMART_SELECTOR_V81_INSTALLED"

IMPORTS = """
# KHIEM_SMART_SELECTOR_V81_INSTALLED
from smart_selector_v81 import (
    image_allowed as v81_image_allowed,
    remember_image as v81_remember_image,
    is_export as v81_is_export,
    save_timeline_report as v81_save_report,
)
"""


def fail(message):
    raise RuntimeError(message)


def find_function(tree, name):
    matches = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == name
    ]
    if len(matches) != 1:
        fail(f"Khong tim thay duy nhat ham {name}()")
    return matches[0]


def find_lines(source, pattern, label):
    matches = list(
        re.finditer(pattern, source, re.MULTILINE)
    )
    if len(matches) != 1:
        fail(
            f"{label}: tim thay {len(matches)} vi tri. "
            "Dung cai dat de bao ve app.py."
        )
    return matches[0]


def replace_line(source, pattern, builder, label):
    match = find_lines(source, pattern, label)
    return (
        source[:match.start()]
        + builder(match)
        + source[match.end():]
    )


def check_plan(source):
    tree = ast.parse(source)
    plan = find_function(tree, "plan")
    find_function(tree, "render")

    required = {"c", "log"}
    parameters = {
        arg.arg for arg in plan.args.args
    }
    if not required.issubset(parameters):
        fail("Ham plan() khong co tham so c, log")

    return plan


def patch(source):
    # Check the supplied V8.0 structure.
    plan = check_plan(source)

    # 1. Track perceptual image hashes.
    source = replace_line(
        source,
        r"^(?P<indent>[ \t]*)(?P<line>[^\n]*\bused=set\(\);[^\n]*\bintervals=\{\};[^\n]*)$",
        lambda m: (
            m.group("indent")
            + m.group("line").replace(
                "used=set();",
                "used=set(); used_images=[];",
                1
            )
        ),
        "Khoi tao used_images"
    )

    # 2. Exclude exported videos before pool insertion.
    def add_video_filter(m):
        indent = m.group("indent")
        return (
            indent
            + "if kind == 'video' and "
            + "v81_is_export(src, c):\n"
            + indent
            + "    log('V81: Bo qua video thanh pham: '"
            + "+str(src))\n"
            + indent
            + "    continue\n"
            + indent
            + "pools[kind].append(src)"
        )

    source = replace_line(
        source,
        r"^(?P<indent>[ \t]*)pools\[kind\]\.append\(src\)[ \t]*$",
        add_video_filter,
        "Loc video thanh pham"
    )

    # 3. Reject visually similar images.
    def add_image_check(m):
        indent = m.group("indent")
        return (
            indent + "if h in used: continue\n"
            + indent
            + "if kind == 'image' and "
            + "not v81_image_allowed(src, used_images):\n"
            + indent + "    continue"
        )

    source = replace_line(
        source,
        r"^(?P<indent>[ \t]*)if h in used:[ \t]*continue[ \t]*$",
        add_image_check,
        "Chong anh gan trung"
    )

    # 4. Remember each selected image.
    def add_remember(m):
        indent = m.group("indent")
        return (
            indent
            + "if kind=='image':\n"
            + indent + "    used.add(h)\n"
            + indent
            + "    v81_remember_image(src, used_images)"
        )

    source = replace_line(
        source,
        r"^(?P<indent>[ \t]*)if kind\s*==\s*['\"]image['\"]:[ \t]*used\.add\(h\)[ \t]*$",
        add_remember,
        "Ghi nho anh"
    )

    # 5. Locate return parts within plan().
    plan = check_plan(source)

    returns = [
        node for node in ast.walk(plan)
        if isinstance(node, ast.Return)
        and isinstance(node.value, ast.Name)
        and node.value.id == "parts"
    ]

    if len(returns) != 1:
        fail(
            "Ham plan() phai co duy nhat "
            "mot lenh return parts"
        )

    lines = source.splitlines(keepends=True)
    index = returns[0].lineno - 1
    original_line = lines[index]

    indent = re.match(
        r"^[ \t]*", original_line
    ).group(0)

    lines.insert(
        index,
        indent
        + "v81_save_report(c, parts, log)\n"
    )

    source = "".join(lines)

    # 6. Insert imports safely after existing imports.
    tree = ast.parse(source)
    insert_at = 0

    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            insert_at = node.end_lineno
        elif isinstance(node, ast.Expr) and isinstance(
            node.value, ast.Constant
        ) and isinstance(node.value.value, str):
            if node == tree.body[0]:
                insert_at = node.end_lineno

    lines = source.splitlines(keepends=True)
    lines.insert(insert_at, "\n" + IMPORTS + "\n")
    source = "".join(lines)

    ast.parse(source)

    return source


def install():
    print("=" * 55)
    print("KHIEM YOUTUBE V8.1 SMART SELECTOR")
    print("=" * 55)

    if not APP.is_file():
        fail("Khong tim thay app.py cung thu muc")

    if not MODULE.is_file():
        fail("Khong tim thay smart_selector_v81.py")

    with tokenize.open(str(APP)) as f:
        original = f.read()

    with tokenize.open(str(MODULE)) as f:
        module_source = f.read()

    ast.parse(module_source, filename=str(MODULE))

    if MARKER in original:
        print("V81 da duoc cai dat. Khong cai lap.")
        return

    # No changes to app.py before full validation.
    updated = patch(original)
    compile(updated, str(APP), "exec")

    # Verify required helper functions exist.
    module_tree = ast.parse(module_source)
    names = {
        node.name for node in module_tree.body
        if isinstance(node, ast.FunctionDef)
    }

    required = {
        "image_allowed",
        "remember_image",
        "is_export",
        "save_timeline_report"
    }

    if not required.issubset(names):
        fail(
            "smart_selector_v81.py thieu ham: "
            + ", ".join(sorted(required - names))
        )

    backup_dir = ROOT / "_V81_BACKUPS"
    backup_dir.mkdir(exist_ok=True)

    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    backup = (
        backup_dir / f"app_before_v81_{stamp}.py"
    )

    shutil.copy2(APP, backup)

    temp = ROOT / "_app_v81_install_pending.py"

    try:
        temp.write_text(updated, encoding="utf-8")
        compile(
            temp.read_text(encoding="utf-8"),
            str(temp),
            "exec"
        )

        os.replace(str(temp), str(APP))

    finally:
        if temp.exists():
            temp.unlink()

    print()
    print("================================")
    print("CAI DAT THANH CONG")
    print("================================")
    print()
    print("Da sao luu app.py:")
    print(backup)
    print()
    print("1. Chong anh gan trung")
    print("2. Loc video thanh pham")
    print("3. Bao cao timeline")
    print()
    print("KHONG SUA capcut.py")
    print("KHONG SUA semantic.py")
    print("KHONG SUA thu muc template")
    print()
    print("Hay chay phan mem thu nghiem.")


if __name__ == "__main__":
    try:
        install()
    except Exception as e:
        print()
        print("CAI DAT THAT BAI:")
        print(str(e))
        print("Khong ghi de app.py neu chua kiem tra xong.")
        sys.exit(1)
