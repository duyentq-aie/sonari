# sonari-speech

Speech service: reference text to expected phonemes (P21), audio decoding and the phoneme
model (P20), then alignment and GOP scoring. No torch: onnxruntime and numpy only.

## Runtime (P20)

`SpeechRuntime.analyse(upload_bytes)` is what the scoring endpoint (P23) calls:

1. **Decode** (`runtime/audio.py`): ffmpeg turns WebM/Opus (Chrome), Ogg/Opus (Firefox),
   MP4/AAC (Safari, iPhone) and WAV into 16 kHz mono float32. The container is recognised from
   its first bytes and forced with `-f`, only the `file` protocol is allowed, and decoding
   stops one second past the limit. Over 5 MB: 413; not audio: 415; over 15 s: 422.
2. **Trim** (`runtime/vad.py`): energy-based, relative to the clip's own noise floor, keeps
   150 ms either side. Under 0.3 s of speech: 422 `errors.audio.too_short`.
3. **Infer** (`runtime/model.py`): the int8 wav2vec2 model, one shared onnxruntime session
   with one intra-op thread per request, returns log-posteriors `[frames, 392]` (20 ms each).
4. **Gate** (`runtime/gate.py`): at most `slots` requests run at once, at most
   `in_flight_limit` are admitted; the next gets 503 + `Retry-After` at once, not a long queue.

The model and G2P load in background tasks. `/healthz` answers at once; `/readyz` is 503 until
the file's SHA-256 matched `runtime/models.yaml`, the session loaded and a warm-up inference
ran, until G2P loaded (`g2p` check), and while ffmpeg cannot be started. A model that fails to load keeps the process up and not
ready (the reason is in the log).

| Variable | Default | Meaning |
|---|---|---|
| `SPEECH_MODEL_DIR` | `$DATA_DIR/onnx` (`/models` in the image) | holds `wav2vec2_int8.onnx` |
| `SPEECH_CORES` | CPUs usable by the process, capped by the container quota | inference slots, up to the in-flight limit |
| `SPEECH_MAX_IN_FLIGHT` | from BENCH.md: 1 core 2, 2 cores 5, 4+ cores 7 (never the core count) | running + waiting; explicit override |
| `SPEECH_INTRA_OP_THREADS` | 1 | as measured in BENCH.md |
| `SPEECH_RETRY_AFTER_S` | 2 | value of `Retry-After` |

The capacity table is the **laptop's** (BENCH.md, "Limits"); re-measure on the VPS and set
`SPEECH_MAX_IN_FLIGHT`.

### The model file

int8, as decided for P20 (BENCH.md: keeps the G0 verdict, about 2x faster on CPU). G1 is
calibrated on exactly this file, so it is pinned by SHA-256 in `runtime/models.yaml` and a
different file is never loaded.

```bash
uv run python -m sonari_speech.runtime.weights --dir ~/sonari-data/onnx   # fetch + verify
uv run python -m sonari_speech.runtime.weights --check                    # verify only
SPEECH_MODEL_URL=https://... uv run python -m sonari_speech.runtime.weights   # only this URL
```

