
"""
KHIEM YOUTUBE V7.1 AI SMART EDITOR

Adds contextual ranking to the existing CLIP score.
Does not modify CapCut, Turbo, or source media.
"""

import re
from pathlib import Path
from functools import wraps

STOPWORDS = {
    "the", "and", "for", "with", "from", "that",
    "this", "they", "them", "were", "have",
    "been", "when", "what", "your", "their",
    "about", "into", "then", "there", "would",
    "could", "should", "because", "before",
    "after", "while", "just", "very", "more",
    "some", "only", "over", "under", "also",
    "like", "never", "always", "people",
    "video", "image", "photo", "picture",
    "clip", "footage", "archive", "archival",
    "documentary", "interview", "number",
    "full", "final", "edit", "copy", "new"
}


def tokens(text):
    words = re.findall(
        r"[a-z0-9]+",
        str(text).lower()
    )

    return {
        word for word in words
        if len(word) >= 3
        and word not in STOPWORDS
        and not word.isdigit()
    }


def read_metadata(path):
    source = Path(path)

    # Existing optional metadata convention:
    # filename.mp4.txt or filename.jpg.txt
    sidecar = source.with_suffix(
        source.suffix + ".txt"
    )

    description = ""

    if sidecar.is_file():
        try:
            description = sidecar.read_text(
                encoding="utf-8-sig",
                errors="replace"
            )[:3000]
        except OSError:
            pass

    return source.stem, description


def contextual_bonus(path, query):
    query_words = tokens(query)

    if not query_words:
        return 0.0

    filename, description = read_metadata(path)

    name_words = tokens(filename)
    description_words = tokens(description)

    name_hits = len(
        query_words & name_words
    )

    description_hits = len(
        query_words & description_words
    )

    # Small, bounded bonuses.
    # CLIP remains the main ranking signal.
    name_bonus = min(
        0.045,
        name_hits * 0.015
    )

    description_bonus = min(
        0.035,
        description_hits * 0.007
    )

    return name_bonus + description_bonus


def install_smart_ranking(Semantic):
    if getattr(
        Semantic,
        "_khiem_v71_installed",
        False
    ):
        return Semantic

    original_score = Semantic.score

    @wraps(original_score)
    def smart_score(
        self,
        kind,
        path,
        start,
        length,
        query
    ):
        base_score = original_score(
            self,
            kind,
            path,
            start,
            length,
            query
        )

        # Preserve the original failure indicator.
        if base_score <= -1:
            return base_score

        bonus = contextual_bonus(
            path,
            query
        )

        return base_score + bonus

    Semantic.score = smart_score
    Semantic._khiem_v71_installed = True

    return Semantic


if __name__ == "__main__":
    print("KHIEM YOUTUBE V7.1 SMART EDITOR")
    print("Context ranking: READY")
    print("No CapCut modifications")
