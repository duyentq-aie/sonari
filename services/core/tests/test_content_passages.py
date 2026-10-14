"""Passages: the stored classification's checks, the line cutting, and both routes over HTTP with
the database replaced. tests/integration/test_passages_live.py runs ingest and the loaders on
the real MongoDB."""

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from fakes import AppFactory
from sonari_core.content.passages import PassageClassRecord, listable
from sonari_core.content.passages_ingest import load_classes
from sonari_core.content.passages_router import (
    PassageDetail,
    PassageOut,
    Segment,
    load_passage,
    load_passages,
    segments,
)
from sonari_core.shared.errors import AppError
from sonari_core.shared.message_keys import MessageKey

ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = ROOT / "packages/contracts/schema"
DEMO = ROOT / "tools/speaking_items"
ID = "voa:123@voa-trim/aaaaaaaaaaaa"
PASSAGE = PassageOut(id=ID, title="Study tips", type="explainer", url="https://x/a/123.html")
LINE = "A short one. Students who sleep well learn more in class. Done"
DETAIL = PassageDetail(
    **PASSAGE.model_dump(),
    lines=[segments(LINE, [(0, 12, False), (13, 57, True)]), segments("", [])],
)


def schema(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((SCHEMAS / name).read_text("utf-8")))


def record(**changes: Any) -> dict[str, Any]:
    fields = {
        "source": ID, "type": "explainer", "type_rule": "default", "units": ["Study and work"],
        "safety_flags": {"strict": [], "default": [], "loose": ["crime"]},
        "classifier_version": "voa-classify/x+g2p/y",
        "sentences": [[0, 0, 12, False], [0, 13, 57, True]],
    }  # fmt: skip
    return fields | changes


def test_a_record_needs_the_default_rule_and_sentences_in_order_and_apart() -> None:
    PassageClassRecord.model_validate(record())
    for bad in (
        record(safety_flags={"strict": []}),
        record(sentences=[[0, 13, 57, True], [0, 0, 12, False]]),
        record(sentences=[[0, 0, 20, False], [0, 13, 57, True]]),
        record(sentences=[[0, 5, 5, True]]),
    ):
        with pytest.raises(ValidationError):
            PassageClassRecord.model_validate(bad)


def test_a_line_is_cut_at_its_practicable_sentences_and_joins_back() -> None:
    cut = segments(LINE, [(0, 12, False), (13, 57, True)])
    assert cut == [
        Segment(text="A short one. ", practicable=False),
        Segment(text="Students who sleep well learn more in class.", practicable=True),
        Segment(text=" Done", practicable=False),
    ]
    assert "".join(s.text for s in cut) == LINE
    assert segments(LINE, [(0, 12, False)]) == [Segment(text=LINE, practicable=False)]
    assert segments("", []) == []


def test_only_explainers_and_news_items_with_no_default_flag_are_listed() -> None:
    assert listable("Study and work") == {
        "type": {"$in": ["explainer", "news_item"]},
        "safety_flags.default": {"$size": 0},
        "units": "Study and work",
    }
    assert "units" not in listable()


def client(
    make_app: AppFactory, passages: list[PassageOut], detail: PassageDetail | None
) -> TestClient:
    seen: list[str] = []

    async def many(unit: str) -> list[PassageOut]:
        seen.append(unit)
        return passages

    async def one(passage_id: str) -> PassageDetail:
        seen.append(passage_id)
        if detail is None or passage_id != detail.id:
            raise AppError(404, "passage_not_found", MessageKey.NOT_FOUND)
        return detail

    app = make_app()
    app.dependency_overrides[load_passages] = many
    app.dependency_overrides[load_passage] = one
    test_client = TestClient(app, raise_server_exceptions=False)
    test_client.seen = seen  # type: ignore[attr-defined]
    return test_client


def test_the_list_answers_for_a_unit_and_matches_the_contract(make_app: AppFactory) -> None:
    http = client(make_app, [PASSAGE], DETAIL)
    response = http.get("/v1/passages", params={"unit": "Study and work"})
    assert response.status_code == 200
    assert response.json() == {"passages": [PASSAGE.model_dump()]}
    schema("passages-response.schema.json").validate(response.json())
    assert http.seen == ["Study and work"]  # type: ignore[attr-defined]


def test_the_list_needs_a_unit(make_app: AppFactory) -> None:
    response = client(make_app, [], None).get("/v1/passages")
    assert response.status_code == 422
    assert response.json()["error"]["messageKey"] == "errors.validation"


def test_a_passage_by_its_encoded_id_matches_the_contract(make_app: AppFactory) -> None:
    response = client(make_app, [], DETAIL).get(f"/v1/passages/{quote(ID, safe='')}")
    assert response.status_code == 200
    schema("passage-response.schema.json").validate(response.json())
    assert [s["practicable"] for s in response.json()["lines"][0]] == [False, True, False]


def test_an_unknown_or_unlisted_passage_is_not_found(make_app: AppFactory) -> None:
    response = client(make_app, [], DETAIL).get("/v1/passages/voa%3A999%40voa-trim%2Fx")
    assert response.status_code == 404
    assert response.json()["error"]["messageKey"] == "errors.not_found"


def test_the_demo_classes_load_and_every_sentence_lies_in_its_seeded_source() -> None:
    records = load_classes(DEMO / "classes.jsonl")
    texts = {}
    for line in (DEMO / "sources.jsonl").read_text("utf-8").splitlines():
        raw = json.loads(line)
        number = raw["url"].rsplit("/", 1)[-1].removesuffix(".html")
        texts[f"voa:{number}@{raw['trim']['rules_version']}"] = raw["text"]
    assert {r.source for r in records} == set(texts)
    for r in records:
        assert all(end <= len(texts[r.source][n]) for n, _, end, _ in r.sentences), r.source
