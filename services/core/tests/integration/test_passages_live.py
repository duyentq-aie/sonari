"""Passage classes on the real MongoDB (`make infra`), as the `core` user: ingest outcomes, the
check against the pinned Source, and both loaders, which a pure test cannot show.

Article numbers are ones no real VOA page has; everything a test writes is deleted after.
"""

import random
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from pymongo import AsyncMongoClient

from sonari_core import content
from sonari_core.content.ingest import ingest_sources, passage_from_record
from sonari_core.content.models import Source
from sonari_core.content.passages import PassageClass, PassageClassRecord
from sonari_core.content.passages_ingest import ingest_classes, source_problems
from sonari_core.content.passages_router import load_passage, load_passages
from sonari_core.shared.errors import AppError
from source_fakes import BASE_ARTICLE, BODY, VERSION_A, VERSION_B, make_record

NOW = datetime(2026, 10, 14, 1, 0, tzinfo=UTC)
UNIT = "Test unit"  # no real passage carries it, so a list holds only what a test stored


def classes(article: int, version: str = VERSION_A, **changes: Any) -> PassageClassRecord:
    fields = {
        "source": f"voa:{article}@{version}", "type": "explainer", "type_rule": "default",
        "safety_flags": {"default": []}, "units": [UNIT], "classifier_version": "voa-classify/a",
        "sentences": [[0, 0, len(BODY[0]), True], [1, 0, len(BODY[1]), False]],
    }  # fmt: skip
    return PassageClassRecord.model_validate(fields | changes)


@pytest_asyncio.fixture
async def articles(core_mongo_uri: str) -> AsyncIterator[list[int]]:
    """Two stored Sources; they and their classes are deleted after."""
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(core_mongo_uri, tz_aware=True)
    await content.SPEC.init(client)
    numbers = random.sample(range(BASE_ARTICLE, BASE_ARTICLE + 9_000_000), 2)
    await ingest_sources([passage_from_record(make_record(n)) for n in numbers], NOW)
    yield numbers
    for n in numbers:
        await PassageClass.find({"_id": {"$regex": f"^voa:{n}@"}}).delete()
        await Source.find({"source_id": f"voa:{n}"}).delete()
    await client.close()


async def test_ingest_inserts_keeps_replaces_on_a_new_version_and_refuses_a_conflict(
    articles: list[int],
) -> None:
    first = classes(articles[0])
    assert (await ingest_classes([first], NOW)).inserted == 1
    assert (await ingest_classes([first], NOW)).unchanged == 1
    same_version = classes(articles[0], type="news_item")
    assert (await ingest_classes([same_version], NOW)).conflicts == [first.source]
    newer = classes(articles[0], type="news_item", classifier_version="voa-classify/b")
    assert (await ingest_classes([newer], NOW)).superseded == 1
    stored = await PassageClass.get(first.source)
    assert stored is not None and stored.type == "news_item"


async def test_a_record_must_pin_a_stored_source_and_fit_its_lines(articles: list[int]) -> None:
    missing = classes(articles[0], VERSION_B)
    too_long = classes(articles[1], sentences=[[0, 0, 999, True]])
    problems = await source_problems([classes(articles[0]), missing, too_long])
    assert len(problems) == 2
    assert "is not in content.sources" in problems[0] and "outside the text" in problems[1]


async def test_the_loaders_serve_only_listable_passages_and_cut_their_lines(
    articles: list[int],
) -> None:
    listed, flagged = articles
    hidden = classes(flagged, safety_flags={"default": ["crime"]})
    await ingest_classes([classes(listed), hidden], NOW)

    passages = await load_passages(UNIT)
    assert [p.id for p in passages] == [f"voa:{listed}@{VERSION_A}"]
    with pytest.raises(AppError) as refused:
        await load_passage(hidden.source)
    assert refused.value.status_code == 404

    detail = await load_passage(passages[0].id)
    source = await Source.get(passages[0].id)
    assert source is not None
    assert ["".join(s.text for s in line) for line in detail.lines] == source.text
    assert [s.practicable for s in detail.lines[0]] == [True]
    assert [s.practicable for s in detail.lines[1]] == [False]
