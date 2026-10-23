# glosses

Vietnamese glosses for the B1-B2 words of the reading page: a short gloss and one line on how the
word is used in that sentence. Generated offline, reviewed, then ingested; no LLM call at learner
runtime (ADR-0004). The English sentence is the stored corpus sentence, never generated or edited;
the model writes only the Vietnamese (ADR-0006).

Order: **gold set first, then the harness, then prompt tuning.** Prompt v1 has not been run on the
gold set.

## Targets (`make passage-classes gloss-gold`)

The sentences are what `/v1/passages` serves for the reading unit (*Study and work*: usable type,
no safety flag under the default rule, practicable sentences only). A target is a token at B1 or B2
of CEFR-J 1.5 that is not a proper noun or acronym (`voa_corpus.measure.token_class`). On
2026-10-23: **267 sentences in 36 passages** (2 of the 38 listed passages have no practicable
sentence), **165 distinct words** (lowercase spelling, so "users" and "user" would be two),
**211 word-sentence pairs**. The level lookup is approximate: "found" is read as the B2 headword
("to found a school"), although most uses are the past of "find".

## The gold set (`gold.tsv`)

40 pairs, seed 20261023. Senses cannot be told apart automatically, so 10 words seen in more than
one sentence come twice, as far apart as the data allows: two nltk tags first, then two passages,
then two sentences. The other 20 are one pair per word, B1 and B2 alternating. `pos` is nltk's tag
in that sentence, a hint with errors (pair 2 tags "sometimes" as a verb).

**The owner fills it, from the sentence alone, with no model output in sight.** Open `gold.tsv` in
an editor that keeps tabs (or a spreadsheet, saved back as tab-separated UTF-8) and fill two columns
on every row:

- `my_gloss`: the Vietnamese gloss of the word in that sentence, as a learner should see it
  (1-4 words).
- `note`: optional. Anything a reviewer should know: an acceptable alternative gloss, "same sense
  as pair 5", "the tag is wrong", "a bad target, skip".

Change no other column, add no row, keep no tab or line break inside a cell. Then:

    make gloss-lock      # refuses while a my_gloss is empty; writes gold.sha256
    git add tools/glosses/gold.tsv tools/glosses/gold.sha256

From then on `make gloss-eval` refuses to run if `gold.tsv` differs from its lock, so the gold set
cannot move after a model answer is seen. To change it on purpose, edit, lock again and say why in
the commit.

## The harness (`make gloss-eval`)

Needs `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `LLM_PRICE_IN`, `LLM_PRICE_OUT` in `.env` (any
chat completions API; prices in USD per million tokens). `ARGS=--fake` runs the fake provider
instead (no API call). One call per pair at temperature 0, then `runs/<prompt>-<model>-<time>.tsv`:
your gloss beside the model's gloss and explanation, the automatic checks (`checks.py`: parses,
vietnamese, no_english, short), the model, tokens in and out, latency and cost. Fill its `review`
column by hand: `agree`, `partly` or `disagree`. In this first round no model judges a gloss.

Each call is an OpenTelemetry span with `gen_ai.*` attributes (operation, provider, request and
response model, input and output tokens, cost) and the prompt version. With `LANGFUSE_PUBLIC_KEY`
and `LANGFUSE_SECRET_KEY` set (`LANGFUSE_HOST` defaults to Langfuse Cloud) spans go to Langfuse's
OTLP endpoint; without them nothing leaves the process and the run is the same.

The API key goes only in the Authorization header: never in a URL, a log line, a span or an error.
