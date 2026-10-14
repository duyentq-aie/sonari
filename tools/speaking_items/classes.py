"""`make passage-classes`: one JSON line per passage, keyed by its pinned `Source._id`: type and
deciding rule, safety flags under each rule of classify_report, unit tags, classifier version, and
every sentence of `text` as [line, start, end, practicable] by pick.practicable. The content
service stores it as is (content/passages.py). Runs in the speech service's environment (G2P);
read-only. Demo: `ARGS="--only tools/speaking_items/sources.jsonl --out <its classes.jsonl>"`.
"""

import argparse
import json
from pathlib import Path
from typing import Any

from voa_corpus.classify_report import DEFAULT, RULES, flags, load
from voa_corpus.trim import rules_version

from speaking_items.pick import SENTENCE, lowercase_words, practicable

HERE = Path(__file__).parent
CORPUS = HERE.parent / "voa_corpus"
DECIDING = [CORPUS / "classify.py", CORPUS / "safety.tsv", CORPUS / "units.tsv"]


def classifier_version(g2p: str) -> str:
    """A digest of every file that decides a field, plus the G2P version the marks rest on."""
    digest = rules_version([*DECIDING, HERE / "pick.py"]).removeprefix("voa-trim/")
    return f"voa-classify/{digest}+{g2p}"


def record(row: dict[str, Any], marks: list[list[Any]], version: str) -> dict[str, Any]:
    return {
        "source": f"voa:{row['id']}@{row['raw']['trim']['rules_version']}",
        "type": row["type"],
        "type_rule": row["rule"],
        "safety_flags": {rule: sorted(flags(row, rule)) for rule in RULES},
        "units": row["units"],
        "classifier_version": version,
        "sentences": marks,
    }


def main() -> None:
    from sonari_speech.g2p import G2pEnBackend, Pronouncer
    from sonari_speech.g2p.version import g2p_version

    parser = argparse.ArgumentParser()
    parser.add_argument("--only", type=Path, help="a trimmed file: keep only its passages")
    parser.add_argument("--out", type=Path, default=DEFAULT.with_name("classes.jsonl"))
    args = parser.parse_args()
    rows = load(DEFAULT)  # the whole corpus: `plain` reads the corpus's own word counts
    vocab = lowercase_words(line for r in rows for line in r["raw"]["text"])
    pronounce, version = Pronouncer(G2pEnBackend()).pronounce, classifier_version(g2p_version())
    if args.only:
        keep = {json.loads(line)["url"] for line in args.only.read_text("utf-8").splitlines()}
        rows = [r for r in rows if r["raw"]["url"] in keep]
    out = []
    for row in rows:
        marks = [
            [n, m.start(), m.end(), bool(practicable(m.group(), vocab, pronounce))]
            for n, line in enumerate(row["raw"]["text"])
            for m in SENTENCE.finditer(line)
        ]
        out.append(record(row, marks, version))
    args.out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in out), "utf-8")
    print(f"{len(out)} passages, {sum(m[3] for r in out for m in r['sentences'])} practicable")


if __name__ == "__main__":
    main()
