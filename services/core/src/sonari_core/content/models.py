"""Models of the content database: the validated passage, and the Beanie document that stores it.

The ADR-0008 checks run where a file enters (`TrimmedPassage`, `Trim`), never on read. A stored
version is immutable (ADR-0010), so a rule tightened later must not stop it from loading: `Source`
and its `trim` keep the shape (`PassageRecord`, `StoredTrim`) without the rule checks.
"""

from datetime import datetime
from typing import ClassVar, Self

from beanie import Document
from pydantic import BaseModel, Field, model_validator
from pymongo import ASCENDING, IndexModel

from sonari_core.content.trim_rules import (
    MAX_FK,
    MAX_WORDS,
    MIN_WORDS,
    TRIM_CAP,
    count_words,
    editorial_words,
)


class RemovedLine(BaseModel):
    """One line a trim took out of the original (ADR-0008 decision 3)."""

    index: int  # 0-based, into `original_text`
    kind: str = Field(min_length=1)
    rule: str = Field(min_length=1)  # the rule that removed it, so a reader can audit the call
    text: str


class StoredTrim(BaseModel):
    """`trim` as stored: the shape only. `Trim` adds the ADR-0008 checks for a file coming in."""

    rules_version: str = Field(min_length=1)
    cap: float  # ADR-0008 decision 2: always `TRIM_CAP`; a file does not choose its own
    removed_words: int  # editorial words only; page furniture does not count against the cap
    removed_share: float  # `removed_words` over the original's words, to 4 places
    removed: list[RemovedLine]


class Trim(StoredTrim):
    @model_validator(mode="after")
    def _the_cap_is_the_adr_s_and_the_cut_is_what_the_lines_say(self) -> Self:
        if self.cap != TRIM_CAP:
            raise ValueError(f"ADR-0008 decision 2: trim.cap is {self.cap}, the cap is {TRIM_CAP}")
        derived = editorial_words((line.kind, line.text) for line in self.removed)
        if self.removed_words != derived:
            raise ValueError(
                f"ADR-0008 decision 2: trim.removed_words is {self.removed_words}, but the "
                f"removed lines hold {derived} words that count (furniture does not, decision 1)"
            )
        return self


class PassageRecord(BaseModel):
    """One passage of English source text as one rules version trimmed it: the fields only.
    `TrimmedPassage` checks them where a file enters; `Source` stores them."""

    source_id: str  # `voa:<article number>`: the passage, whatever version of its trim this is
    url: str
    title: str
    program: str = ""  # empty when the page names none
    fk: float  # Flesch-Kincaid grade of `text`, the trimmed lines; below `MAX_FK`
    # Words of the ORIGINAL, the denominator of `trim.removed_share`. It is the corpus's count of
    # `original_text`, so the validator derives it and refuses a file that declares another.
    original_words: int
    original_text: list[str]  # the lines as the parser returned them, untouched
    text: list[str]  # `original_text` minus `trim.removed`, byte for byte
    trim: StoredTrim

    @property
    def key(self) -> str:
        """Identity of this version of the passage: also its `_id` once stored (ADR-0010)."""
        return f"{self.source_id}@{self.trim.rules_version}"


class TrimmedPassage(PassageRecord):
    """A line of the trimmed corpus, checked the way ADR-0008 asks: a trim removes whole lines
    and nothing else, within the cap, the length window and the grade ceiling. It needs no
    database, so a file is validated before anything is written. `Source` is the stored form."""

    trim: Trim

    @model_validator(mode="after")
    def _text_is_the_original_minus_the_removed_lines(self) -> Self:
        gone = [line.index for line in self.trim.removed]
        if len(set(gone)) != len(gone):
            raise ValueError("a line is recorded as removed twice")
        for line in self.trim.removed:
            if not 0 <= line.index < len(self.original_text):
                raise ValueError(f"removed index {line.index} is outside the original")
            if self.original_text[line.index] != line.text:
                raise ValueError(f"removed line {line.index} is not the original line")
        kept = [text for index, text in enumerate(self.original_text) if index not in set(gone)]
        if self.text != kept:
            raise ValueError("text is not the original lines minus the removed ones")
        return self

    @model_validator(mode="after")
    def _the_cut_is_within_the_cap_by_the_lines_and_not_by_the_file(self) -> Self:
        """The cap is a share of the original's words, so both sides of it are derived."""
        words = count_words(self.original_text)
        if self.original_words != words:
            raise ValueError(
                f"ADR-0008 decision 2: original_words is {self.original_words}, "
                f"but original_text has {words} words"
            )
        if words == 0:
            raise ValueError("ADR-0008 decision 2: the passage has no words, so none can be cut")
        cut = self.trim.removed_words  # `Trim` has already checked it against the lines
        if self.trim.removed_share != round(cut / words, 4):
            raise ValueError(
                f"ADR-0008 decision 2: trim.removed_share is {self.trim.removed_share}, "
                f"but {cut} of {words} words is {round(cut / words, 4)}"
            )
        if cut > TRIM_CAP * words:
            raise ValueError(
                f"ADR-0008 decision 2: the trim cut {cut} of {words} words, "
                f"over the cap of {TRIM_CAP:.0%}"
            )
        return self

    @model_validator(mode="after")
    def _the_trimmed_text_is_in_the_window_and_below_the_grade_ceiling(self) -> Self:
        words = count_words(self.text)
        if not MIN_WORDS <= words <= MAX_WORDS:
            raise ValueError(
                f"ADR-0008 decision 2: the trimmed text has {words} words, "
                f"outside {MIN_WORDS}-{MAX_WORDS}"
            )
        if not self.fk < MAX_FK:  # written so that a NaN fails it too
            raise ValueError(f"ADR-0008 decision 2: fk is {self.fk}, not below {MAX_FK:g}")
        return self


class Source(PassageRecord, Document):
    """A stored version of a passage. Every rules version is its own immutable document;
    exactly one version of a passage is `current` (ADR-0010). Everything downstream reads
    `text`; `original_text` and `trim` let the trim be audited and undone. Read as stored: the
    ADR-0008 checks ran when the version came in, and are not repeated on read."""

    id: str  # type: ignore[assignment]  # `key`, so dev and prod hold the same ids
    current: bool
    ingested_at: datetime

    class Settings:
        name = "sources"
        # The one query that needs an index: "the current version of this passage". The
        # partial unique index is also what guarantees there is never a second one.
        # `_id` serves lookups of a pinned version. Nothing else is indexed: a filter on `fk`
        # or `original_words` scans a few hundred current sources faster than an index pays.
        indexes: ClassVar[list[IndexModel]] = [
            IndexModel(
                [("source_id", ASCENDING)],
                name="source_id_current",
                unique=True,
                partialFilterExpression={"current": True},
            )
        ]

    @classmethod
    async def get_current(cls, source_id: str) -> Self | None:
        return await cls.find_one({"source_id": source_id, "current": True})
