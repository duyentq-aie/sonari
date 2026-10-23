# ADR-0010: A Source version is immutable, and one version of each passage is current

- Status: Accepted
- Date: 2026-10-04

## Context

The trimmed corpus (ADR-0008, 724 passages at a 5% cap, `rules_version` `voa-trim/163aae96e072`)
now lives in the `content` database as `Source` documents, so that everything downstream reads
it from one place. Ingesting it raises a question ADR-0008 5.6 leaves open: **when a passage is
re-trimmed under a newer `rules_version`, does the stored document get overwritten, or are both
kept with one marked current?** Three facts decide it.

- **Everything downstream is derived from `text`.** Learnables (example sentences), exercises,
  the full read of P50 and the passage audio all describe specific lines. If `text` changes
  under them, they describe lines that may no longer be there, and nothing says so.
- **`rules_version` has no order.** It is a digest of the rule files (`voa-trim/<12 hex>`), so
  neither the database nor the ingest can tell which of two versions is newer.
- **ADR-0008 5.6 says a re-trim is read before and after**, removed lines side by side. Both
  versions must therefore be readable at the same time.

## Decision

1. **A passage is identified by VOA's article number, not its URL and not a hash of its text.**
   `source_id = voa:<number>`, taken from the URL. 700 of the 724 URLs carry a title slug
   (`/a/<slug>/<number>.html`) that VOA can edit; the number is VOA's own and is unique across the
   corpus (checked: 724 distinct). A hash of the text would change with every trim, so it could
   not tell "the same passage, trimmed again" from "a different passage". The prefix names the
   origin, so Tatoeba sentences get their own later.
2. **A stored version is identified by `(source_id, rules_version)`**, and that pair is the
   document's `_id`: `voa:1630766@voa-trim/163aae96e072`. The `_id` is the identity key of the
   ingest, and the `_id` index is what makes it idempotent: a second run cannot create a second
   document, whatever the interleaving. It is deterministic on purpose, so dev and prod hold the
   same ids and a corpus loaded into a fresh database does not break references.
3. **Re-trimming keeps both.** A new `rules_version` adds a new document and leaves the old one
   untouched. Exactly one version of each passage has `current: true`, and a partial unique
   index on `source_id` (where `current` is true) makes the database refuse a second one. The
   ingest makes a version current in one transaction per passage (demote the old, insert or
   promote the new), so a passage never has zero or two current versions, and a run that stops
   half-way is finished by running it again.

   Why not overwrite:
   - *The "before" is lost.* The 5.6 reading needs both versions, and `~/sonari-trimmed` is not
     versioned: the old file may be gone by then.
   - *Derived content goes stale in silence.* With versions, anything derived stores the
     `Source._id` it was built from and reads that, not "current". It is stale exactly when its
     pinned id is not the current one, a check inside the content context.
   - *Rollback is cheap.* A bad rules version is undone by ingesting the old file again, which
     inserts nothing and flips `current` back (tested). With an overwrite it needs the old file.

   The cost is that a reader must say which version it means. Authoring reads the current one
   through `Source.get_current(source_id)`; derived content reads its pinned `_id`. A query on
   `source_id` without `current: true` cannot use the partial index (`explain`: COLLSCAN) and may
   return several versions, so do not write one.
4. **The ingest does not decide which version is newer.** The file you ingest becomes current for
   every passage in it. Ingesting an older file is a rollback, and is allowed. The gate of
   ADR-0008 5.6 (removed lines read before and after) comes before the file is ingested, as it
   did for this corpus. The summary line counts the passages that were superseded.
5. **The same key with different content is a conflict.** If `(source_id, rules_version)` is
   stored and the file carries other content for it, the trim changed without a version bump
   (the version digests the rule files, so a parser change does not move it). The ingest refuses
   that passage, leaves what is stored, names the key and exits with status 1.
