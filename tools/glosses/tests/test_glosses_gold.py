"""Served sentences, the gold draw and the gold file: filters, determinism, senses, no prefill."""

import json
from pathlib import Path

import pytest
from glosses import targets
from glosses.targets import COLUMNS, Pair, gold, served, write_gold

SOURCE = "voa:111@voa-trim/aaaaaaaaaaaa"


def classes_line(source: str, **change: object) -> str:
    record = {
        "source": source,
        "type": "explainer",
        "units": ["Study and work"],
        "safety_flags": {"default": []},
        "sentences": [[0, 0, 9, True], [0, 10, 21, False]],
    }
    return json.dumps(record | change)


def test_served_keeps_practicable_sentences_of_listable_passages_cut_exactly(
    tmp_path: Path,
) -> None:
    trimmed = tmp_path / "trimmed.jsonl"
    rows = [(n, "Go there. Not this one.") for n in ("111", "222", "333", "444")]
    trim = {"rules_version": "voa-trim/aaaaaaaaaaaa"}
    records = [{"url": f"https://x/a/slug/{n}.html", "text": [t], "trim": trim} for n, t in rows]
    trimmed.write_text("".join(json.dumps(r) + "\n" for r in records))
    classes = tmp_path / "classes.jsonl"
    classes.write_text("\n".join([
        classes_line(SOURCE),
        classes_line("voa:222@voa-trim/aaaaaaaaaaaa", type="dialogue_script"),
        classes_line("voa:333@voa-trim/aaaaaaaaaaaa", safety_flags={"default": ["crime"]}),
        classes_line("voa:444@voa-trim/aaaaaaaaaaaa", units=["Sport"]),
    ]))  # fmt: skip
    assert served(classes, trimmed) == [(f"{SOURCE}#0:0", "Go there.")]


def pair(word: str, level: str, pos: str, n: int, source: str = SOURCE) -> Pair:
    return Pair(word, level, pos, f"{source}#{n}:0", f"Sentence {n} with {word}.")


FOUND = [
    *(pair(f"multi{i}", "B1", pos, 10 * i + k) for i in range(12)
      for k, pos in enumerate(["noun", "verb", "noun"])),
    *(pair(f"bone{i}", "B1", "noun", 500 + i) for i in range(30)),
    *(pair(f"btwo{i}", "B2", "adj", 600 + i) for i in range(30)),
]  # fmt: skip


def test_the_draw_is_fixed_by_its_seed_and_changes_with_it() -> None:
    assert gold(FOUND) == gold(list(reversed(FOUND)))
    assert gold(FOUND) != gold(FOUND, seed=1)


def test_a_word_seen_in_two_parts_of_speech_gives_one_pair_in_each() -> None:
    picked = gold(FOUND)
    multi = [p for p in picked if p.word.startswith("multi")]
    assert len(multi) == 2 * targets.MULTI_WORDS
    for word in {p.word for p in multi}:
        assert sorted(p.pos for p in multi if p.word == word) == ["noun", "verb"]


def test_two_tags_come_first_then_two_passages_then_two_sentences() -> None:
    found = [
        pair("same", "B1", "noun", 1), pair("same", "B1", "noun", 2),
        pair("apart", "B1", "noun", 3), pair("apart", "B1", "noun", 4, "voa:9@v"),
        pair("tagged", "B1", "noun", 5), pair("tagged", "B1", "verb", 6),
    ]  # fmt: skip
    picked = gold(found, size=4)
    assert [p.word for p in picked] == ["tagged", "tagged", "apart", "apart"]
    assert {p.sentence_id.split("#")[0] for p in picked[2:]} == {SOURCE, "voa:9@v"}


def test_the_rest_is_one_pair_per_word_alternating_b1_and_b2() -> None:
    picked = gold(FOUND)
    rest = [p for p in picked if not p.word.startswith("multi")]
    assert len(picked) == targets.SIZE and len({p.word for p in rest}) == len(rest)
    assert [p.level for p in rest] == ["B1", "B2"] * (len(rest) // 2)


def test_the_gold_file_has_empty_gloss_and_note_columns(tmp_path: Path) -> None:
    path = tmp_path / "gold.tsv"
    write_gold(gold(FOUND), path)
    header, *rows = [line.split("\t") for line in path.read_text("utf-8").splitlines()]
    assert header == COLUMNS and len(rows) == targets.SIZE
    assert all(r[COLUMNS.index("my_gloss")] == r[COLUMNS.index("note")] == "" for r in rows)


def test_the_committed_gold_file_is_unfilled_or_owner_written() -> None:
    """Shape only: 40 rows, the sentence at its id. Glosses are the owner's, never generated."""
    rows = [line.split("\t") for line in targets.GOLD.read_text("utf-8").splitlines()][1:]
    assert len(rows) == targets.SIZE
    assert len({r[COLUMNS.index("sentence_id")] + r[1] for r in rows}) == targets.SIZE


def test_pairs_tag_parts_of_speech_and_drop_proper_nouns(tmp_path: Path) -> None:
    pytest.importorskip("nltk")  # the speech environment only
    pytest.importorskip("sonari_speech")
    wordlists = Path.home() / ".cache/sonari/wordlists"
    if not wordlists.exists():
        pytest.skip("make voa-wordlists")
    found = targets.pairs([("s#0:0", "Maria is willing to reduce the secondary costs.")], wordlists)
    assert {(p.word, p.level) for p in found} == {
        ("willing", "B2"),
        ("reduce", "B1"),
        ("secondary", "B2"),
    }
