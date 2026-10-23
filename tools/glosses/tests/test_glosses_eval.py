"""Checks, the provider port, the gen_ai span and the harness, with the fake provider."""

import io
import json
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from glosses import evaluate
from glosses.checks import check, parse
from glosses.provider import ENV, Fake, OpenAICompatible
from glosses.targets import Pair, write_gold
from glosses.telemetry import chat, tracer_provider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

MARKS = {
    "`": 0x300,
    "'": 0x301,
    "^": 0x302,
    "~": 0x303,
    "(": 0x306,
    "?": 0x309,
    "+": 0x31B,
    "*": 0x323,
}
TABLE = {"the": 0, "company": 0, "will": 0, "budget": 2, "manage": 2, "next": 0, "year": 0}
KEY = "sk-test-not-a-real-key"


def vi(text: str) -> str:
    """Vietnamese from ASCII plus mark signs ("vie^*c" -> viec with circumflex and dot below), so no
    Vietnamese letter sits in this file (scripts/check_no_vietnamese.py)."""
    for sign, code in MARKS.items():
        text = text.replace(sign, chr(code))
    return unicodedata.normalize("NFC", text.replace("dd", chr(0x111)))


GLOSS = vi("ngu^`n ti^`n")
EXPLANATION = vi("Danh tu+` chi? so^' ti^`n co^ng ty du+* ti'nh chi tie^u.")


def answer(gloss: str = GLOSS, explanation: str = EXPLANATION) -> str:
    return json.dumps({"gloss": gloss, "explanation": explanation}, ensure_ascii=False)


def test_a_vietnamese_answer_passes_every_check() -> None:
    assert check(answer(), "budget", TABLE)[1] == dict.fromkeys(
        ("parses", "vietnamese", "no_english", "short"), True
    )


def test_a_fenced_answer_parses_and_a_broken_one_does_not() -> None:
    assert parse(f"```json\n{answer()}\n```") == {"gloss": GLOSS, "explanation": EXPLANATION}
    for bad in ("not json", "[]", '{"gloss": "x"}', '{"gloss": "", "explanation": "y"}'):
        assert parse(bad) is None
        assert check(bad, "budget", TABLE)[1]["parses"] is False


def test_english_text_is_not_vietnamese() -> None:
    assert (
        check(answer("budget", "The money a company plans to spend."), "budget", TABLE)[1][
            "vietnamese"
        ]
        is False
    )


def test_the_target_word_is_allowed_and_a_copied_sentence_is_not() -> None:
    quoted = answer(explanation=vi("Tu+` budget o+? dda^y la` danh tu+`."))
    assert check(quoted, "budget", TABLE)[1]["no_english"] is True
    copied = answer(explanation=vi("Ca^u: the company will manage the budget."))
    assert check(copied, "budget", TABLE)[1]["no_english"] is False


def test_a_long_explanation_fails_short() -> None:
    assert check(answer(explanation=EXPLANATION * 4), "budget", TABLE)[1]["short"] is False


