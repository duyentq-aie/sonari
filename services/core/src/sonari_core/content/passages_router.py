"""GET /v1/passages?unit=<unit> and GET /v1/passages/{id}: the passages a learner may read, from
`passage_classes` and `sources` only; lines are cut at the stored marks (content/passages.py)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from sonari_core.content.models import Source
from sonari_core.content.passages import PassageClass, listable
from sonari_core.shared.errors import AppError, ErrorEnvelope
from sonari_core.shared.message_keys import MessageKey

router = APIRouter(prefix="/v1/passages", tags=["content"])


class PassageOut(BaseModel):
    id: str  # the pinned Source._id; URL-encode it as a path segment
    title: str
    type: str
    url: str  # the VOA page, for the credit


class PassagesOut(BaseModel):
    passages: list[PassageOut]


class Segment(BaseModel):
    text: str
    practicable: bool  # a whole sentence a learner can record (and send as referenceText)


class PassageDetail(PassageOut):
    lines: list[list[Segment]]  # each line of `text`, cut into segments that join back to it


def segments(line: str, marks: list[tuple[int, int, bool]]) -> list[Segment]:
    """`line` cut at its practicable sentences; the text between them is one plain segment."""
    out: list[Segment] = []
    at = 0  # where the text not yet cut starts
    for start, end in sorted((s, e) for s, e, practicable in marks if practicable):
        if start > at:
            out.append(Segment(text=line[at:start], practicable=False))
        out.append(Segment(text=line[start:end], practicable=True))
        at = end
    if at < len(line):
        out.append(Segment(text=line[at:], practicable=False))
    return out


async def load_passages(unit: Annotated[str, Query(min_length=1)]) -> list[PassageOut]:
    """Current versions only, ordered by `_id` (a dependency: the route tests replace it)."""
    types = {c.id: c.type for c in await PassageClass.find(listable(unit)).to_list()}
    found = await Source.find({"_id": {"$in": list(types)}, "current": True}).sort("_id").to_list()
    return [PassageOut(id=s.id, title=s.title.strip(), type=types[s.id], url=s.url) for s in found]


async def load_passage(passage_id: str) -> PassageDetail:
    """Any pinned version (ADR-0010), but only one the list rule lets through; else 404."""
    found = await PassageClass.find_one({"_id": passage_id} | listable())
    source = await Source.get(passage_id) if found is not None else None
    if found is None or source is None:
        raise AppError(404, "passage_not_found", MessageKey.NOT_FOUND)
    lines = [
        segments(text, [(s, e, p) for n, s, e, p in found.sentences if n == number])
        for number, text in enumerate(source.text)
    ]
    head = {"id": source.id, "title": source.title.strip(), "type": found.type, "url": source.url}
    return PassageDetail(**head, lines=lines)


@router.get("", response_model=PassagesOut, responses={500: {"model": ErrorEnvelope}})
async def passages(found: Annotated[list[PassageOut], Depends(load_passages)]) -> PassagesOut:
    return PassagesOut(passages=found)


@router.get("/{passage_id:path}", responses={c: {"model": ErrorEnvelope} for c in (404, 500)})
async def passage(found: Annotated[PassageDetail, Depends(load_passage)]) -> PassageDetail:
    return found
