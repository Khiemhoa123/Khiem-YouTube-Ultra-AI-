# -*- coding: utf-8 -*-
"""Script-first matching. Fast, deterministic, no external API calls."""
import re
from collections import Counter
from pathlib import Path

VERSION = "1.0"
STOP = set(("the a an and or but with from that this there their they them then when where what who how was were are is of in on at to for by as it its i my me we you your he she his her our not can could would should have has had be been do did into about after before most ever greatest people person voice song music singer singers artist artists number opening ending full mp4 video interview youtube ytsave media 1080p 720p official live audio").split())
TOKEN = re.compile(r"[A-Za-z][A-Za-z']+")
NAME = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\b")
NOISE = {"The", "When", "After", "Before", "Number", "Opening", "Ending", "Voice", "Greatest", "American", "YouTube", "Smart", "Interview"}

def words(text):
    return [w.lower() for w in TOKEN.findall(str(text)) if len(w) > 2 and w.lower() not in STOP]

def names(text):
    result = set()
    for match in NAME.findall(str(text)):
        chunks = match.split()
        if chunks[0] not in NOISE and chunks[-1] not in NOISE:
            result.add(" ".join(chunks).lower())
    return result

def prepare(scripts, log):
    """Read ALL script sections before choosing any media."""
    sections = {}
    corpus = []
    for n, path in sorted(scripts.items()):
        content = Path(path).read_text(encoding="utf-8-sig", errors="replace")
        if not content.strip():
            raise ValueError("TXT rỗng: " + str(path))
        sections[n] = {"text": content, "tokens": words(content), "names": names(content)}
        corpus.extend(sections[n]["tokens"])
    counts = Counter(corpus)
    # Common words in the whole story are less discriminative than local details.
    for n, data in sections.items():
        data["counts"] = Counter(data["tokens"])
    log("SCRIPT FIRST: Đã đọc %d TXT, %d từ khóa, trước khi chọn tư liệu." %
        (len(sections), len(corpus)))
    return {"sections": sections, "global_counts": counts}

def score_media(query, source, story, section, label_text=None):
    """Cheap context scoring, with conservative person mismatch penalty.
    Names are inferred only from actual script and filename, never from a face.
    """
    label = str(label_text if label_text is not None else Path(source).stem)
    qwords = set(words(query))
    lwords = set(words(label))
    if not qwords or not lwords:
        return 0.0
    global_counts = story["global_counts"]
    overlap = qwords & lwords
    score = sum(1.0 / (1.0 + global_counts.get(w, 0) ** 0.5) for w in overlap)
    # Names in the immediate narration are more important than generic tags.
    qnames = names(query)
    source_names = names(label.replace("_", " ").replace("-", " "))
    section_names = story["sections"][section]["names"]
    # Only evaluate names known from the actual script to avoid treating titles as people.
    relevant = qnames & section_names
    known_source = source_names & set().union(*(s["names"] for s in story["sections"].values()))
    if relevant and known_source:
        if relevant & known_source:
            score += 3.0
        elif not relevant & known_source:
            score -= 4.0
    return max(-4.0, min(5.0, score))

def query_at(section, fraction, width=42):
    tokens = section["text"].split()
    if not tokens:
        return ""
    center = min(len(tokens)-1, max(0, int(len(tokens) * fraction)))
    half = width // 2
    return " ".join(tokens[max(0, center-half):min(len(tokens), center+half)])