def test_from_env_names_the_missing_variables_never_values(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LLM_API_KEY", KEY)
    with pytest.raises(SystemExit) as stopped:
        OpenAICompatible.from_env()
    assert "LLM_BASE_URL" in str(stopped.value) and KEY not in str(stopped.value)


def adapter() -> OpenAICompatible:
    return OpenAICompatible("https://llm.example/v1", KEY, "m-1", price_in=1.0, price_out=4.0)


def test_the_adapter_sends_the_key_in_a_header_and_prices_the_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[urllib.request.Request] = []
    body = {"model": "m-1-2026", "choices": [{"message": {"content": answer()}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500}}  # fmt: skip

    def urlopen(request: urllib.request.Request, timeout: float) -> io.BytesIO:
        sent.append(request)
        return io.BytesIO(json.dumps(body).encode())

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    reply = adapter().complete("system", "user")
    assert (reply.model, reply.tokens_in, reply.tokens_out, reply.cost_usd) == (
        "m-1-2026",
        1000,
        500,
        0.003,
    )
    assert (
        sent[0].full_url == "https://llm.example/v1/chat/completions"
        and KEY not in sent[0].full_url
    )
    assert sent[0].get_header("Authorization") == f"Bearer {KEY}"
    assert KEY not in (sent[0].data or b"").decode()


def test_an_http_error_names_the_status_not_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen(request: urllib.request.Request, timeout: float) -> None:
        raise urllib.error.HTTPError(request.full_url, 401, "no", {}, io.BytesIO(b"bad key"))  # type: ignore[arg-type]

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    with pytest.raises(RuntimeError, match="HTTP 401") as failed:
        adapter().complete("system", "user")
    assert KEY not in str(failed.value)


def traced() -> tuple[TracerProvider, InMemorySpanExporter]:
    spans = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(spans))
    return provider, spans


def test_a_call_is_one_span_with_gen_ai_attributes() -> None:
    provider, spans = traced()
    call = chat(provider.get_tracer("t"), Fake({"u": answer()}), "s", "u", "v1/abc")
    (span,) = spans.get_finished_spans()
    attributes = dict(span.attributes or {})
    assert span.name == "chat fake-1" and call.reply is not None and call.error == ""
    assert attributes["gen_ai.operation.name"] == "chat"
    assert attributes["gen_ai.request.model"] == attributes["gen_ai.response.model"] == "fake-1"
    assert attributes["gen_ai.usage.input_tokens"] == call.reply.tokens_in
    assert attributes["gen_ai.usage.output_tokens"] == call.reply.tokens_out
    assert (
        attributes["gen_ai.usage.cost"] == 0.0 and attributes["sonari.prompt.version"] == "v1/abc"
    )
    assert attributes["sonari.latency_ms"] == call.latency_ms


def test_a_failed_call_is_recorded_not_raised() -> None:
    class Down(Fake):
        def complete(self, system: str, user: str) -> object:
            raise TimeoutError("slow")

    provider, spans = traced()
    call = chat(provider.get_tracer("t"), Down({}), "s", "u", "v1/abc")
    assert call.reply is None and call.error == "TimeoutError: slow"
    assert spans.get_finished_spans()[0].attributes["error.type"] == "TimeoutError"  # type: ignore[index]


def test_without_langfuse_keys_nothing_is_exported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert tracer_provider()._active_span_processor._span_processors == ()


def gold_file(tmp_path: Path, gloss: str) -> Path:
    path = tmp_path / "gold.tsv"
    pairs = [Pair("budget", "B1", "noun", "s#0:0", "The company will manage the budget.")]
    write_gold(pairs, path)
    budget = "The company will manage the budget."
    path.write_text(path.read_text("utf-8").replace(f"{budget}\t\t", f"{budget}\t{gloss}\t"))
    return path


def test_lock_refuses_an_unfilled_gold_set(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="pair"):
        evaluate.lock(gold_file(tmp_path, ""), tmp_path / "gold.sha256")


def test_eval_refuses_a_gold_set_changed_after_its_lock(tmp_path: Path) -> None:
    gold, lock = gold_file(tmp_path, GLOSS), tmp_path / "gold.sha256"
    evaluate.lock(gold, lock)
    gold.write_text(gold.read_text("utf-8").replace(GLOSS, "x"), "utf-8")
    with pytest.raises(SystemExit, match="not locked"):
        evaluate.run(Fake({}), traced()[0], TABLE, gold, lock, tmp_path / "runs")


def test_eval_puts_the_model_gloss_beside_the_owner_s_with_checks_and_cost(tmp_path: Path) -> None:
    gold, lock = gold_file(tmp_path, GLOSS), tmp_path / "gold.sha256"
    evaluate.lock(gold, lock)
    before = gold.read_bytes()
    llm = Fake({}, default=answer(vi("nga^n sa'ch")))
    path = evaluate.run(llm, traced()[0], TABLE, gold, lock, tmp_path / "runs")
    header, row = [line.split("\t") for line in path.read_text("utf-8").splitlines()]
    got = dict(zip(header, row, strict=True))
    assert header == evaluate.OUT and gold.read_bytes() == before
    assert (got["my_gloss"], got["word"], got["review"]) == (GLOSS, "budget", "")
    assert got["parses"] == "true" and got["model"] == "fake-1" and got["cost_usd"] == "0.000000"
    assert (
        "Word: budget" in llm.calls[0][1]
        and "The company will manage the budget." in llm.calls[0][1]
    )