6. **A file is validated whole before anything is written** (`TrimmedPassage`, no database):
   the ADR-0008 decision 1 invariants (`text` is `original_text` minus the removed lines, each
   removed record is the line it says, no line twice), the ADR-0008 decision 2 limits (the cap is
   5% whatever the file declares; `original_words`, `removed_words` and `removed_share` are
   derived from the lines and must equal what the file says; the trimmed text is 250-1,200 words;
   `fk` is below 7), a field the schema does not keep (so provenance cannot vanish quietly), one
   version per passage per file, and, when `MANIFEST.json` sits beside it, the file's sha256 and
   passage count. `Source` does not inherit these checks: they run where a file enters, and a
   stored version is read as stored, so a rule that tightens later cannot make an older version
   unreadable (as decision 3 requires).

## The document

`Source` in `services/core/src/sonari_core/content/models.py`, collection `content.sources`.

| Field | Holds |
|---|---|
| `id` | `source_id@rules_version` |
| `source_id`, `url`, `title`, `program` | the passage and where it came from (`program` is empty when the page names none) |
| `fk` | Flesch-Kincaid grade of **`text`**, the trimmed lines |
| `original_words` | words of the **original** page, counted over every line of `original_text` (page furniture included) with the corpus tokeniser: the corpus's `words`, the denominator of `trim.removed_share`. Derived and checked at ingest |
| `original_text`, `text` | lists of lines, not joined: `trim.removed[].index` addresses positions in `original_text` |
| `trim` | `rules_version`, `cap`, `removed_words`, `removed_share`, `removed[{index, kind, rule, text}]` |
| `current`, `ingested_at` | which version is current; when this version was stored (versions cannot be ordered by `rules_version`) |

`words` was renamed. In the corpus it counts the original page while `fk` is measured on the
trimmed text (the maximum is 1,241, over the 1,200 ceiling the filter applies to the trimmed
text). Under the name `words` a reader would filter `text` by a number that is not its length.
No word count of `text` is stored. Where the service needs one it counts (`trim_rules.count_words`,
the corpus tokeniser written out once more and pinned to the original by a drift test): the length
window of ADR-0008 decision 2 is checked that way.

**Queried:** the passage by `source_id` with `current: true` (partial unique index
`source_id_current`), and a pinned version by `_id`. **Not indexed:** `fk`, `original_words`,
`program`, `title`. Filters on them scan the current sources (724 documents, 6 MiB), which is
cheaper than keeping an index; add one when the corpus grows or a profile shows the query.

## Consequences

- Each re-trim adds about 8 KB per passage (6 MiB for a full re-trim). Old versions are never
  deleted; a retention rule can come later.
- Learnables and exercises (P40 onwards) must store the pinned `Source._id`.
- Nothing is published: other contexts that need a Source consume events and keep a read model
  (ADR-0001), and no event exists yet (backlog).
- The ADR-0008 invariant is implemented twice, in `tools/voa_corpus/trim.py` (`validate`) and in
  `TrimmedPassage`, because the service cannot import the tools. Both suites pin the edited,
  dropped, forged and reordered cases; the service's adds a duplicated or out-of-range index, a
  missing version or rule, and an unknown field. The numbers of decision 2 (cap, window, grade
  ceiling, and the word counts behind them) are written in both places too, in
  `tools/voa_corpus/filters.py` and `sonari_core/content/trim_rules.py`.
  `scripts/tests/test_adr_0008_drift.py` and `test_adr_0008_constraints_drift.py` feed both the same
  cases, compare the constants with each other and with the text of ADR-0008, and fail if they differ.

## Alternatives rejected

- **Overwrite in place.** Simplest, and right only while nothing is derived from `text`. It
  loses the "before" and makes staleness undetectable.
- **Keep both, with `current` in a separate `source_heads` collection.** Leaves documents fully
  immutable, but promoting is a write to two collections and nothing in the database says a
  passage has one head.
- **The newest `ingested_at` wins automatically.** Ingesting an old file by mistake would then
  be a silent regression, and a rollback would need a new timestamp.
- **The URL as the key.** Not stable: the slug is part of it.
- **A hash of the text as `_id`.** Changes with every trim.
- **An ObjectId `_id` and a compound unique index.** Ids differ per environment, and it costs a
  second index.
