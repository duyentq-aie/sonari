"""The LLM port: one chat call in, text and usage out. `OpenAICompatible` speaks the chat
completions API that most providers serve (ADR-0004: an API, never a self-hosted GPU); `Fake` is
for tests.

The key is read from the environment and only ever goes in the Authorization header: never in a
URL, an exception, a log line or a span. Prices are USD per million tokens, from the provider's
price page, so each call carries its cost.
"""

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol

ENV = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_PRICE_IN", "LLM_PRICE_OUT")


@dataclass(frozen=True)
class Reply:
    text: str
    model: str  # as the provider reports it
    tokens_in: int
    tokens_out: int
    cost_usd: float


class Provider(Protocol):
    name: str  # gen_ai.provider.name
    model: str  # the requested model

    def complete(self, system: str, user: str) -> Reply: ...


@dataclass(frozen=True)
class OpenAICompatible:
    base_url: str
    api_key: str
    model: str
    price_in: float
    price_out: float
    name: str = "openai_compatible"
    timeout_s: float = 60.0

    @classmethod
    def from_env(cls) -> "OpenAICompatible":
        missing = [k for k in ENV if not os.environ.get(k)]
        if missing:
            raise SystemExit(f"set {', '.join(missing)} in .env (see .env.example)")
        e = os.environ
        return cls(e["LLM_BASE_URL"].rstrip("/"), e["LLM_API_KEY"], e["LLM_MODEL"],
                   float(e["LLM_PRICE_IN"]), float(e["LLM_PRICE_OUT"]))  # fmt: skip

    def complete(self, system: str, user: str) -> Reply:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps({"model": self.model, "messages": messages, "temperature": 0}).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                body = json.load(response)
        except urllib.error.HTTPError as error:  # the body is the provider's message, not the key
            raise RuntimeError(f"HTTP {error.code}: {error.read()[:300]!r}") from None
        usage = body.get("usage") or {}
        tokens_in, tokens_out = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        cost = (tokens_in * self.price_in + tokens_out * self.price_out) / 1_000_000
        text = body["choices"][0]["message"]["content"] or ""
        return Reply(text, body.get("model", self.model), tokens_in, tokens_out, cost)


@dataclass
class Fake:
    """Answers from a table keyed by the user message, else `default`; records every call."""

    answers: dict[str, str]
    default: str = "{}"
    name: str = "fake"
    model: str = "fake-1"

    def __post_init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> Reply:
        self.calls.append((system, user))
        text = self.answers.get(user, self.default)
        return Reply(text, self.model, len(system + user) // 4, len(text) // 4, 0.0)
