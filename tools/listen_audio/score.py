"""Scores every "listen" file with a running speech service's POST /v1/score and counts verdicts.

    make score-listen SPEECH_URL=http://localhost:8201

The service takes no MP3, so each file is decoded to WAV first (the audio the browser plays).
The audio is synthetic speech: these counts say how the scorer treats Kokoro, not a speaker. They
are reported in README.md and change no threshold.
"""

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import httpx

OUT = Path(__file__).parents[2] / "apps/web/public/listen"
ITEMS = Path(__file__).parents[2] / "tools/speaking_items/items.jsonl"


def main(url: str) -> None:
    items = [json.loads(line) for line in ITEMS.read_text("utf-8").splitlines() if line]
    texts = {f"{i['source']}#{i['line']}:{i['start']}": i["text"] for i in items}
    manifest = json.loads((OUT / "manifest.json").read_text("utf-8"))
    counts: dict[str, Counter[str]] = {}
    version = ""
    for entry in manifest["files"]:
        cmd = ["ffmpeg", "-loglevel", "error", "-i", str(OUT / entry["file"]), "-f", "wav", "-"]
        audio = subprocess.run(cmd, capture_output=True, check=True).stdout
        form = {"referenceText": texts[entry["item"]]}
        files = {"audio": ("a.wav", audio)}
        reply = httpx.post(f"{url}/v1/score", data=form, files=files, timeout=60)
        reply.raise_for_status()
        body = reply.json()
        version = body["thresholdsVersion"]
        tally = counts.setdefault(entry["voice"], Counter())
        tally.update(p["verdict"] for w in body["words"] for p in w["phonemes"])
        wrong = [w["text"] for w in body["words"] if w["verdict"] == "wrong"]
        tally.update({f"wrong word: {text}" for text in wrong})
    print(f"thresholds {version}; synthetic speech (Kokoro-82M), not a person")
    for voice, c in counts.items():
        total = c["wrong"] + c["unclear"] + c["correct"]
        print(f"{voice} ({manifest['voices'][voice]}): wrong {c['wrong']} / unclear {c['unclear']}"
              f" / correct {c['correct']} of {total} phonemes")  # fmt: skip
        words = ", ".join(k for k in sorted(c) if k.startswith("wrong word"))
        print("  " + (words or "no wrong word"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8001")
