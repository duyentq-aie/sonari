# listen_audio

The "listen" audio of the 20 practice sentences: each read by Kokoro-82M in an American and a
British voice, generated offline and committed as static files of the web app
(`apps/web/public/listen/`, 40 MP3 files, 1.1 MB). No TTS runs in any service, and the speech
service's image gets no new weights.

    make listen-audio                                    # regenerate (about 80 s on 12 cores)
    make score-listen SPEECH_URL=http://localhost:8201   # verdicts from a running speech service

- **Model:** `hexgrad/Kokoro-82M` at revision `f3ff3571791e39611d31c381e3a41a3af07b4987`; every
  file read (weights, config, both voice packs) is pinned by size and SHA-256 in `kokoro.yaml`,
  and `synth.py` refuses a file that differs. Voices: `us` = `af_heart`, `gb` = `bf_emma`;
  speed 1.0. Format: MP3, mono, 24 kHz, 48 kbit/s (plays in every current browser, Safari too).
- **Manifest:** `apps/web/public/listen/manifest.json`, one entry per file: item id, voice, file,
  model revision, and the SHA-256 of the item's text. `tests/test_manifest.py` fails when an item
  lacks a voice or its text no longer matches the hash, so a changed sentence cannot keep stale
  audio: rerun `make listen-audio`.
- **Licences:** Kokoro-82M weights and voice packs: Apache-2.0 (model card on Hugging Face). The
  generator uses `kokoro` (Apache-2.0) and `misaki` (MIT) for G2P, which falls back to espeak-ng
  (GPL-3.0, run as a separate program; its licence does not reach the output). The output audio
  carries no licence restriction from the model; its text is VOA staff writing (public domain,
  ADR-0006), credited with the passage.

## How the scorer hears it (synthetic speech, not a person)

`make score-listen` on 2026-10-14, thresholds v2 (`v2-native-s20261008-val20261009`), each MP3
decoded to WAV first (the service takes no MP3):

| voice | wrong | unclear | correct | phonemes | wrong words |
| --- | --- | --- | --- | --- | --- |
| us (`af_heart`) | 0 | 43 | 741 | 784 | none |
| gb (`bf_emma`) | 1 | 46 | 736 | 783 | laboratory |

This is machine speech scored by a model trained on human speech: it says the audio matches the
references closely, not that it sounds natural or teaches well. No threshold changes because of
it. Quality by ear is still the owner's (`spikes/tts/CHECKLIST.md`).