`url` in `models.yaml` lists the mirrors in order. The first is the model's Hugging Face repo,
pinned to a commit ([model card](https://huggingface.co/duyentq/sonari-wav2vec2-phoneme-int8));
a Cloudflare R2 mirror is a TODO there. The fetcher keeps the first mirror whose download matches
the pinned size and SHA-256, skips one that is down or serves another file, and fails when none
matches. Fetching from Hugging Face took 14 s on the laptop (355,352,992 bytes). A CI check
(`scripts/tests/test_models_manifest.py`) fails when an entry has a null, empty or placeholder
`url`.

### Image

```bash
docker build -t sonari-speech services/speech                    # no model inside
docker build --build-arg MODEL_URL=https://... -t sonari-speech services/speech
docker run --rm --cpus 2 -p 8001:8001 -v ~/sonari-data/onnx:/models:ro sonari-speech
```

Measured 2026-10-03 on the laptop (WSL2, i5-11400H; the VOA crawl was running, the model
file was in the page cache), after `g2p-en` joined the dependencies. The Dockerfile has since
started fetching the NLTK cmudict at build time (2026-10-07, not yet rebuilt or re-measured):

| | |
|---|---|
| Image size | 1.1 GB (ffmpeg layer 464 MB, Python env 202 MB), model not included |
| Cold start | 2.5-3.3 s from `docker run` to `/readyz` 200 (SHA-256 check, load, warm-up 168 ms) |
| Memory at idle | 583 MiB (int8, `--cpus 2`) |
| One clip | 150-165 ms for decode + trim + inference of a 0.8 s clip |

The log shows the capacity in use: `model ready: cores=2 slots=2 in_flight_limit=5`; on 12 cores
`cores=12 slots=7 in_flight_limit=7` (12 at once measured p95 2.08 s, over the 2 s target).

## Reference pronunciation (P21)

```python
from sonari_speech.g2p import G2pEnBackend, Pronouncer

pronouncer = Pronouncer(G2pEnBackend())  # loads g2p_en once, about 2 s
pronouncer.pronounce("I don't think so")
# -> one WordPron per word: text, start/end span in the reference, ARPAbet,
#    espeak tokens, and where they came from (lexicon, dictionary, contraction, predicted, number)
```

Lookup order per word: `g2p/lexicon.yaml` (overrides) → CMUdict → stem plus clitic for
contractions CMUdict lacks → g2p_en's neural guess. Digits are read out ("24" is one word
for the UI, "twenty four" for the model). ARPAbet becomes espeak tokens through
`phoneset/arpabet_to_espeak.yaml` (the P03 table, moved here from `spikes/gop`).

- A sentence takes 0.1-0.2 ms when every word is in CMUdict, about 1 ms per unknown word (the
  neural guess); measured 2026-10-03 on the laptop, budget 10 ms.
- Homographs ("read", "live") take CMUdict's first variant; there is no POS disambiguation.
- Adding a lexicon entry: give `arpabet`, the `espeak` tokens espeak-ng gives and a `why`; the
  tests check that the table maps the first to the second.

### NLTK data

The backend needs the `cmudict` corpus in `$DATA_DIR/nltk_data` (default `~/sonari-data`).
It never downloads at runtime: it raises `G2pDataMissing`, and importing g2p_en runs with
`nltk.download` disabled. Fetch it once, at build time:

```bash
uv run --directory services/speech python -m sonari_speech.g2p.backend
```

## Scoring (P22, part of P23): `POST /v1/score`

Multipart `audio` (any format above) and `referenceText` (1-300 characters). The response is
`packages/contracts/schema/score-response.schema.json`: per word, per expected phoneme,
`verdict` (correct / unclear / wrong), `heard` (what the model rated highest instead, when not
correct), `gop` and the time span; per word, the worse verdict and the `reference` accent used.

1. G2P turns the reference into espeak tokens per word: en-us (g2p_en), en-gb
   (`g2p/espeak.py`, espeak-ng, which must be installed), and, for a closed list of ten function
   words, their weak and strong forms (`g2p/weak_forms.yaml`, each with its source); the runtime
   gives log-posteriors.
2. `scoring/align.py` force-aligns the WHOLE sentence (CTC Viterbi, from spikes/gop/align.py),
   once per reference over the same posteriors; `scoring/accents.py` keeps the best per word.
3. `scoring/gop.py` scores each phoneme as P02 did; `scoring/thresholds/v2.yaml` says correct
   above 0, wrong below −5.0, unclear between, and how −5.0 was chosen and validated; read that file.

Dev only: `SPEECH_DEBUG_DUMP_DIR=<dir>` keeps every request's audio, referenceText and response
(`scoring/dump.py`); refused inside a container, never set in the image.

Each wrong phoneme (not an unclear one) also carries `feedback`: a message key (`pronunciation.fix.<rule>`) and
parameters, never text. `scoring/feedback.py` picks the rule from `scoring/feedback.yaml`, which
also lists the sources and the pairs that have none; the Vietnamese copy is the client's, in
`apps/web/messages/vi.json`. No LLM is involved.

Speech too short to hold the sentence: 422 `audio_too_short` with
`details.reason = "shorter_than_reference"`. Align + GOP take 2-16 ms; the model is the cost.
Per-phoneme output on the G0 clips: `uv run pytest -rP tests/scoring/test_g0_clips.py`.

## Running the tests

```bash
make test-speech
```

It takes about 8 s with everything below available (the budget is 10 s) and about 4 s in CI. A
test that needs something this machine lacks skips, so a bare checkout still passes:

| Missing | Skipped | Where it comes from |
|---|---|---|
| `ffmpeg` | the audio decode and upload tests | the CI speech job installs it; with `CI` set, a missing `ffmpeg` fails instead of skipping |
| `cmudict` in `$DATA_DIR/nltk_data` | 35 tests on the real g2p backend | `python -m sonari_speech.g2p.backend` (see "NLTK data"); CI uses the copy vendored in `tests/data/` (licence and checksums in `tests/data/README.md`) and, with `CI` set, fails instead of skipping |
| `wav2vec2_int8.onnx` in `SPEECH_MODEL_DIR` | 4 tests on the real model | `python -m sonari_speech.runtime.weights` (see "The model file") |

**The 4 real-model tests still skip in CI, on purpose.** They need the 355 MB model file, and CI
does not download it: that would add a 355 MB transfer to every run (14 s on the laptop, more on a
runner). They run on a developer machine that has the file. To run them in CI, fetch it with
`actions/cache` keyed on the pinned SHA-256 (backlog). Everything else in CI runs against fakes,
the vendored dictionary or the real stack. The audio fixtures in `tests/fixtures/` are synthetic
re-encodings, not device recordings (see `generate.py`).
