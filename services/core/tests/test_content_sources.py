"""The trimmed VOA corpus as validated passages. No database here: the write-time checks of
ADR-0008 and the identity scheme of ADR-0010 are pure."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from sonari_core.content import models
from sonari_core.content.ingest import (
    InvalidCorpus,
    load_passages,
    passage_from_record,
    voa_source_id,
)
from sonari_core.content.models import PassageRecord
from source_fakes import BASE_ARTICLE, VERSION_A, make_record, url_of, write_corpus

Record = dict[str, Any]


def test_the_article_number_is_the_identity_whatever_the_title_slug() -> None:
    plain = voa_source_id(url_of(1630766))
    slugged = voa_source_id(url_of(1630766, slug="women-kept-guitars-strumming-during-wwii"))

    assert plain == slugged == "voa:1630766"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/a/1630766.html",  # not VOA Learning English
        "http://learningenglish.voanews.com/a/1630766.html",  # a scheme the crawler never writes
        "https://learningenglish.voanews.com/a/not-a-number.html",
        "https://learningenglish.voanews.com/z/1630766/",  # not an article page
    ],
)
def test_a_url_that_is_not_a_voa_article_is_refused(url: str) -> None:
    with pytest.raises(ValueError, match="not a VOA Learning English article"):
        voa_source_id(url)


def test_a_record_becomes_a_passage_that_keeps_every_provenance_field() -> None:
    record = make_record(BASE_ARTICLE)

    passage = passage_from_record(record)

    assert passage.source_id == f"voa:{BASE_ARTICLE}"
    assert passage.key == f"voa:{BASE_ARTICLE}@{VERSION_A}"
    assert (passage.url, passage.title, passage.program, passage.fk) == (
        record["url"],
        record["title"],
        record["program"],
        record["fk"],
    )
    assert passage.original_text == record["original_text"]
    assert passage.text == record["text"]
    assert passage.trim.rules_version == VERSION_A
    assert passage.trim.cap == 0.05
    assert passage.trim.removed_words == record["trim"]["removed_words"]
    assert passage.trim.removed_share == record["trim"]["removed_share"]
    assert [line.model_dump() for line in passage.trim.removed] == record["trim"]["removed"]


def test_words_is_stored_as_original_words_because_it_counts_the_untrimmed_page() -> None:
    # `words` in the corpus is the denominator of removed_share: the original's editorial
    # words. The name `words` would suggest it describes `text`, which it does not.
    record = make_record(BASE_ARTICLE)

    passage = passage_from_record(record)

    assert passage.original_words == record["words"]
    assert "words" not in passage.model_dump()


def test_a_passage_that_was_not_trimmed_has_nothing_removed() -> None:
    record = make_record(BASE_ARTICLE, remove=())

    passage = passage_from_record(record)

    assert passage.text == passage.original_text
    assert passage.trim.removed == []


def drop_a_kept_line(r: Record) -> None:
    r["text"] = r["text"][1:]


def edit_a_kept_line(r: Record) -> None:
    r["text"][0] += "!"  # ADR-0008: a kept line is byte-identical to VOA's


def reorder_the_kept_lines(r: Record) -> None:
    r["text"].reverse()


def claim_a_line_that_is_not_the_original(r: Record) -> None:
    r["trim"]["removed"][0]["text"] = "Something VOA never wrote."


def record_a_line_as_removed_twice(r: Record) -> None:
    r["trim"]["removed"].append(dict(r["trim"]["removed"][0]))


def remove_a_line_outside_the_original(r: Record) -> None:
    r["trim"]["removed"][0]["index"] = 999


def cut_more_than_the_cap(r: Record) -> None:
    # A real 8% cut with every declared number consistent, so only the cap can refuse it.
    r.clear()
    r.update(make_record(BASE_ARTICLE, remove=(0, 1, 2, 3, 4, -1)))


def lose_the_rules_version(r: Record) -> None:
    r["trim"]["rules_version"] = ""


def lose_the_rule_of_a_removed_line(r: Record) -> None:
    r["trim"]["removed"][0]["rule"] = ""


def carry_a_field_the_schema_does_not_know(r: Record) -> None:
    r["byline"] = "VOA Learning English"  # would be dropped silently, losing provenance


@pytest.mark.parametrize(
    "damage",
    [
        drop_a_kept_line,
        edit_a_kept_line,
        reorder_the_kept_lines,
        claim_a_line_that_is_not_the_original,
        record_a_line_as_removed_twice,
        remove_a_line_outside_the_original,
        cut_more_than_the_cap,
        lose_the_rules_version,
        lose_the_rule_of_a_removed_line,
        carry_a_field_the_schema_does_not_know,
    ],
)
def test_a_record_that_breaks_adr_0008_is_refused(damage: Callable[[Record], None]) -> None:
    record = make_record(BASE_ARTICLE)
    damage(record)

    with pytest.raises(ValueError):  # pydantic's ValidationError is a ValueError
        passage_from_record(record)


def test_load_passages_returns_one_passage_per_line(tmp_path: Path) -> None:
    records = [make_record(BASE_ARTICLE + n) for n in range(3)]

    passages = load_passages(write_corpus(tmp_path, records))

    assert [p.source_id for p in passages] == [f"voa:{BASE_ARTICLE + n}" for n in range(3)]


def test_a_file_that_is_not_the_one_its_manifest_describes_is_refused(tmp_path: Path) -> None:
    path = write_corpus(tmp_path, [make_record(BASE_ARTICLE + n) for n in range(3)])
    path.write_bytes(path.read_bytes().replace(b"Test passage", b"Edited passage"))

    with pytest.raises(InvalidCorpus, match=r"MANIFEST\.json"):
        load_passages(path)


def test_a_corpus_with_no_manifest_is_still_read(tmp_path: Path) -> None:
    path = write_corpus(tmp_path, [make_record(BASE_ARTICLE)], manifest=False)

    assert len(load_passages(path)) == 1


def test_every_bad_record_is_reported_before_any_passage_is_returned(tmp_path: Path) -> None:
    good, bad_one, bad_two = (make_record(BASE_ARTICLE + n) for n in range(3))
    drop_a_kept_line(bad_one)
    cut_more_than_the_cap(bad_two)

    with pytest.raises(InvalidCorpus) as error:
        load_passages(write_corpus(tmp_path, [good, bad_one, bad_two]))

    assert [problem.split(":")[0] for problem in error.value.problems] == ["line 2", "line 3"]


def test_one_article_twice_in_a_file_is_refused_because_two_versions_cannot_both_be_current(
    tmp_path: Path,
) -> None:
    records = [make_record(BASE_ARTICLE), make_record(BASE_ARTICLE, "voa-trim/bbbbbbbbbbbb")]

    with pytest.raises(InvalidCorpus, match=r"line 2.*appears twice"):
        load_passages(write_corpus(tmp_path, records))


# A rule tightened after a version was stored: what ADR-0008 allowed then, it refuses now.
TIGHTER = [("MAX_FK", 4.0), ("TRIM_CAP", 0.04), ("MAX_WORDS", 300)]  # the fake: fk 4.2, 480 words


@pytest.mark.parametrize(("rule", "tighter"), TIGHTER)
def test_a_tighter_rule_refuses_the_file_but_not_the_stored_shape(
    monkeypatch: pytest.MonkeyPatch, rule: str, tighter: float
) -> None:
    record = make_record(BASE_ARTICLE + 7)
    stored = passage_from_record(record).model_dump()
    monkeypatch.setattr(models, rule, tighter)

    with pytest.raises(ValueError, match="ADR-0008"):
        passage_from_record(record)
    assert PassageRecord.model_validate(stored).key == f"voa:{BASE_ARTICLE + 7}@{VERSION_A}"


def test_source_is_read_with_no_adr_0008_check() -> None:
    assert not issubclass(models.Source, models.TrimmedPassage)
    assert models.Source.model_fields["trim"].annotation is models.StoredTrim
    assert not PassageRecord.__pydantic_decorators__.model_validators
    assert not models.StoredTrim.__pydantic_decorators__.model_validators
