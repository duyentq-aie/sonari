"""Ingest the passage classification (tools/speaking_items/classes.py) into passage_classes.

    make ingest-passage-classes     # ~/sonari-trimmed/voa/classes.jsonl (ingest-demo-classes: demo)

Needs the pinned Sources first (ADR-0010). Idempotent; the file is checked whole, and against the
Sources, before any write. Exit 1: invalid file, missing Source, or a conflict.
"""

import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pymongo import AsyncMongoClient
from sonari_core import content
from sonari_core.content.ingest import InvalidCorpus
from sonari_core.content.passages_ingest import ingest_classes, load_classes, source_problems


async def run(path: Path, mongo_uri: str) -> int:
    try:
        records = load_classes(path)
    except InvalidCorpus as error:
        print(f"{path} was not ingested:", *error.problems, sep="\n  ", file=sys.stderr)
        return 1
    client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(mongo_uri, tz_aware=True)
    try:
        await content.SPEC.init(client)
        if problems := await source_problems(records):
            print(f"{path} was not ingested:", *problems, sep="\n  ", file=sys.stderr)
            return 1
        r = await ingest_classes(records, datetime.now(UTC))
        print(f"{len(records)} passages: {r.inserted} inserted, {r.superseded} reclassified, "
              f"{r.unchanged} unchanged, {len(r.conflicts)} conflicts: {r.conflicts}")  # fmt: skip
        return 1 if r.conflicts else 0
    finally:
        await client.close()


if __name__ == "__main__":
    if not (uri := os.environ.get("MONGO_URI_CORE")):
        sys.exit("MONGO_URI_CORE is not set: copy .env.example to .env and run via make")
    sys.exit(asyncio.run(run(Path(sys.argv[1]), uri)))
