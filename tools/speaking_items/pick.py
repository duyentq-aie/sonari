"""`make speaking-items`: pick the practice sentences from the trimmed corpus (ADR-0006).

A sentence is a slice of one line of a passage's trimmed `text`, unchanged, with the offsets that
find it again. It pins the `Source._id` it came from (ADR-0010) and carries the expected phonemes
from G2P, so the API never recomputes them. Runs in the speech service's environment (G2P), so
the imports of `sonari_speech` are inside `main`.
"""

import json
import re
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

UNIT = "Study and work"
OUT = Path(__file__).with_name("items.jsonl")
COUNT, WORDS, PER_PASSAGE = 20, range(6, 15), 2
COMMON = 30  # a sentence may start with a word the corpus writes in lower case at least this often
# What the demo needs to show real errors (feedback.yaml): the two sounds that have a pair rule,
# and a word that ends in s or z. At least this many sentences each, scarcest first.
QUOTA = {"θ": 5, "ð": 5, "final s/z": 5}
SENTENCE = re.compile(r"\S.*?[.?!](?=\s|$)")
PLAIN = re.compile(r"[A-Z][A-Za-z'’, ]*[.?!]")  # no digit, quote, bracket, dash or colon
# A sentence that starts with one of these leans on text the learner has not seen.
STARTERS = frozenset(
    {"he", "she", "it", "they", "we", "this", "that", "these", "those", "but", "and", "so", "or"}
    | {"however", "also", "then", "his", "her", "their", "its", "our", "both", "instead", "others"}
    | {"more", "now"}
)
REPORTED = re.compile(r",\s+\w+\s+(?:says|said)\b")  # "..., she says, ..." needs the speaker
RELIABLE = {"dictionary", "lexicon", "contraction"}  # not a g2p_en guess


@dataclass
class Candidate:
    source: str  # the pinned Source._id: voa:<article>@<rules_version>
    line: int  # index into that Source's `text`
    start: int  # offset of the sentence in that line
    text: str
    words: list[dict[str, Any]]
    on_topic: bool = False  # the passage's title, not only its lead, is about the unit

    @property
    def marks(self) -> frozenset[str]:
        found = {t for w in self.words for t in w["tokens"] if t in ("θ", "ð")}
        return frozenset(
            found | {"final s/z"} if any(w["tokens"][-1] in "sz" for w in self.words) else found
        )


def lowercase_words(lines: Iterator[str]) -> Counter[str]:
    """How often the corpus writes each word in lower case: a capitalised word that is rarely
    seen so (Obama, Thread the charity) is taken for a proper noun."""
    return Counter(w for line in lines for w in re.findall(r"(?<![A-Za-z])[a-z]+", line))


def plain(text: str, vocab: Counter[str]) -> bool:
    """No proper noun, acronym, number, abbreviation or odd punctuation; a start that is whole."""
    if not PLAIN.fullmatch(text) or REPORTED.search(text):
        return False
    first, *rest = re.findall(r"[A-Za-z][A-Za-z'’]*", text)
    common = first == "I" or vocab[first.lower()] >= COMMON
    return (
        first.lower() not in STARTERS
        and common
        and (len(first) == 1 or first[1:].islower())  # not an acronym
        and all(w.islower() or w == "I" or w[:2] in ("I'", "I’") for w in rest)
    )


def practicable(
    text: str, vocab: Counter[str], pronounce: Callable[[str], Sequence[Any]]
) -> Sequence[Any]:
    """The sentence's words when a learner can practise it, else nothing: plain, 6-14 words, and
    every word pronounced from a source that is not a guess. Also what the passage view marks
    (classes.py)."""
    words = pronounce(text) if plain(text, vocab) else []
    return words if len(words) in WORDS and all(w.source in RELIABLE for w in words) else []


def candidates(
    row: dict[str, Any],
    vocab: Counter[str],
    pronounce: Callable[[str], Sequence[Any]],
    on_topic: bool = False,
) -> Iterator[Candidate]:
    source = f"voa:{row['id']}@{row['raw']['trim']['rules_version']}"
    for number, line in enumerate(row["raw"]["text"]):
        for match in SENTENCE.finditer(line):
            if words := practicable(match.group(), vocab, pronounce):
                spans = [
                    {"text": w.text, "start": w.start, "end": w.end, "tokens": list(w.tokens)}
                    for w in words
                ]
                yield Candidate(source, number, match.start(), match.group(), spans, on_topic)


def select(pool: Sequence[Candidate]) -> list[Candidate]:
    """Scarcest sound first, at most PER_PASSAGE from a passage, then the sentences that show the
    most, those of a passage titled for the unit first. Deterministic: ties break on position."""
    ranked = sorted(
        pool,
        key=lambda c: (
            not c.on_topic,
            -len(c.marks),
            abs(len(c.words) - 10),
            c.source,
            c.line,
            c.start,
        ),
    )
    chosen: list[Candidate] = []
    per_passage: Counter[str] = Counter()

    def add(c: Candidate) -> None:
        new = all(c.text != x.text for x in chosen)  # VOA published some articles twice
        if new and per_passage[c.source] < PER_PASSAGE and len(chosen) < COUNT:
            chosen.append(c)
            per_passage[c.source] += 1

    for mark, quota in QUOTA.items():
        for c in ranked:
            if sum(mark in x.marks for x in chosen) >= quota:
                break
            if mark in c.marks:
                add(c)
    for c in ranked:
        add(c)
    return sorted(chosen, key=lambda c: (c.source, c.line, c.start))


def main() -> None:
    from sonari_speech.g2p import G2pEnBackend, Pronouncer
    from sonari_speech.g2p.version import g2p_version
    from voa_corpus.classify_report import DEFAULT, load, usable
    from voa_corpus.measure import UNITS

    rows = load(DEFAULT)
    vocab = lowercase_words(line for r in rows for line in r["raw"]["text"])
    pronounce, unit = Pronouncer(G2pEnBackend()).pronounce, dict(UNITS)[UNIT]
    pool = [
        c
        for r in rows
        if usable(r) and UNIT in r["units"]
        for c in candidates(r, vocab, pronounce, bool(unit.search(r["title"])))
    ]
    picked = select(pool)
    records = [
        {"source": c.source, "line": c.line, "start": c.start, "unit": UNIT, "text": c.text}
        | {"words": c.words, "g2p_version": g2p_version()}
        for c in picked
    ]
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), "utf-8")
    print(f"{len(pool)} candidates, {len(picked)} picked -> {OUT}")


if __name__ == "__main__":
    main()
