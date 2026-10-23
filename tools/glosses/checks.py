"""Automatic checks on one model answer. They test form, not meaning: whether a gloss is right is
judged by the owner in the review column of the run file.

- parses: a JSON object with non-empty string fields `gloss` and `explanation` (a ```json fence is
  tolerated).
- vietnamese: at least VI_SHARE of the words carry a Vietnamese tone or vowel mark (or d-stroke).
  Marks are tested on the NFD form by code point, so this file holds no Vietnamese letter.
- no_english: no run of ENGLISH_RUN or more English words in a row (CEFR-J/Octanove headwords
  and their inflections, ASCII only) once the target word is taken out: the sentence, or any
  other English, is not copied in.
- short: gloss at most GLOSS_MAX characters, explanation at most EXPLANATION_MAX.
"""

import json
import re
import unicodedata

from voa_corpus import wordlist

VI_MARKS = {0x0300, 0x0301, 0x0302, 0x0303, 0x0306, 0x0309, 0x031B, 0x0323}
D_STROKE = {chr(0x0110), chr(0x0111)}
VI_SHARE, ENGLISH_RUN, GLOSS_MAX, EXPLANATION_MAX = 0.3, 3, 40, 160
WORD = re.compile(r"[^\W\d_]+")
CHECKS = ("parses", "vietnamese", "no_english", "short")


def parse(text: str) -> dict[str, str] | None:
    body = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        found = json.loads(body)
    except json.JSONDecodeError:
        return None
    fields = ("gloss", "explanation")
    if not isinstance(found, dict) or not all(isinstance(found.get(f), str) for f in fields):
        return None
    out = {f: found[f].strip() for f in fields}
    return out if all(out.values()) else None


def marked(word: str) -> bool:
    nfd = unicodedata.normalize("NFD", word)
    return any(ord(c) in VI_MARKS or c in D_STROKE for c in nfd)


def english_run(text: str, target: str, table: dict[str, int]) -> int:
    longest = run = 0
    for word in WORD.findall(text):
        low = word.lower()
        english = low != target and low.isascii() and wordlist.level_of(low, table) is not None
        run = run + 1 if english else 0
        longest = max(longest, run)
    return longest


def check(
    text: str, target: str, table: dict[str, int]
) -> tuple[dict[str, str] | None, dict[str, bool]]:
    answer = parse(text)
    if answer is None:
        return None, dict.fromkeys(CHECKS, False) | {"parses": False}
    both = f"{answer['gloss']} {answer['explanation']}"
    words = WORD.findall(both)
    return answer, {
        "parses": True,
        "vietnamese": bool(words) and sum(map(marked, words)) / len(words) >= VI_SHARE,
        "no_english": english_run(both, target, table) < ENGLISH_RUN,
        "short": len(answer["gloss"]) <= GLOSS_MAX
        and len(answer["explanation"]) <= EXPLANATION_MAX,
    }
