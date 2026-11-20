
# KHIEM YOUTUBE V8.0
# SMART SELECTOR V81
# Safe integration with existing app.py

import json
from pathlib import Path
from functools import lru_cache
from datetime import datetime

from PIL import Image, ImageOps


@lru_cache(maxsize=20000)
def image_hash(path, size, mtime):
    """64-bit difference hash."""
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
    p = Path(path)
    st = p.stat()
    return image_hash(
        str(p.resolve()),
        st.st_size,
        st.st_mtime_ns
    )


def image_allowed(path, selected_hashes):
    """
    Reject images that look too similar to
    images already selected for the timeline.

    Threshold 3 is deliberately conservative.
    """
    try:
        current = get_hash(path)

        for previous in selected_hashes:
            distance = (current ^ previous).bit_count()

            if distance <= 3:
                return False

        return True

    except Exception:
        # Original app handles unreadable images.
        return True


def remember_image(path, selected_hashes):
    try:
        selected_hashes.append(get_hash(path))
    except Exception:
        pass


def is_export(path, config):
    """
    Exclude videos inside the configured
    export folder and the current project's
    exported MP4.
    """
    try:
        p = Path(path).resolve()
        out = Path(config["out"]).resolve()

        if p == out or out in p.parents:
            return True

        name = config.get("name", "").strip()

        if name and p.name.lower() == (
            name + ".mp4"
        ).lower():
            return True

    except Exception:
        pass

    return False


def save_timeline_report(config, parts, log):
    """Write a non-destructive scene report."""
    out = Path(config["out"])
    out.mkdir(parents=True, exist_ok=True)

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
        "version": "8.0-smart-selector-v81",
        "created_at": datetime.now().isoformat(),
        "project": config.get("name", ""),
        "scene_count": len(scenes),
        "image_count": sum(
            s["type"] == "image" for s in scenes
        ),
        "video_count": sum(
            s["type"] == "video" for s in scenes
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
        "V8 SMART SELECTOR: "
        + str(len(scenes))
        + " cảnh đã được ghi báo cáo."
    )

    log("Báo cáo: " + str(destination))
