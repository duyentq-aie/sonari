# Backlog

Ideas parked here are not planned. Moving one into a milestone needs a reason in the
PR description.

- Levels 1–3 and 5–7
- Placement test (needs a second level)
- Roleplay screen B18 (levels 1–3)
- LLM roleplay partner
- Estimated speaking band (gated by QWK ≥ 0.6 vs human raters)
- Leagues
- Agent tutor, MCP server, grammar RAG
- Reading, writing
- Web push reminders (email first)
- Beginner-friendly TTS for levels 1-3: 0.8x alone is not enough. Options, cheapest
  first: try other Kokoro voices; insert 300-500 ms pauses at clause boundaries;
  play each line twice (slow with pauses, then natural). Raised after the P05 spike.
- Topic labels: a second labeller on the same 100 pages (agreement is unmeasured), and a
  stratified top-up sample for topics with fewer than 10 labelled pages, so per-topic
  precision and recall can be reported for them. Raised by the P06 tagger evaluation.
- Part 1 starter (speaking only, no VOA passage): examiner-style questions on hometown,
  home/accommodation and family, which open most IELTS Part 1 tests but have no level 4
  VOA source. Questions are scaffolding under ADR-0006. Raised by
  `docs/level4-units-proposal.md`.
- CI integration tests: add a MongoDB replica-set service to the `core` job so the P11
  transaction and access tests run in CI; today they skip there because CI has no MongoDB.
- MongoDB users for the later processes: `ai-gateway` (owns `tutor`, no user exists yet)
  and `worker` (ADR-0001 does not say which databases it writes). Add them, with the
  matching `.env.example` entries, when those processes are created. Raised by P11.
- Event bus follow-ups (P15): a CLI to inspect and replay `dead.events.*` entries, and
  W3C `traceparent` carried in the stream entry so a consumer span joins the producer's
  trace. Raised by ADR-0007.
- G2P follow-ups (P21): homograph disambiguation ("read", "live"; the backend takes CMUdict's
  first variant, g2p_en would use POS tags); generate `g2p/lexicon.yaml` entries for each
  unit's vocabulary by comparing CMUdict variants with espeak-ng (a probe on 2026-10-03 found
  camera, restaurant, average, every, different); download `cmudict` in CI so the 35 live g2p
  tests run there.
