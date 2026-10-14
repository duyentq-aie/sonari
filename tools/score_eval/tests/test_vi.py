"""Part 2 report on synthetic dumps and scores: notes, order, matching, counts, the verdict."""

import json
import os
from pathlib import Path
from typing import Any

import pytest
from score_eval import vi


def ph(expected: str, gop: float) -> dict[str, Any]:
    return {"expected": expected, "gop": gop, "heard": "y"}


def word(text: str, *phonemes: tuple[str, float]) -> dict[str, Any]:
    return {"text": text, "us": [ph(e, g) for e, g in phonemes], "gb": None, "weak": []}


def clip(*words: dict[str, Any]) -> dict[str, Any]:
    return {"speech_s": 1.0, "words": list(words)}


# "I think so": /θ/ at -5.5 is wrong under v1 (-3.4) and v2 (-5.0); /k/ at -4.0 only under v1.
THINK_PHONEMES = (("θ", -5.5), ("ɪ", 1.0), ("ŋ", 1.0), ("k", -4.0))  # noqa: RUF001
THINK = clip(word("I", ("aɪ", 2.0)), word("think", *THINK_PHONEMES))  # noqa: RUF001
NORMAL = clip(word("so", ("s", 1.0), ("oʊ", -1.0)), word("valued", *[(p, -6.0) for p in "vælj"]))


def test_notes_take_normal_and_error_lines_and_skip_comments() -> None:
    notes = vi.parse_notes("# take 1\nnormal\n\nerror Think θ   # said tink\n")
    assert [(n.kind, n.word, n.phoneme, n.line) for n in notes] == [
        ("normal", "", "", 2),
        ("error", "think", "θ", 4),
    ]


@pytest.mark.parametrize("line", ["error think", "wrong", "normal extra", "error a b c"])
def test_a_malformed_line_stops_with_its_number(line: str) -> None:
    with pytest.raises(SystemExit, match="notes line 2"):
        vi.parse_notes(f"normal\n{line}\n")


def dump(root: Path, name: str, mtime_ns: int) -> Path:
    d = root / name
    d.mkdir()
    (d / "request.json").write_text(json.dumps({"referenceText": "I think so"}), "utf-8")
    (d / "audio.webm").write_bytes(b"x")
    os.utime(d / "request.json", ns=(mtime_ns, mtime_ns))
    return d


def test_recordings_sort_by_time_then_by_write_order_within_one_second(tmp_path: Path) -> None:
    late = dump(tmp_path, "20261014T010203-aaaaaaaa", 3)
    first = dump(tmp_path, "20261014T010202-ffffffff", 9)
    second = dump(tmp_path, "20261014T010203-00000000", 5)
    (tmp_path / "stray").mkdir()  # no request.json: not a recording
    assert vi.recordings(tmp_path) == [first, late, second]


def test_counts_that_differ_stop_the_run(tmp_path: Path) -> None:
    dirs = [dump(tmp_path, "20261014T010202-aaaaaaaa", 1)]
    with pytest.raises(SystemExit, match="1 recordings but 2 notes"):
        vi.pair(dirs, vi.parse_notes("normal\nnormal"))


def test_a_note_naming_a_word_or_phoneme_the_sentence_lacks_stops_the_run() -> None:
    for note, message in (("error thing θ", "no word 'thing'"), ("error think ð", "/ð/ not in")):
        (n,) = vi.parse_notes(note)
        with pytest.raises(SystemExit, match=message):
            vi.summarise([(n, THINK)], -5.0)


def test_summary_counts_the_target_apart_from_other_wrongs_and_normal_deviations() -> None:
    error, normal = vi.parse_notes("error think θ\nnormal")
    v1 = vi.summarise([(error, THINK), (normal, NORMAL)], -3.4)
    assert (v1["caught"], v1["other_wrong"]) == (1, 1)  # /k/ at -4.0
    v2 = vi.summarise([(error, THINK), (normal, NORMAL)], -5.0)
    assert (v2["caught"], v2["other_wrong"]) == (1, 0)
    assert dict(v2["deviations"]) == {"correct": 1, "unclear": 1, "wrong": 4}
    assert v2["word_failures"] == ["valued"]


def test_an_error_scored_unclear_is_not_caught() -> None:
    (error,) = vi.parse_notes("error think k")
    assert vi.summarise([(error, THINK)], -5.0)["caught"] == 0


def summary(errors: int, caught: int, normal: int, wrong: int) -> dict[str, Any]:
    deviations = {"wrong": wrong, "unclear": 0, "correct": 0}
    return {"errors": errors, "caught": caught, "normal": normal, "deviations": deviations}


def test_verdict_rule() -> None:
    assert vi.verdict(summary(10, 8, 20, 20)).startswith("FIT")
    assert vi.verdict(summary(10, 7, 20, 0)).startswith("NOT FIT")
    assert vi.verdict(summary(10, 10, 20, 21)).startswith("NOT FIT")
    assert vi.verdict(summary(0, 0, 20, 0)).startswith("CANNOT TELL")
    assert vi.verdict(summary(5, 5, 0, 0)).startswith("CANNOT TELL")


def test_main_rescores_from_audio_and_prints_both_versions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dump(tmp_path, "20261014T010202-aaaaaaaa", 1)
    dump(tmp_path, "20261014T010203-aaaaaaaa", 1)
    (tmp_path / "20261014T010202-aaaaaaaa" / "response.json").write_text("not read", "utf-8")
    notes = tmp_path / "notes.txt"
    notes.write_text("error think θ\nnormal\n", "utf-8")

    async def fake(pairs: list[tuple[Path, vi.Note]]) -> tuple[list[Any], list[str]]:
        assert [n.kind for _, n in pairs] == ["error", "normal"]
        return [(pairs[0][1], THINK), (pairs[1][1], NORMAL)], []

    monkeypatch.setattr(vi, "score_all", fake)
    monkeypatch.setattr("sys.argv", ["vi", "--dump", str(tmp_path), "--notes", str(notes)])
    vi.main()
    out = capsys.readouterr().out
    assert "| v1 | 1 of 1 | 1 |" in out and "| v2 | 1 of 1 | 0 |" in out
    assert "4 / 1 / 1 in 1" in out and "NOT FIT" in out  # 4 wrong in one normal reading
