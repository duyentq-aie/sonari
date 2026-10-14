"""Reading the classes file and storing it: the part of passage classes that needs `ingest`."""

import json
from datetime import datetime
from pathlib import Path

from sonari_core.content.ingest import IngestReport, InvalidCorpus, Outcome
from sonari_core.content.models import Source
from sonari_core.content.passages import PassageClass, PassageClassRecord


def load_classes(path: Path) -> list[PassageClassRecord]:
    """Every line of `path` as a record, or `InvalidCorpus` naming each bad line."""
    records: list[PassageClassRecord] = []
    problems: list[str] = []
    for number, line in enumerate(path.read_text("utf-8").splitlines(), start=1):
        try:
            record = PassageClassRecord.model_validate(json.loads(line))
        except ValueError as error:  # bad JSON and pydantic's ValidationError
            problems.append(f"line {number}: {error}")
            continue
        if any(record.source == other.source for other in records):
            problems.append(f"line {number}: {record.source} appears twice")
        records.append(record)
    if problems:
        raise InvalidCorpus(problems)
    return records


async def source_problems(records: list[PassageClassRecord]) -> list[str]:
    """Records whose pinned Source is not stored, or whose sentences fall outside its lines."""
    problems = []
    for record in records:
        source = await Source.get(record.source)
        if source is None:
            problems.append(f"{record.source} is not in content.sources")
            continue
        for line, _, end, _ in record.sentences:
            if line >= len(source.text) or end > len(source.text[line]):
                problems.append(f"{record.source}: sentence {line}:..{end} is outside the text")
    return problems


async def ingest_classes(records: list[PassageClassRecord], now: datetime) -> IngestReport:
    """Same content: unchanged. Another classifier version: replaced. Else a conflict, refused."""
    report = IngestReport()
    for record in records:
        stored = await PassageClass.get(record.source)
        new = PassageClass(id=record.source, ingested_at=now, **record.model_dump())
        if stored is None:
            outcome = Outcome.INSERTED
            await new.insert()
        elif stored.model_dump(include=set(PassageClassRecord.model_fields)) == record.model_dump():
            outcome = Outcome.UNCHANGED
        elif stored.classifier_version != record.classifier_version:
            outcome = Outcome.SUPERSEDED
            await new.replace()
        else:
            outcome = Outcome.CONFLICT
        report.record(outcome, record.source)
    return report