- Hooks in merge commits: #62 installs `pre-merge-commit` (a clean merge now runs every hook). Still open: a merge
  with conflicts runs the pre-commit hooks on the conflicted files only (pre-commit's own rule, "Checking
  merge-conflict files only"), so a Python file that merged cleanly is not linted; CI's `--all-files` covers it.
- Speech runtime follow-ups (P20): a smaller image (the ffmpeg package is 464 MB of 1.1 GB; a
  static ffmpeg build would be about 70 MB); the OpenTelemetry SDK, exporter and FastAPI
  instrumentation for the speech service as core has them (the runtime already creates
  `speech.decode` and `speech.infer` spans through the API), with the first HTTP endpoint
  (P23); real iPhone and Chrome recordings as fixtures instead of the synthetic ones; capacity
  numbers measured on the VPS.
- CI follow-ups (#28): the 4 tests on the real int8 model still skip in CI: `runtime/models.yaml` has
  a URL now, but CI deliberately does not download 355 MB. To run them, fetch it in the speech job with
  `actions/cache` keyed on the pinned SHA-256 (the first run downloads it, later runs restore it).
  If the core job grows (it is 42 s now, 24 s of it starting MongoDB and Redis), cache the mongo and redis
  images, or run only `mongod` for the tests that do not need Redis.
- Add a CI check that fails when any models.yaml entry has a null or empty url.
  PR #26 merged with `url: null`; draft status is a convention, not an
  enforcement.
- Cap PR size going forward. #26 was 38 files / 2392 lines in one commit, past
  the point where review is real. Split prompts by layer, target under 500 lines.
- A Cloudflare R2 mirror of the int8 model, as the second entry of `url` in `runtime/models.yaml` (a
  commented TODO there), so that a Hugging Face outage cannot stop an image build. The fetcher already
  tries the list in order; the CI check rejects a placeholder that is left in.
- Decide whether the parser should read bullet lists in the body. `<li>` text inside `div.wsw` holds 530
  lines (23,763 words) on 309 pages; 124 lines are the same comment-box instructions, the rest are real
  bullet points. The bare-text fix skips lists as instructed (`docs/reports/voa-corpus.md`).
- `has_audio` may be wrong on some old pages: 962 pages (380 passages) have an `.mp3` link in some letter case
  but `has_audio` is false. `parse.MP3` is case-sensitive (`.Mp3` in 2010-2012 pages) and `parse_page` only
  looks inside `#article-content`. Not analysed further; check before relying on `has_audio`.
- Pair the audio-only pages with their text page: 7,700 text-less pages share a title with a passage
  (more by fuzzier matching), so a passage could get its listening audio from the twin page.
- ADR-0008 recall (not planned: the 90% target was withdrawn, `docs/reports/voa-trim-corpus.md`; kept as a
  record of what is left). 57% of the 5% set is free of missed frame. By lines in the round-two sample, with the
  passages that hold one: A closings and
  teasers in plain prose, "Join us again soon for Part 2", "We leave you with ... singing" (22 lines, 19
  passages); B programme blurbs and openers with other wording, "Each week we explore ..." (12, 12); C practice
  or discussion prompts without a channel word, "Practice what you learned today!" (9, 8); D editor or series
  notes, cross-references, page headers (7, 6); E pointers to a video, a song or a page (8, 5). Covering A, B
  and C would give about 89% in the sample (in-sample). A and B read like content in a lesson body, so each
  needs closed anchors (a series name) and the reading of ADR-0008 section 5, and a rule that needs the
  position of the line in the passage is a new idea that the ADR has not weighed.
- Closed versions of rules that had an open slot, if recall is ever wanted back (each needs the evidence of
  ADR-0008 section 5): credits with an explicit list of nouns after "wrote this" (lesson, story, report, ...),
  VITA leaflets by topic, the opener with the programme titles listed, glossary entries as exact sentences. The
  open versions removed 4,568 lines (`docs/reports/voa-trim-corpus.md`).
- A blocking screen for what recall cannot reach: block a passage that has a line with a channel, a programme
  word or a closing phrase left after the rules. About 83-87% clean on the "before" sample (in-sample), at the
  cost of more than a third of the passages. Not adopted; only if cleanliness matters more than the count.
- `make voa-precision`: the sampler and summariser behind `voa-trim-precision.md`, `voa-trim-recall.md` and
  `voa-trim-corpus.md` were one-off scripts (seeds 20261003 to 20261008; populations and strata are in the
  reports). Make them a target
  that draws the samples, writes the TSV to label and prints the counts with exact intervals, so every change
  to the lists can be re-measured. The grade is computed with the lines the rules miss still in, so recompute
  it as recall improves (below grade 7 was 3,253, 3,335, 3,214 and 3,313 passages with the four rule sets).
- Not stored on `Source` (ADR-0010 ingests the trimmed corpus as it is): the "Words in This Story" glossary,
  which the parser splits off, and the credit lines the parser drops before the trim; both are in the cached
  HTML. P50 decides whether they matter.
- `Source` stores no word count of `text`. The service counts it to check the window
  (`trim_rules.count_words`), so a reader that needs the length (P50's filters) can call that. Store a number
  only if a query has to filter on it, which would be a contract change, tools first.
- `SourceIngested` event for the other contexts (ADR-0001: they keep read models, they never query `content`).
  Nothing consumes Sources yet, so none exists; add it with its first consumer.
- `--dry-run` counts a rollback (a stored older version made current again) as `superseded`, like a
  re-trim, because the real run's summary does. To tell them apart, split the outcome in `_decide`
  (`content/ingest.py`), which the run and the plan both ask.
- Provenance of the batch is not on `Source`: only `ingested_at`. The manifest's `snapshot.index_sha256` (which
  crawl) and `trimmed_jsonl_sha256` (which file) are checked at ingest and then dropped. Add them if an audit
  ever needs to name the crawl a stored trim came from.
- The cap's two sides are counted differently. `removed_words` counts by whitespace and leaves page furniture
  out; `original_words` is the corpus tokeniser over every line of `original_text`, furniture included (all 724
  stored records; ADR-0010 called it "editorial words"). The gap is small and runs both ways. Both are enforced
  as the writer produces them (`trim_rules.py`); whether they should share one tokeniser is a superseding ADR.
- `make test-scripts` pins pydantic, beanie and what they pull in to the core lock (`scripts/locked_pins.py`);
  pytest, pyyaml and uv itself still float.
- One passage ends a content line with the page furniture "Return to main page" glued on (a letter in the
  *Dear Doctor* series); a whole-line trim cannot cut it. Parser territory, not touched here.
- Classification (`docs/reports/voa-classify.md`), ideas only, none coded. The stems are narrowed
  (`docs/reports/voa-safety-stems.md`); what stems cannot fix is how a mention is counted: count a stem once per
  paragraph (one anecdote gave "politician" 4 times and 5 war words; "President Donald Trump" counts as `president`
  and `trump`), and read a sample of passages the flags left alone, which no pass has done.
- The "American Mosaic:" title makes a magazine even when the stored text is one segment (1 of 3 read); look at the
  text. An English lesson with no programme and no lesson title ("Some New Words for VOA's Word Book") is tagged
  explainer. The 50 labels have one labeller (the assistant): have the owner overrule any, and read a second sample
  that was not used to write the rules.
- The unit tags (`units.tsv`) are not validated: 352 of the 724 match no unit, and 7 of 15 reader letters are
  tagged *Study and work*. Measure their precision on a read sample before the per-unit counts decide a unit.
- Missed frame by type: voa-trim-corpus.md measured 57% of the 724 as free of a frame line the lists miss, mostly in
  the lesson programmes. Re-measure it on the 370 explainers and news items, the set the reading path draws from.
- `--dry-run` for `ingest_speaking_items.py`, as `ingest_sources.py` has: bind without indexes and
  report. Left out of the speaking-items PR to stay under its 250-line budget.
- Score: context-dependent references. "the" before a vowel is ðɪ, "a" in citation is eɪ; one citation form per
  word gives false errors (held-out native utterance in `docs/reports/score-false-alarms.md`). espeak-ng in
  sentence mode knows some of this, but then word boundaries in its output are not reliable.
- Score: GOP over more than one CTC frame (spike plus adjoining blanks, or posterior-weighted). Measure on the
  evaluation set before choosing.
- Score: remaining native false alarms at v2 (`docs/reports/score-weak-forms.md`), each a reference problem,
  none coded. (1) The vowel+schwa tokens `aɪə aɪɚ iə` (fire, quiet, diocese): half of their 57 occurrences are wrong
  and the model hears aɪ; they are 15% of the wrongs left. (2) The flap t→ɾ and the syllabic l (ə→əl). (3) Short
  words outside the ten, reduced in connected speech: an, his, from, have, because, me, her. Each needs a source for
  its other forms before it is added; pick them from a sample other than the one the threshold comes from.
- Score: a speaker-disjoint held-out check for v2 (LibriSpeech test-clean has 40 other speakers); the held-out run
  in `score-weak-forms.md` shares its 40 speakers with the calibration sample.
- Web result view, ideas only, none coded: play the learner's own recording back beside a model reading of the
  sentence (TTS exists, `spikes/tts`); show the position of a wrong phoneme in the recording (the response has
  `startMs`/`endMs`); remember which words the learner tapped. Open: how a learner reads "Chưa rõ" (unclear) next to
  "Cần luyện" (wrong) is untested; ask a native reader and watch one learner before the legend wording is fixed.
- Web: the page trusts the shape of `/v1/score` beyond `words` being an array. If the contract grows a field the view
  needs, validate it at the proxy (the schema is in `packages/contracts`) rather than in the component.
- Listen audio (#56): playback was not exercised in a real browser; quality by ear is still `spikes/tts/CHECKLIST.md`.
  Kokoro's `bf_emma` scored one word wrong ("laboratory", British /ləˈbɒrətri/). A sentence whose text changes needs
  `make listen-audio` again (the manifest test fails until then). Voices for passages beyond the 20 items: not made.
- Score-vi (#55): the FIT rule (≥ 80% of deliberate errors caught, ≤ 1.0 wrong per normal reading) was set without
  data by the assistant; revisit it before the evaluation set is scored. Notes name a deliberate error by the first
  word with that spelling; a sentence with the word twice needs an index.
- Passages (#57, #58): a G2P change moves `classifier_version`, so a re-run reclassifies every passage (replaced, not
  versioned). The detail route serves any pinned version that passes the list rule; the list shows current versions
  only. The unit names are English API values; the reading page has Vietnamese copy for "Study and work" only.
- Reading page (#59): the passage id travels as `?id=`; the practice view of a passage sentence has no listen audio
  unless the sentence is also a speaking item.
- `make test-speech` ran in about 11 s on the laptop on 2026-10-14 (458 tests on main): over the 10 s budget. Profile
  with `pytest --durations=15` and move slow cases out or speed them up.
