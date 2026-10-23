"""`make gloss-gold`: the B1-B2 words of the sentences /v1/passages serves, and the gold set.

Served = what `content/passages.py` lists for the reading unit: a usable type, no safety flag under
the default rule, practicable sentences only (classes file of `make passage-classes`). A word is a
token of the sentence that `voa_corpus.measure.token_class` puts at B1 or B2 of CEFR-J 1.5, so
proper nouns and acronyms (judged by capitals) are out. A word is its lowercase spelling, so an
inflected form is its own word; the level lookup is approximate ("found" is read as the B2 headword,
not as "find"). `pos` is nltk's tag in the sentence, a hint with errors. The gold set never holds
model output (see README.md).
"""

import argparse
import json
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from voa_corpus import measure, wordlist
from voa_corpus.classify import USABLE_TYPES

HERE = Path(__file__).parent
GOLD = HERE / "gold.tsv"
UNIT, DEFAULT_RULE = "Study and work", "default"  # apps/web READING_UNIT; passages.DEFAULT_RULE
B1, B2 = wordlist.LEVELS.index("B1"), wordlist.LEVELS.index("B2")
SEED, SIZE, MULTI_WORDS = 20261023, 40, 10  # MULTI_WORDS words give 2 pairs each (gold())
POS = {"N": "noun", "V": "verb", "J": "adj", "R": "adv"}
# The owner's columns sit beside the sentence and never last: an empty last cell is trailing
# whitespace, which the pre-commit hook strips.
COLUMNS = ["pair", "word", "sentence", "my_gloss", "note", "level", "pos", "sentence_id"]


@dataclass(frozen=True)
class Pair:
    word: str  # lowercase, as written in the sentence
    level: str
    pos: str
    sentence_id: str  # <Source._id>#<line>:<start>, the id apps/web gives the sentence
    sentence: str  # cut from the stored text at the stored marks, never edited


def served(classes: Path, trimmed: Path) -> list[tuple[str, str]]:
    """(sentence_id, sentence) of every practicable sentence of every served passage."""
    texts = {}
    for line in trimmed.read_text("utf-8").splitlines():
        r = json.loads(line)
        number = r["url"].rsplit("/", 1)[-1].removesuffix(".html")
        texts[f"voa:{number}@{r['trim']['rules_version']}"] = r["text"]
    out = []
    for line in classes.read_text("utf-8").splitlines():
        c = json.loads(line)
        if c["type"] in USABLE_TYPES and not c["safety_flags"][DEFAULT_RULE] and UNIT in c["units"]:
            text = texts[c["source"]]
            out += [
                (f"{c['source']}#{n}:{s}", text[n][s:e]) for n, s, e, ok in c["sentences"] if ok
            ]
    return out


def pairs(sentences: list[tuple[str, str]], wordlist_dir: Path) -> list[Pair]:
    import nltk  # the speech environment's nltk and tagger data (g2p_en uses both)
    from sonari_speech.g2p.backend import default_nltk_dir

    nltk.data.path.insert(0, str(default_nltk_dir()))
    measure.STATE["table"] = wordlist.load(wordlist_dir)
    out: dict[tuple[str, str], Pair] = {}
    for sid, sentence in sentences:
        tokens = measure.TOKEN.findall(sentence)
        for i, (token, tag) in enumerate(nltk.pos_tag(tokens)):
            level = measure.token_class(token, i == 0)
            if level in (B1, B2) and (token.lower(), sid) not in out:
                pos = POS.get(tag[0], "other")
                out[token.lower(), sid] = Pair(
                    token.lower(), wordlist.LEVELS[level], pos, sid, sentence
                )
    return list(out.values())


CONTEXTS = (lambda p: p.pos, lambda p: p.sentence_id.split("#")[0], lambda p: p.sentence_id)


def gold(found: list[Pair], seed: int = SEED, size: int = SIZE) -> list[Pair]:
    """Senses cannot be told apart here, so MULTI_WORDS words seen in more than one sentence give
    two pairs as far apart as the data allows: two tags, else two passages, else two sentences
    (words with two tags first, then words in two passages). Then one pair per other word, B1 and
    B2 alternating, until `size`. Deterministic for a seed and an input."""
    rng = random.Random(seed)
    by_word: dict[str, list[Pair]] = defaultdict(list)
    for p in sorted(found, key=lambda p: (p.word, p.sentence_id)):
        by_word[p.word].append(p)

    def apart(ps: list[Pair]) -> int:  # 0: two tags, 1: two passages, 2: two sentences
        return next(n for n, key in enumerate(CONTEXTS) if len({key(p) for p in ps}) > 1)

    multi = sorted(w for w, ps in by_word.items() if len(ps) > 1)
    ranked = sorted(multi, key=lambda w: (apart(by_word[w]), rng.random()))
    picked: list[Pair] = []
    for word in ranked[: min(MULTI_WORDS, size // 2)]:
        key = CONTEXTS[apart(by_word[word])]
        groups: dict[str, list[Pair]] = defaultdict(list)
        for p in by_word[word]:
            groups[key(p)].append(p)
        picked += [rng.choice(groups[g]) for g in rng.sample(sorted(groups), 2)]
    rest = {lv: [w for w in sorted(by_word) if w not in multi and by_word[w][0].level == lv]
            for lv in ("B1", "B2")}  # fmt: skip
    for words in rest.values():
        rng.shuffle(words)
    while len(picked) < size and (rest["B1"] or rest["B2"]):
        level = "B1" if (len(picked) % 2 == 0 and rest["B1"]) or not rest["B2"] else "B2"
        picked.append(rng.choice(by_word[rest[level].pop()]))
    return picked


def write_gold(picked: list[Pair], path: Path = GOLD) -> None:
    rows = [COLUMNS] + [
        [str(n), p.word, p.sentence, "", "", p.level, p.pos, p.sentence_id]
        for n, p in enumerate(picked, 1)
    ]
    assert not any("\t" in f or "\n" in f for row in rows for f in row)
    path.write_text("".join("\t".join(row) + "\n" for row in rows), "utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--classes", type=Path, default=Path.home() / "sonari-trimmed/voa/classes.jsonl"
    )
    parser.add_argument(
        "--trimmed", type=Path, default=Path.home() / "sonari-trimmed/voa/trimmed.jsonl"
    )
    parser.add_argument("--wordlists", type=Path, default=Path.home() / ".cache/sonari/wordlists")
    args = parser.parse_args()
    sentences = served(args.classes, args.trimmed)
    found = pairs(sentences, args.wordlists)
    passages = len({sid.split("#")[0] for sid, _ in sentences})
    print(f"{len(sentences)} practicable sentences in {passages} passages of unit {UNIT!r}")
    print(f"{len({p.word for p in found})} distinct B1-B2 words, {len(found)} word-sentence pairs")
    if GOLD.exists():
        raise SystemExit(f"{GOLD} exists: it may hold your glosses; delete it to draw again")
    picked = gold(found)
    write_gold(picked)
    print(f"{len(picked)} pairs -> {GOLD} (seed {SEED})")


if __name__ == "__main__":
    main()
