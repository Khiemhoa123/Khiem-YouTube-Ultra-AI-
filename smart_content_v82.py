
import re
import unicodedata
from pathlib import Path

# KHIEM YOUTUBE V8.2
# Context-aware media ranking

KNOWN_PEOPLE = {
    "florence ballard": ["florence ballard", "florence"],
    "diana ross": ["diana ross"],
    "mary wilson": ["mary wilson"],
    "marvin gaye": ["marvin gaye"],
    "michael jackson": ["michael jackson"],
    "smokey robinson": ["smokey robinson"],
    "berry gordy": ["berry gordy"],
    "lionel richie": ["lionel richie"],
    "stevie wonder": ["stevie wonder"],
}

GROUPS = {
    "the supremes": ["supremes", "florence ballard",
                     "mary wilson", "diana ross"]
}


def normalize(text):
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(
        ch for ch in text if not unicodedata.combining(ch)
    )
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def mentioned_people(text):
    s = " " + normalize(text) + " "
    found = set()

    for person, aliases in KNOWN_PEOPLE.items():
        if any(" " + normalize(a) + " " in s
               for a in aliases):
            found.add(person)

    return found


def context_score(source, query, script="", main_person=""):
    """
    Returns an additive ranking adjustment.
    Does not claim to identify faces or verify events.
    """
    name = normalize(Path(source).stem)
    context = normalize(query)
    script_context = normalize(script)

    targets = mentioned_people(context)

    if not targets and main_person:
        targets = mentioned_people(main_person)

    if not targets:
        return 0.0, "No named target"

    media_people = mentioned_people(name)
    bonus = 0.0
    notes = []

    for group, members in GROUPS.items():
        if group in name:
            if targets.intersection(members):
                bonus += 0.22
                notes.append("Relevant group")

    if media_people.intersection(targets):
        bonus += 0.40
        notes.append("Person name matched")

    elif media_people and not media_people.intersection(targets):
        bonus -= 0.65
        notes.append("Different named person")

    elif not media_people:
        notes.append("Identity unverified")

    if "supremes" in context and "supremes" in name:
        bonus += 0.12
        notes.append("Group context matched")

    return max(-0.8, min(0.8, bonus)), ", ".join(notes)


def rank_adjustment(source, query, script="", main_person=""):
    return context_score(
        source, query, script, main_person
    )[0]
