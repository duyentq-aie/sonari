"""Every practice sentence has listen audio in both voices, made from the sentence as it is now."""

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[3]
LISTEN = ROOT / "apps/web/public/listen"
MANIFEST = json.loads((LISTEN / "manifest.json").read_text("utf-8"))
PINS = yaml.safe_load((Path(__file__).parents[1] / "kokoro.yaml").read_text("utf-8"))
ITEMS = [
    json.loads(line)
    for line in (ROOT / "tools/speaking_items/items.jsonl").read_text("utf-8").splitlines()
    if line
]
TEXTS = {f"{i['source']}#{i['line']}:{i['start']}": i["text"] for i in ITEMS}


def test_every_item_has_both_voices_and_nothing_else() -> None:
    found = sorted((e["item"], e["voice"]) for e in MANIFEST["files"])
    assert found == sorted((item, voice) for item in TEXTS for voice in PINS["voices"])


def test_the_text_hash_matches_the_item_so_a_changed_sentence_cannot_keep_old_audio() -> None:
    for entry in MANIFEST["files"]:
        text = TEXTS[entry["item"]]
        assert entry["textSha256"] == hashlib.sha256(text.encode()).hexdigest(), entry["item"]


def test_every_file_exists_and_comes_from_the_pinned_model() -> None:
    assert MANIFEST["modelRevision"] == PINS["revision"]
    for entry in MANIFEST["files"]:
        assert entry["modelRevision"] == PINS["revision"]
        assert (LISTEN / entry["file"]).read_bytes()[:2] in (b"ID", b"\xff\xfb", b"\xff\xf3")
    assert {p.name for p in LISTEN.glob("*.mp3")} == {e["file"] for e in MANIFEST["files"]}


def test_the_audio_stays_small_enough_to_commit() -> None:
    assert sum(p.stat().st_size for p in LISTEN.glob("*.mp3")) < 5 * 1024 * 1024
