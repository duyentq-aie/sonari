"""The classes file: its record shape, its version, and the demo copy agreeing with the picker."""

import json
from pathlib import Path

from speaking_items.classes import classifier_version, record

HERE = Path(__file__).parents[1]


def test_the_version_names_the_deciding_files_digest_and_the_g2p_version() -> None:
    version = classifier_version("g2p/abc")
    assert version.startswith("voa-classify/") and version.endswith("+g2p/abc")
    assert len(version.split("/")[1].split("+")[0]) == 12


def test_a_record_keys_the_pinned_source_and_carries_every_rule_s_flags() -> None:
    row = {
        "id": "123", "type": "explainer", "rule": "default", "units": ["Study and work"],
        "hits": {"crime": (False, 1)}, "raw": {"trim": {"rules_version": "voa-trim/aaaaaaaaaaaa"}},
    }  # fmt: skip
    out = record(row, [[0, 0, 5, True]], "v")
    assert out["source"] == "voa:123@voa-trim/aaaaaaaaaaaa"
    assert out["safety_flags"] == {"strict": [], "default": [], "loose": ["crime"]}
    assert (out["type"], out["type_rule"]) == ("explainer", "default")
    assert out["sentences"] == [[0, 0, 5, True]]


def test_the_demo_file_marks_every_picked_sentence_practicable() -> None:
    marks = {
        (c["source"], line, start): ok
        for c in map(json.loads, (HERE / "classes.jsonl").read_text("utf-8").splitlines())
        for line, start, _, ok in c["sentences"]
    }
    items = [json.loads(x) for x in (HERE / "items.jsonl").read_text("utf-8").splitlines()]
    assert len(items) == 20
    assert all(marks.get((i["source"], i["line"], i["start"])) for i in items)
