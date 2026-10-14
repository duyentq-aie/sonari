"""`content.passage_classes`: type, safety flags, unit tags and classifier version of one pinned
Source version, plus each sentence of its `text` marked practicable or not. Written offline by
tools/speaking_items/classes.py with pick.practicable and stored as is: the service cannot import
the tools, and G2P lives in the speech service. Source gets no field (its versions are immutable,
ADR-0010), so this sits beside it under the same `_id`; a new classifier version replaces it."""

from datetime import datetime
from typing import Self

from beanie import Document
from pydantic import BaseModel, Field, model_validator

USABLE_TYPES = ("explainer", "news_item")  # voa_corpus.classify.USABLE_TYPES (drift-tested)
DEFAULT_RULE = "default"  # the safety rule a listed passage must pass (classify_report.RULES)


class PassageClassRecord(BaseModel):
    """A line of the classes file: everything that can be checked without a database."""

    source: str = Field(min_length=1)  # the pinned `Source._id`: voa:<article>@<rules_version>
    type: str = Field(min_length=1)
    type_rule: str  # the rule that decided `type`, so a reader can audit it
    safety_flags: dict[str, list[str]]  # rule -> flagged categories
    units: list[str]
    classifier_version: str = Field(min_length=1)
    sentences: list[tuple[int, int, int, bool]]  # line, start, end, practicable

    @model_validator(mode="after")
    def _the_sentences_are_in_order_and_apart(self) -> Self:
        if DEFAULT_RULE not in self.safety_flags:
            raise ValueError(f"no safety flags under the {DEFAULT_RULE!r} rule")
        last = (-1, 0)
        for line, start, end, _ in self.sentences:
            if not (0 <= start < end and (line, start) >= last):
                raise ValueError(f"sentence {line}:{start}-{end}: empty, overlapping or unordered")
            last = (line, end)
        return self


class PassageClass(PassageClassRecord, Document):
    id: str  # type: ignore[assignment]  # `source`
    ingested_at: datetime

    class Settings:
        name = "passage_classes"  # a few hundred documents: a scan beats an index


def listable(unit: str | None = None) -> dict[str, object]:
    """The filter a passage a learner may read passes: an explainer or a news item with no
    safety flag under the default rule (and, given one, tagged for `unit`)."""
    query: dict[str, object] = {"type": {"$in": list(USABLE_TYPES)}}
    query[f"safety_flags.{DEFAULT_RULE}"] = {"$size": 0}
    return query | ({"units": unit} if unit is not None else {})
