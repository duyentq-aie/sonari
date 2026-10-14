SERVICES := core speech
UV_RUN := uv run --directory

LINT_TARGETS := $(SERVICES:%=lint-%)
TYPECHECK_TARGETS := $(SERVICES:%=typecheck-%)

# Every target is phony (none produces a file of that name).
# NOTE: make skips implicit (%) rule search for phony targets, so per-service targets
# must use static pattern rules ("targets: pattern:"), never a bare "lint-%:" rule;
# otherwise they silently become empty recipes ("Nothing to be done").
.PHONY: setup dev infra infra-reset lint typecheck test test-core test-speech test-scripts \
	test-tools check-phoneset check-imports fmt lint-scripts typecheck-web test-web build-web \
	$(LINT_TARGETS) $(TYPECHECK_TARGETS)

# One-time setup per clone: the pre-commit hook, the pre-merge-commit hook (the same checks on a
# merge commit, which skips pre-commit) and the commit-msg hook (strips AI trailers).
# Git worktrees of the clone share these hooks.
setup:
	uvx pre-commit install
	uvx pre-commit install --hook-type pre-merge-commit
	uvx pre-commit install --hook-type commit-msg

# Local settings. Created once from the example and never overwritten.
.env:
	cp .env.example .env

# MongoDB (single-node replica set rs0) and Redis; returns once both are healthy.
infra: .env
	docker compose up -d --wait

# Stops the stack and deletes its named volumes. Scoped to the compose project "sonari",
# so volumes of other projects are untouched.
infra-reset: .env
	docker compose down --volumes --remove-orphans

# Starts the infra, then the apps in the foreground: core :8000, speech :8001 and the web app
# :3000, which proxies to both. Use `make infra` when you only need the databases (for example
# `make infra && make test-core`).
dev: infra apps/web/node_modules
	@trap 'kill 0' INT TERM; \
	$(UV_RUN) services/core --env-file $(CURDIR)/.env uvicorn sonari_core.main:app_factory --factory --reload --port 8000 & \
	$(UV_RUN) services/speech uvicorn sonari_speech.main:app --reload --port 8001 & \
	NEXT_TELEMETRY_DISABLED=1 CORE_URL=http://localhost:8000 SPEECH_URL=http://localhost:8001 npm run --prefix apps/web dev & \
	wait

# From a fresh clone to the practice page: the speech data, the infra, the demo content, the apps.
# Needs Docker, Node 22, uv, ffmpeg and espeak-ng (README.md, "Run it").
.PHONY: demo
demo: speech-data ingest-demo-sources ingest-speaking-items ingest-demo-classes dev

# The speech service's data, once per machine (needs network, about 360 MB): the int8 model from
# Hugging Face, kept only when its size and SHA-256 match runtime/models.yaml, and the CMUdict
# corpus that g2p_en reads. Both go to DATA_DIR (default ~/sonari-data). ffmpeg and espeak-ng
# come from the system's package manager.
.PHONY: speech-data
speech-data:
	@command -v ffmpeg >/dev/null || { echo "ffmpeg is not installed (apt install ffmpeg)"; exit 1; }
	@command -v espeak-ng >/dev/null || { echo "espeak-ng is not installed (apt install espeak-ng)"; exit 1; }
	$(UV_RUN) services/speech python -m sonari_speech.runtime.weights
	$(UV_RUN) services/speech python -m sonari_speech.g2p.backend

# The web app (apps/web). It needs Node 22 on the machine that runs make: in WSL, install it inside
# the distro (the Windows node and npm do not count). `npm ci` runs again when the lockfile changes.
apps/web/node_modules: apps/web/package-lock.json
	@command -v node >/dev/null || { echo "node is not installed: apps/web needs Node 22 (install it inside WSL)"; exit 1; }
	npm ci --prefix apps/web --no-audit --no-fund
	@touch $@

typecheck-web: apps/web/node_modules
	npm run --prefix apps/web typecheck

test-web: apps/web/node_modules
	npm test --prefix apps/web

build-web: apps/web/node_modules
	NEXT_TELEMETRY_DISABLED=1 npm run --prefix apps/web build

lint: $(LINT_TARGETS) lint-scripts

$(LINT_TARGETS): lint-%:
	$(UV_RUN) services/$* ruff check .
	$(UV_RUN) services/$* ruff format --check .

# ADR-0001 rule 1: fails on any import between bounded contexts. Part of lint-core, so CI
# runs it.
check-imports:
	$(UV_RUN) services/core lint-imports

lint-core: check-imports

lint-scripts:
	uv run --no-project --with ruff ruff check scripts tools spikes
	uv run --no-project --with ruff ruff format --check scripts tools spikes
	uv run --no-project python scripts/check_no_vietnamese.py services scripts tools spikes

typecheck: $(TYPECHECK_TARGETS) typecheck-web

$(TYPECHECK_TARGETS): typecheck-%:
	$(UV_RUN) services/$* mypy

test: test-core test-speech test-scripts test-tools test-web

test-core:
	$(UV_RUN) services/core pytest

# Must stay under 10 s and must not load model weights.
test-speech:
	$(UV_RUN) services/speech pytest

