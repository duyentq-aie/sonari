"""Part 2: `make score-vi DUMP=<dir> NOTES=<file>` (README.md). Each recording is scored again
from its audio under thresholds v1 and v2; response.json is never read. Recordings and notes match
by order; the reference per word is analyse.choose, the copy of scoring/accents.py.
"""

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import Any, NamedTuple

import yaml

from score_eval import analyse as a

THRESHOLDS_DIR = Path(__file__).parents[2] / "services/speech/src/sonari_speech/scoring/thresholds"
# The verdict's rule, fixed before any recording exists (README.md, "Verdict").
MIN_CAUGHT = 0.8  # share of deliberate errors marked wrong under v2
MAX_WRONG_PER_NORMAL = 1.0  # wrong phonemes per normal reading, on average, under v2
HEADER = "| thresholds | deliberate errors marked wrong | other wrong in those recordings | normal readings: wrong / unclear / correct (deviations) | whole-word failures |"  # noqa: E501


class Note(NamedTuple):
    line: int
    kind: str  # "normal" or "error"
    word: str = ""
    phoneme: str = ""


def parse_notes(text: str) -> list[Note]:
    notes = []
    for n, raw in enumerate(text.splitlines(), 1):
        fields = raw.split("#", 1)[0].split()
        if not fields:
            continue
        if fields == ["normal"]:
            notes.append(Note(n, "normal"))
        elif len(fields) == 3 and fields[0] == "error":
            notes.append(Note(n, "error", fields[1].lower(), fields[2]))
        else:
            raise SystemExit(f"notes line {n}: not `normal` or `error <word> <phoneme>`: {raw}")
    return notes


def recordings(dump: Path) -> list[Path]:
    """The dump's request directories, oldest first (name = UTC second, then a random suffix)."""
    dirs = [d for d in dump.iterdir() if (d / "request.json").is_file()]
    return sorted(dirs, key=lambda d: (d.name[:15], (d / "request.json").stat().st_mtime_ns))


def pair(dirs: list[Path], notes: list[Note]) -> list[tuple[Path, Note]]:
    if len(dirs) != len(notes):
        raise SystemExit(f"{len(dirs)} recordings but {len(notes)} notes: fix the notes first")
    return list(zip(dirs, notes, strict=True))


def words_of(clip: dict[str, Any], wrong_below: float) -> list[tuple[str, list[str], list[str]]]:
    out = []
    for word in clip["words"]:
        chosen = a.choose(word, wrong_below)[1]
        verdicts = [a.verdict(p["gop"], wrong_below) for p in chosen]
        out.append((word["text"].lower(), [p["expected"] for p in chosen], verdicts))
    return out


def target(note: Note, scored: list[tuple[str, list[str], list[str]]]) -> tuple[int, int]:
    for i, (text, expected, _) in enumerate(scored):
        if text == note.word:
            if note.phoneme not in expected:
                raise SystemExit(f"notes line {note.line}: /{note.phoneme}/ not in {expected}")
            return i, expected.index(note.phoneme)
    raise SystemExit(f"notes line {note.line}: the sentence has no word {note.word!r}")


def summarise(pairs: list[tuple[Note, dict[str, Any]]], wrong_below: float) -> dict[str, Any]:
    caught, other_wrong, normal, failures = 0, 0, Counter[str](), []
    for note, clip in pairs:
        scored = words_of(clip, wrong_below)
        for text, _, verdicts in scored:
            most = verdicts.count("wrong") > len(verdicts) // 2
            if len(verdicts) >= a.COLLAPSE_MIN_PHONEMES and most:
                failures.append(text)
        if note.kind == "normal":
            normal.update(v for _, _, vs in scored for v in vs)
            continue
        wi, pi = target(note, scored)
        hit = scored[wi][2][pi] == "wrong"
        caught += hit
        other_wrong += sum(v.count("wrong") for _, _, v in scored) - hit
    kinds = Counter(n.kind for n, _ in pairs)
    return {"errors": kinds["error"], "caught": caught, "other_wrong": other_wrong,
            "normal": kinds["normal"], "deviations": normal, "word_failures": failures}  # fmt: skip


def verdict(s: dict[str, Any]) -> str:
    if not s["errors"] or not s["normal"]:
        return "CANNOT TELL: the set needs both deliberate-error and normal recordings"
    caught, per = s["caught"] / s["errors"], s["deviations"]["wrong"] / s["normal"]
    fit = caught >= MIN_CAUGHT and per <= MAX_WRONG_PER_NORMAL
    rule = f"caught {caught:.0%} (need >= {MIN_CAUGHT:.0%}), "
    rule += f"wrong per normal reading {per:.2f} (need <= {MAX_WRONG_PER_NORMAL})"
    return f"{'FIT' if fit else 'NOT FIT'} to show a learner: {rule}"


def render(by_version: dict[str, dict[str, Any]], failed: list[str]) -> str:
    lines = [HEADER, "| --- | --- | --- | --- | --- |"]
    for version, s in by_version.items():
        d, failures = s["deviations"], ", ".join(s["word_failures"]) or "-"
        normal = f"{d['wrong']} / {d['unclear']} / {d['correct']} in {s['normal']}"
        lines.append(f"| {version} | {s['caught']} of {s['errors']} | {s['other_wrong']} | ")
        lines[-1] += f"{normal} | {len(s['word_failures'])}: {failures} |"
    lines += [f"Not scored ({len(failed)}): {', '.join(failed) or 'none'}", ""]
    return "\n".join([*lines, "v2: " + verdict(by_version["v2"])])


async def score_all(pairs: list[tuple[Path, Note]]) -> tuple[list[tuple[Note, Any]], list[str]]:
    from score_eval.score import ClipScorer

    scorer = ClipScorer()
    await scorer.start()
    scored, failed = [], []
    for directory, note in pairs:
        text = json.loads((directory / "request.json").read_text("utf-8"))["referenceText"]
        audio = next(directory.glob("audio*")).read_bytes()
        try:
            scored.append((note, await scorer.score(audio, text)))
        except Exception as err:  # e.g. too short: listed in the report
            failed.append(f"{directory.name} ({type(err).__name__})")
    return scored, failed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump", type=Path, required=True)
    parser.add_argument("--notes", type=Path, required=True)
    args = parser.parse_args()
    pairs = pair(recordings(args.dump), parse_notes(args.notes.read_text("utf-8")))
    scored, failed = asyncio.run(score_all(pairs))
    by_version = {}
    for version in ("v1", "v2"):
        raw = yaml.safe_load((THRESHOLDS_DIR / f"{version}.yaml").read_text("utf-8"))
        if float(raw["correct_above"]) != a.CORRECT_ABOVE:
            raise SystemExit(f"{version}: correct_above differs from analyse.CORRECT_ABOVE")
        by_version[version] = summarise(scored, float(raw["wrong_below"]))
    print(render(by_version, failed))


if __name__ == "__main__":
    main()
