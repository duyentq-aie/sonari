"""Offline: synthesise every speaking item with Kokoro-82M, one American and one British voice.

    make listen-audio      (runs in spikes/tts's environment: torch and kokoro, CPU)

Writes apps/web/public/listen/<sha256(item id)[:16]>-<voice>.mp3 (mono, 24 kHz, 48 kbit/s MP3,
which every browser plays) and manifest.json, one entry per file: item id, voice, model revision,
and the SHA-256 of the item's text, so tests/test_manifest.py fails when a sentence changes and
its audio does not. Every model file is checked against kokoro.yaml before it is read.
"""

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from huggingface_hub import hf_hub_download
from kokoro import KModel, KPipeline

HERE = Path(__file__).parent
ROOT = HERE.parents[1]
ITEMS = ROOT / "tools/speaking_items/items.jsonl"
OUT = ROOT / "apps/web/public/listen"
RATE, BITRATE = 24000, "48k"


def item_id(item: dict[str, Any]) -> str:
    """SpeakingItem.key in services/core/.../content/speaking.py."""
    return f"{item['source']}#{item['line']}:{item['start']}"


def file_name(iid: str, voice: str) -> str:
    return f"{hashlib.sha256(iid.encode()).hexdigest()[:16]}-{voice}.mp3"


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def pinned(pins: dict[str, Any], name: str) -> str:
    path = hf_hub_download(pins["repo"], name, revision=pins["revision"])
    want = pins["files"][name]
    data = Path(path).read_bytes()
    if len(data) != want["size"] or hashlib.sha256(data).hexdigest() != want["sha256"]:
        raise SystemExit(f"{name}: size or SHA-256 differs from kokoro.yaml; refusing it")
    return path


def mp3(audio: np.ndarray) -> bytes:
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    cmd = ["ffmpeg", "-loglevel", "error", "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", "-"]
    cmd += ["-codec:a", "libmp3lame", "-b:a", BITRATE, "-map_metadata", "-1", "-f", "mp3", "-"]
    return subprocess.run(cmd, input=pcm, capture_output=True, check=True).stdout


def main() -> None:
    pins = yaml.safe_load((HERE / "kokoro.yaml").read_text("utf-8"))
    paths = {name: pinned(pins, name) for name in pins["files"]}
    model = KModel(config=paths["config.json"], model=paths["kokoro-v1_0.pth"]).eval()
    items = [json.loads(line) for line in ITEMS.read_text("utf-8").splitlines() if line]
    OUT.mkdir(parents=True, exist_ok=True)
    entries = []
    for key, voice in pins["voices"].items():
        pipeline = KPipeline(lang_code=voice["lang"], repo_id=pins["repo"], model=model)
        pack = paths[f"voices/{voice['name']}.pt"]
        for item in items:
            chunks = [r.audio.numpy() for r in pipeline(item["text"], voice=pack, speed=1.0)]
            name = file_name(item_id(item), key)
            (OUT / name).write_bytes(mp3(np.concatenate(chunks)))
            entry = {"item": item_id(item), "voice": key, "file": name}
            entry |= {"modelRevision": pins["revision"], "textSha256": text_hash(item["text"])}
            entries.append(entry)
    manifest = {
        "model": pins["repo"],
        "modelRevision": pins["revision"],
        "voices": {key: v["name"] for key, v in pins["voices"].items()},
        "files": sorted(entries, key=lambda e: (e["item"], e["voice"])),
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")
    print(f"{len(entries)} files -> {OUT}")


if __name__ == "__main__":
    main()
