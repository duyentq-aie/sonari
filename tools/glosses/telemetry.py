"""One span per LLM call with the OpenTelemetry gen_ai.* attributes, exported to Langfuse's OTLP
endpoint when LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set; without them spans stay in the
process and the tool runs the same. Model, tokens, latency and cost also come back on `Call`.
"""

import base64
import os
import time
from dataclasses import dataclass

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Tracer

from glosses.provider import Provider, Reply


@dataclass(frozen=True)
class Call:
    reply: Reply | None  # None when the call failed
    error: str
    latency_ms: int


def tracer_provider() -> TracerProvider:
    provider = TracerProvider()
    public, secret = os.environ.get("LANGFUSE_PUBLIC_KEY"), os.environ.get("LANGFUSE_SECRET_KEY")
    if public and secret:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        host = os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com").rstrip("/")
        auth = base64.b64encode(f"{public}:{secret}".encode()).decode()
        exporter = OTLPSpanExporter(
            endpoint=f"{host}/api/public/otel/v1/traces", headers={"Authorization": f"Basic {auth}"}
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
    return provider


def chat(tracer: Tracer, llm: Provider, system: str, user: str, prompt_version: str) -> Call:
    with tracer.start_as_current_span(f"chat {llm.model}") as span:
        span.set_attributes({
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": llm.name,
            "gen_ai.request.model": llm.model,
            "gen_ai.request.temperature": 0.0,
            "sonari.prompt.version": prompt_version,
        })  # fmt: skip
        start = time.perf_counter()
        try:
            reply, error = llm.complete(system, user), ""
        except Exception as exc:  # one failed pair is a row in the report, not a stopped run
            reply, error = None, f"{type(exc).__name__}: {exc}"
            span.set_attribute("error.type", type(exc).__name__)
        latency_ms = round((time.perf_counter() - start) * 1000)
        span.set_attribute("sonari.latency_ms", latency_ms)
        if reply is not None:
            span.set_attributes({
                "gen_ai.response.model": reply.model,
                "gen_ai.usage.input_tokens": reply.tokens_in,
                "gen_ai.usage.output_tokens": reply.tokens_out,
                "gen_ai.usage.cost": reply.cost_usd,
            })  # fmt: skip
        return Call(reply, error, latency_ms)