# The ADR-0008 drift tests import the content models to compare them with the tools' trim rules.
# pydantic, beanie and everything they pull in are pinned to the versions the core service locks
# (scripts/locked_pins.py reads services/core/uv.lock), so a release upstream cannot turn CI red
# with no change here, and a pin cannot go stale. The script fails the target if it cannot pin.
test-scripts:
	pins="$$(uv run --no-project python scripts/locked_pins.py pydantic beanie)" && \
	uv run --no-project --with pytest --with pyyaml $$pins pytest -q scripts/tests

# numpy-only tests (tools + spike aligner); neither torch project is installed for these.
test-tools:
	uv run --no-project --with pytest --with numpy --with pyyaml pytest tools spikes/gop/tests

# VOA inventory (P06): a polite, resumable crawl into DATA_DIR/voa_cache, then an offline
# report. The crawl needs VOA_CONTACT_EMAIL (it goes into the User-Agent). Not part of CI.
.PHONY: voa-crawl voa-report voa-sample voa-evaluate voa-corpus voa-trim voa-wordlists voa-missing
.PHONY: voa-classify voa-classify-validate
voa-crawl:
	PYTHONPATH=tools uv run --no-project --with pyyaml python -m voa_inventory.crawl $(ARGS)

voa-report:
	PYTHONPATH=tools uv run --no-project --with pyyaml python -m voa_inventory.report $(ARGS)

# The CEFR word lists of tools/voa_corpus: CEFR-J 1.5 and Octanove C1/C2, pinned to a commit of
# openlanguageprofiles/olp-en-cefrj and checked against tools/voa_corpus/wordlists.sha256. Not
# copied into the repo (the CEFR-J terms say nothing about redistribution).
WORDLIST_DIR ?= $(HOME)/.cache/sonari/wordlists
WORDLIST_URL := https://raw.githubusercontent.com/openlanguageprofiles/olp-en-cefrj/d4e45b75b38f27b30dfc5c44d8c571aec7e7092f
voa-wordlists:
	mkdir -p $(WORDLIST_DIR)
	for f in $$(awk '{print $$2}' tools/voa_corpus/wordlists.sha256); do \
	  [ -f $(WORDLIST_DIR)/$$f ] || curl -fsSL -o $(WORDLIST_DIR)/$$f $(WORDLIST_URL)/$$f; done
	cd $(WORDLIST_DIR) && sha256sum -c $(CURDIR)/tools/voa_corpus/wordlists.sha256

# Measures the whole cached corpus (read only) and rewrites the generated block of
# docs/reports/voa-corpus.md. About 90 s.
voa-corpus: voa-wordlists
	PYTHONPATH=tools uv run --no-project --with pyyaml python -m voa_corpus.analyze --report docs/reports/voa-corpus.md $(ARGS)

# The trimmed corpus (ADR-0008): the passages usable at a 5% cut, each with the lines the
# parser returned, the lines left and every removed line with its rule. Read-only on DATA_DIR; it
# writes $(TRIM_DIR) (default ~/sonari-trimmed/voa). About 90 s.
voa-trim: voa-wordlists
	PYTHONPATH=tools uv run --no-project --with pyyaml python -m voa_corpus.write_trimmed $(ARGS)

# Loads the trimmed corpus into content.sources as the `core` user (ADR-0010). Idempotent: run
# it again after a re-trim to add the new version and make it current. Starts the infra first.
# `make ingest-sources ARGS=--dry-run` reports what would be inserted, superseded or refused and
# writes nothing; it exits 1 on a conflict, like the real run.
SOURCES_FILE ?= $(HOME)/sonari-trimmed/voa/trimmed.jsonl
.PHONY: ingest-sources
ingest-sources: infra
	$(UV_RUN) services/core --env-file $(CURDIR)/.env python $(CURDIR)/scripts/ingest_sources.py $(SOURCES_FILE) $(ARGS)

# Only the 13 passages the 20 practice sentences pin (tools/speaking_items/sources.jsonl, copied
# byte for byte from the trimmed corpus; tests/test_demo_seed.py checks it): a fresh clone needs no
# VOA crawl, which takes about 14 hours. The full corpus ingested later leaves these unchanged.
.PHONY: ingest-demo-sources
ingest-demo-sources: SOURCES_FILE = $(CURDIR)/tools/speaking_items/sources.jsonl
ingest-demo-sources: ingest-sources

# Loads the picked practice sentences into content.speaking_items. Needs `make ingest-sources`
# (or `make ingest-demo-sources`) first. Idempotent: a second run stores nothing twice.
ITEMS_FILE ?= $(CURDIR)/tools/speaking_items/items.jsonl
.PHONY: ingest-speaking-items
ingest-speaking-items: infra
	$(UV_RUN) services/core --env-file $(CURDIR)/.env python $(CURDIR)/scripts/ingest_speaking_items.py $(ITEMS_FILE) $(ARGS)

# What the text-less pages are: the seeded sample's labels (docs/reports/voa-missing-labels.tsv) with
# confidence intervals, and a census of the article text the parser never reads. Read only; about 60 s.
voa-missing:
	PYTHONPATH=tools uv run --no-project --with pyyaml python -m voa_corpus.missing $(ARGS)

