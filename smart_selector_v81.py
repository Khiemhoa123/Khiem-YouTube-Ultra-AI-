
# KHIEM YOUTUBE V10.0
# SMART SELECTOR V81
# Fixed source video exclusion
# Compatible with existing app.py

import json
from pathlib import Path
from functools import lru_cache
from datetime import datetime

from PIL import Image, ImageOps


# ============================================================
# IMAGE HASH
# ============================================================

@lru_cache(maxsize=20000)
def image_hash(path, size, mtime):
    """Calculate a 64-bit difference hash."""

    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im)
        im = im.convert("L").resize((9, 8))
        pixels = list(im.getdata())

    value = 0

    for y in range(8):
        for x in range(8):
            left = pixels[y * 9 + x]
            right = pixels[y * 9 + x + 1]

            value = (value << 1) | int(left > right)

    return value


def get_hash(path):
    """Get cached hash of an image."""

    p = Path(path)
    st = p.stat()

    return image_hash(
        str(p.resolve()),
        st.st_size,
        st.st_mtime_ns
    )


# ============================================================
# PREVENT DUPLICATE IMAGES
# ============================================================

def image_allowed(path, selected_hashes):
    """
    Reject images that are visually too similar
    to images already selected for the timeline.

    A Hamming distance of 3 or less is rejected.
    """

    try:
        current = get_hash(path)

        for previous in selected_hashes:
            distance = (current ^ previous).bit_count()

            if distance <= 3:
                return False

        return True

    except Exception:
        # Let the original application handle
        # unreadable or invalid images.
        return True


def remember_image(path, selected_hashes):
    """Remember an image selected for the timeline."""

    try:
        selected_hashes.append(get_hash(path))

    except Exception:
        pass


# ============================================================
# FIX: PROTECT SOURCE VIDEOS
# ============================================================

def is_export(path, config):
    """
    Detect exported media without rejecting source videos.

    Source videos stored in:
        video/1/
        video/2/
        video/3/
        ...

    are always treated as source media.

    Files directly inside the configured output
    directory are treated as exported files.
    """

    try:
        p = Path(path).resolve()

        out_value = config.get("out")

        if not out_value:
            return False

        out = Path(out_value).resolve()

        # Protect source videos in numbered folders.
        #
        # Example:
        # KHIEM_OUTPUT/video/1/2.mp4
        # KHIEM_OUTPUT/video/2/source.mp4

        if (
            p.parent.name.isdigit()
            and p.parent.parent.name.lower() == "video"
        ):
            return False

        # Reject exported files located directly
        # inside the configured output folder.

        if p.parent == out:
            return True

        # Do not reject media in subfolders
        # merely because they are under output.

        return False

    except (OSError, ValueError, TypeError, AttributeError):
        return False


# ============================================================
# SAVE TIMELINE REPORT
# ============================================================

def save_timeline_report(config, parts, log):
    """Write a non-destructive scene report."""

    out = Path(config["out"])

    out.mkdir(
        parents=True,
        exist_ok=True
    )

    scenes = []

    for part in parts:

        for clip in part["clips"]:

            scenes.append({
                "part": part["number"],
                "type": clip["type"],
                "source": clip["source"],
                "source_start": clip["source_start"],
                "timeline_start": clip["start"],
                "duration": clip["duration"],
                "frames": clip["frames"],
                "effect": clip.get("effect", "")
            })

    report = {
        "version": "10.0-smart-selector-v81",
        "created_at": datetime.now().isoformat(),
        "project": config.get("name", ""),
        "scene_count": len(scenes),
        "image_count": sum(
            s["type"] == "image"
            for s in scenes
        ),
        "video_count": sum(
            s["type"] == "video"
            for s in scenes
        ),
        "scenes": scenes
    }

    filename = (
        config.get("name", "project")
        + ".smart_v81.json"
    )

    destination = out / filename

    destination.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    log(
        "V10 SMART SELECTOR: "
        + str(len(scenes))
        + " cảnh đã được ghi báo cáo."
    )

    log(
        "Báo cáo: "
        + str(destination)
    )
