"""`make gloss-lock` and `make gloss-eval`.

lock: every pair of gold.tsv has the owner's gloss, then its SHA-256 goes to gold.sha256.
eval: refuses unless gold.tsv still matches that hash (the gold set cannot move after a model answer
is seen), then asks the model once per pair and writes runs/<prompt>-<model>-<time>.tsv: the owner's
gloss beside the model's, the automatic checks (checks.py), model, tokens, latency and cost, and an
empty `review` column the owner fills by hand (agree / partly / disagree). No model judges a gloss.
"""

import argparse
import hashlib
import time
from pathlib import Path

from opentelemetry.sdk.trace import TracerProvider
from voa_corpus import wordlist

from glosses.checks import CHECKS, check
from glosses.provider import Fake, OpenAICompatible, Provider
from glosses.targets import COLUMNS, GOLD, HERE
from glosses.telemetry import chat, tracer_provider

LOCK, RUNS, PROMPT = HERE / "gold.sha256", HERE / "runs", HERE / "prompts/v1.md"
OUT = ["pair", "word", "sentence", "my_gloss", "model_gloss", "model_explanation", *CHECKS,
       "error", "model", "tokens_in", "tokens_out", "latency_ms", "cost_usd", "review"]  # fmt: skip


def read_gold(path: Path = GOLD) -> list[dict[str, str]]:
    header, *rows = [line.split("\t") for line in path.read_text("utf-8").splitlines() if line]
    if header != COLUMNS or any(len(r) != len(COLUMNS) for r in rows):
        raise SystemExit(f"{path}: expected {len(COLUMNS)} tab-separated columns {COLUMNS}")
    return [dict(zip(COLUMNS, r, strict=True)) for r in rows]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lock(gold: Path = GOLD, lock_file: Path = LOCK) -> None:
    empty = [r["pair"] for r in read_gold(gold) if not r["my_gloss"].strip()]
    if empty:
        raise SystemExit(f"no my_gloss yet for pair(s) {', '.join(empty)}")
    lock_file.write_text(f"{digest(gold)}  {gold.name}\n")


def load_prompt(path: Path = PROMPT) -> tuple[str, str, str]:
    text = path.read_text("utf-8")
    system, user = text.split("=== user ===\n")
    return system.strip(), user, f"{path.stem}/{hashlib.sha256(text.encode()).hexdigest()[:12]}"


def run(llm: Provider, tracer: TracerProvider, table: dict[str, int], gold: Path = GOLD,
        lock_file: Path = LOCK, out_dir: Path = RUNS) -> Path:  # fmt: skip
    if not lock_file.exists() or lock_file.read_text().split()[0] != digest(gold):
        raise SystemExit(f"{gold.name} is not locked as it stands: fill it, then `make gloss-lock`")
    system, template, version = load_prompt()
    rows = [OUT]
    for g in read_gold(gold):
        user = template.replace("{sentence}", g["sentence"]).replace("{word}", g["word"])
        call = chat(tracer.get_tracer("glosses"), llm, system, user, version)
        reply = call.reply
        answer, ok = (
            check(reply.text, g["word"], table) if reply else (None, dict.fromkeys(CHECKS, False))
        )
        answer = answer or {"gloss": "", "explanation": reply.text if reply else ""}
        rows.append([g["pair"], g["word"], g["sentence"], g["my_gloss"], answer["gloss"],
                     answer["explanation"], *(str(ok[c]).lower() for c in CHECKS), call.error,
                     reply.model if reply else llm.model, str(reply.tokens_in if reply else 0),
                     str(reply.tokens_out if reply else 0), str(call.latency_ms),
                     f"{reply.cost_usd:.6f}" if reply else "0", ""])  # fmt: skip
    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    path = out_dir / f"{version.replace('/', '-')}-{llm.model.replace('/', '_')}-{stamp}.tsv"
    clean = [[" ".join(f.split()) for f in row] for row in rows]  # no tab or newline in a cell
    path.write_text("".join("\t".join(r) + "\n" for r in clean), "utf-8")
    body = rows[1:]
    print(f"{len(body)} pairs, prompt {version}, model {llm.model} -> {path}")
    for n, c in enumerate(CHECKS, 6):
        print(f"  {c}: {sum(r[n] == 'true' for r in body)}/{len(body)}")
    cost, tokens = sum(float(r[-2]) for r in body), sum(int(r[-5]) + int(r[-4]) for r in body)
    print(f"  tokens {tokens}, cost ${cost:.4f}, errors {sum(bool(r[10]) for r in body)}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["lock", "eval"])
    parser.add_argument("--fake", action="store_true", help="the fake provider: a dry run, no API")
    parser.add_argument("--wordlists", type=Path, default=Path.home() / ".cache/sonari/wordlists")
    args = parser.parse_args()
    if args.command == "lock":
        return lock()
    llm = Fake({}) if args.fake else OpenAICompatible.from_env()
    tracer = tracer_provider()
    try:
        run(llm, tracer, wordlist.load(args.wordlists))
    finally:
        tracer.shutdown()  # flush the spans to Langfuse before exit


if __name__ == "__main__":
    main()