# Tags the trimmed corpus by type and topic safety and prints the counts (docs/reports/voa-classify.md).
# Read only on TRIM_DIR, no model, a few seconds. `ARGS=--sample 50` prints the seeded sample to read
# by hand, untagged; `ARGS=--tsv` prints one line per passage. `voa-classify-validate` scores the hand
# labels in docs/reports/voa-classify-labels.tsv.
voa-classify:
	PYTHONPATH=tools uv run --no-project --with pyyaml python -m voa_corpus.classify_report $(ARGS)

# Picks the practice sentences (tools/speaking_items/items.jsonl) from the trimmed corpus; needs the
# speech service's environment for G2P. Read only on the corpus; rewrites the items file.
# Native GOP calibration (docs/reports/score-native-calibration.md): scores a seeded LibriSpeech
# dev-clean sample with the real model (400 utterances, 4 workers: about 4 min), then the tables.
NATIVE_JSONL ?= $(or $(DATA_DIR),$(HOME)/sonari-data)/derived/score_eval/native-20261008-400.jsonl
.PHONY: score-native
score-native:
	PYTHONPATH=$(CURDIR)/tools $(UV_RUN) services/speech --with pyarrow python -m score_eval.native $(ARGS)
	PYTHONPATH=$(CURDIR)/tools uv run --no-project python -m score_eval.report $(NATIVE_JSONL)

# Part 2 (tools/score_eval/README.md): re-scores a SPEECH_DEBUG_DUMP_DIR dump from its audio under
# thresholds v1 and v2, matched by order to a hand-written notes file. Real model; local only.
.PHONY: score-vi
score-vi:
	@test -n "$(DUMP)" -a -n "$(NOTES)" || { echo "usage: make score-vi DUMP=<dir> NOTES=<file>"; exit 1; }
	PYTHONPATH=$(CURDIR)/tools $(UV_RUN) services/speech python -m score_eval.vi --dump $(abspath $(DUMP)) --notes $(abspath $(NOTES))

# The "listen" audio of the practice sentences (tools/listen_audio/README.md): Kokoro-82M, pinned in
# kokoro.yaml, in spikes/tts's environment (torch, CPU; first run downloads about 330 MB). Rewrites
# apps/web/public/listen/. Offline only: no TTS runs in any service.
.PHONY: listen-audio
listen-audio:
	uv run --directory spikes/tts --with pyyaml python $(CURDIR)/tools/listen_audio/synth.py

# Scores every listen file with a running speech service (synthetic speech; README.md reports it).
SPEECH_URL ?= http://localhost:8001
.PHONY: score-listen
score-listen:
	$(UV_RUN) services/speech python $(CURDIR)/tools/listen_audio/score.py $(SPEECH_URL)

# Passage type, safety flags, units and practicable sentences -> ~/sonari-trimmed/voa/classes.jsonl
# (tools/speaking_items/classes.py, about 1 min), then into content.passage_classes (idempotent).
.PHONY: passage-classes ingest-passage-classes ingest-demo-classes
passage-classes:
	PYTHONPATH=$(CURDIR)/tools $(UV_RUN) services/speech python -m speaking_items.classes $(ARGS)

CLASSES_FILE ?= $(HOME)/sonari-trimmed/voa/classes.jsonl
ingest-passage-classes: infra
	$(UV_RUN) services/core --env-file $(CURDIR)/.env python $(CURDIR)/scripts/ingest_passage_classes.py $(CLASSES_FILE) $(ARGS)

ingest-demo-classes: CLASSES_FILE = $(CURDIR)/tools/speaking_items/classes.jsonl
ingest-demo-classes: ingest-passage-classes

.PHONY: speaking-items
speaking-items:
	PYTHONPATH=$(CURDIR)/tools $(UV_RUN) services/speech python -m speaking_items.pick $(ARGS)

voa-classify-validate:
	PYTHONPATH=tools uv run --no-project --with pyyaml python -m voa_corpus.classify_validate $(ARGS)

# Topic-tagger evaluation (needs the owner's labels in tools/voa_inventory/labels/). The
# sample step is cheap; the evaluate step loads bge-m3 (2.3 GB download, ~3 GB RAM).
voa-sample:
	PYTHONPATH=tools uv run --no-project --with pyyaml python -m voa_inventory.sample

voa-evaluate:
	PYTHONPATH=tools uv run python -m voa_inventory.evaluate

# Needs network (model vocab from the Hugging Face hub) and espeak-ng; not part of CI.
check-phoneset:
	$(UV_RUN) spikes/gop python -m phoneset.check_vocab
	$(UV_RUN) spikes/gop python -m phoneset.roundtrip_test

fmt:
	@for s in $(SERVICES); do \
		$(UV_RUN) services/$$s ruff check --fix . && $(UV_RUN) services/$$s ruff format . || exit 1; \
	done
	uv run --no-project --with ruff ruff check --fix scripts tools spikes
	uv run --no-project --with ruff ruff format scripts tools spikes
