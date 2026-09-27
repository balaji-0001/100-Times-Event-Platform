"""Thin wrapper around the configured LLM provider (Google Gemini or Anthropic Claude).

This is the ONLY place in the codebase that talks to an LLM. Every
AI-dependent pipeline stage goes through here so there is exactly one place
that knows which provider is configured, and exactly one place that changes
to swap providers — the rest of the application never imports a vendor SDK.

`AI_PROVIDER` selects the implementation (`gemini` or `anthropic`). Both
expose the same four operations with identical signatures and return shapes,
so no agent, pipeline stage, route, or test needs to know which one is live:

- `generate_structured`      -> a dict matching the caller's JSON schema
- `generate_text`            -> plain text
- `generate_with_web_search` -> {"text": str, "citations": [{"url", "title"}, ...]}
- `ping`                     -> a safe connectivity diagnostic dict

Golden rule enforced here: this client only ever returns what the model
actually said. It never fabricates a fallback response when the API key is
missing or the call fails — callers get an `AIClientError` and decide how to
record that honestly (e.g. FAILED_AI_EXTRACTION). Web-search citations come
only from URLs the provider itself returned — none are invented — and API
keys never appear in any error message, return value, or log line.
"""

import copy
import json
import logging
import time
from typing import Any
from urllib.parse import urlparse

import httpx
from anthropic import Anthropic
from anthropic import APIError as AnthropicAPIError
from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from backend.core.config import Settings, get_settings
from backend.services.social_agent.web_fetch import USER_AGENT

logger = logging.getLogger(__name__)

PROVIDER_GEMINI = "gemini"
PROVIDER_ANTHROPIC = "anthropic"
SUPPORTED_PROVIDERS = (PROVIDER_GEMINI, PROVIDER_ANTHROPIC)
_PROVIDER_KEY_ENV = {PROVIDER_GEMINI: "GEMINI_API_KEY", PROVIDER_ANTHROPIC: "ANTHROPIC_API_KEY"}


class AIClientError(Exception):
    """Raised when the AI provider is not configured, or a call fails
    unrecoverably (auth error, network error, malformed model output)."""


def not_configured_message(settings: Settings | None = None) -> str:
    """The one 'no API key' message every call site uses, so the wording is
    consistent and always names the env var for the provider actually selected."""
    settings = settings or get_settings()
    env_var = _PROVIDER_KEY_ENV.get(settings.ai_provider, "an API key")
    return f"AI provider is not configured (AI_PROVIDER={settings.ai_provider} requires {env_var})"


class AIClient:
    """Provider-neutral interface. One subclass per vendor; nothing outside
    this module should depend on which subclass it is holding."""

    provider: str = ""

    @property
    def is_configured(self) -> bool:
        raise NotImplementedError

    @property
    def model(self) -> str:
        raise NotImplementedError

    def generate_structured(
        self,
        system: str,
        user: str,
        tool_name: str,
        tool_description: str,
        input_schema: dict[str, Any],
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def generate_with_web_search(
        self,
        system: str,
        user: str,
        max_tokens: int = 2048,
        max_uses: int = 5,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def generate_text(self, system: str, user: str, max_tokens: int = 512) -> str:
        raise NotImplementedError

    def ping(self) -> dict[str, Any]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Anthropic (Claude)
# ---------------------------------------------------------------------------


class AnthropicAIClient(AIClient):
    provider = PROVIDER_ANTHROPIC

    def __init__(self) -> None:
        self._client: Anthropic | None = None

    @property
    def is_configured(self) -> bool:
        return bool(get_settings().anthropic_api_key)

    @property
    def model(self) -> str:
        return get_settings().anthropic_model

    def _get_client(self) -> Anthropic:
        if not self.is_configured:
            raise AIClientError(not_configured_message())
        if self._client is None:
            self._client = Anthropic(api_key=get_settings().anthropic_api_key)
        return self._client

    def generate_structured(
        self,
        system: str,
        user: str,
        tool_name: str,
        tool_description: str,
        input_schema: dict[str, Any],
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Forces the model to respond via a single tool call matching
        `input_schema`, and returns that call's parsed input directly —
        far more reliable than asking the model to emit raw JSON text."""
        client = self._get_client()
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                tools=[{"name": tool_name, "description": tool_description, "input_schema": input_schema}],
                tool_choice={"type": "tool", "name": tool_name},
            )
        except AnthropicAPIError as exc:
            raise AIClientError(f"Anthropic API call failed: {exc}") from exc

        for block in response.content:
            if block.type == "tool_use" and block.name == tool_name:
                return block.input

        raise AIClientError("Model response did not include the expected tool call")

    def generate_with_web_search(
        self,
        system: str,
        user: str,
        max_tokens: int = 2048,
        max_uses: int = 5,
    ) -> dict[str, Any]:
        """Lets the model search the public web via Anthropic's server-side
        `web_search` tool and returns what it actually found — the model
        decides how many searches (if any) it needs, up to `max_uses`.

        Returns `{"text": <the model's final answer text>, "citations":
        [{"url", "title"}, ...]}` — citations come only from real
        `web_search_tool_result` blocks the API returned, never invented.
        An empty `citations` list is a legitimate, honest outcome (the model
        found nothing useful), not a failure."""
        client = self._get_client()
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": max_uses}],
            )
        except AnthropicAPIError as exc:
            raise AIClientError(f"Anthropic API call failed: {exc}") from exc

        text = "".join(block.text for block in response.content if block.type == "text").strip()

        citations: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for block in response.content:
            if block.type != "web_search_tool_result":
                continue
            results = getattr(block, "content", None)
            if not isinstance(results, list):
                continue  # a WebSearchToolResultError (that one search failed) — not a citation list
            for result in results:
                url = getattr(result, "url", None)
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                citations.append({"url": url, "title": getattr(result, "title", None) or ""})

        return {"text": text, "citations": citations}

    def generate_text(self, system: str, user: str, max_tokens: int = 512) -> str:
        client = self._get_client()
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except AnthropicAPIError as exc:
            raise AIClientError(f"Anthropic API call failed: {exc}") from exc

        return "".join(block.text for block in response.content if block.type == "text").strip()

    def ping(self) -> dict[str, Any]:
        """Minimal live connectivity check — a real request, not a fake
        success. Returns a dict that is always safe to expose over the API:
        it never includes the API key, and on failure only reports the
        exception type + HTTP status, never the raw SDK error body (which
        could echo back request details)."""
        if not self.is_configured:
            return {"provider": self.provider, "configured": False, "reachable": False, "message": not_configured_message()}

        client = self._get_client()
        started = time.monotonic()
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=8,
                messages=[{"role": "user", "content": "Reply with exactly one word: pong"}],
            )
        except AnthropicAPIError as exc:
            status_code = getattr(exc, "status_code", None)
            return {
                "provider": self.provider,
                "configured": True,
                "reachable": False,
                "model": self.model,
                "message": f"Anthropic API call failed: {type(exc).__name__}" + (f" (HTTP {status_code})" if status_code else ""),
            }
        except Exception as exc:  # network errors etc. — still never leak the key
            return {
                "provider": self.provider,
                "configured": True,
                "reachable": False,
                "model": self.model,
                "message": f"Anthropic API call failed: {type(exc).__name__}",
            }

        latency_ms = round((time.monotonic() - started) * 1000)
        reply_text = "".join(block.text for block in response.content if block.type == "text").strip()
        return {
            "provider": self.provider,
            "configured": True,
            "reachable": True,
            "model": self.model,
            "latencyMs": latency_ms,
            "message": f"Anthropic API reachable — model replied {reply_text!r} in {latency_ms}ms",
        }


# ---------------------------------------------------------------------------
# Google Gemini
# ---------------------------------------------------------------------------

# Gemini 2.5-generation models "think" before answering and those thinking
# tokens count against `max_output_tokens`. Callers pass small budgets sized
# for the visible answer (they were written for Claude), so the headroom
# below is added on top — otherwise the budget can be spent entirely on
# thinking and the visible answer comes back empty (finish_reason=MAX_TOKENS).
_GEMINI_THINKING_HEADROOM = 8192

# Google Search grounding returns its sources as redirect links through this
# host rather than the page's own address. The discovery pipeline classifies
# and deduplicates sources by hostname, so redirects are resolved before use.
_GOOGLE_REDIRECT_HOST_SUFFIX = "vertexaisearch.cloud.google.com"
_GOOGLE_REDIRECT_PATH_MARKER = "/grounding-api-redirect/"
_REDIRECT_TIMEOUT_SECONDS = 8.0


def is_google_redirect_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    return host.endswith(_GOOGLE_REDIRECT_HOST_SUFFIX) or _GOOGLE_REDIRECT_PATH_MARKER in (parsed.path or "")


def resolve_redirect_url(url: str) -> str | None:
    """Follows a Google grounding redirect to the page it actually points at
    and returns that final URL. Returns `None` — never a guessed address —
    when the redirect can't be followed (network error, timeout) or doesn't
    lead out of Google's redirect service. Only the redirect chain is
    followed; the destination page's body is not downloaded here."""
    try:
        with (
            httpx.Client(follow_redirects=True, timeout=_REDIRECT_TIMEOUT_SECONDS, headers={"User-Agent": USER_AGENT}) as client,
            client.stream("GET", url) as response,
        ):
            final_url = str(response.url)
    except httpx.HTTPError:
        return None

    parsed = urlparse(final_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or is_google_redirect_url(final_url):
        return None
    return final_url


def _gemini_json_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Gemini's `response_json_schema` accepts standard JSON Schema (incl.
    `$defs`/`$ref`/`anyOf`) but not the `default` keyword Pydantic emits for
    optional fields. Defaults are applied by the caller's Pydantic validation
    anyway, so dropping them here changes nothing about the parsed result."""

    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            return {key: strip(value) for key, value in node.items() if key != "default"}
        if isinstance(node, list):
            return [strip(item) for item in node]
        return node

    return strip(copy.deepcopy(schema))


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """Returns the JSON object in `text`, or `None` if it isn't one. Tolerates
    a Markdown code fence around the JSON; never repairs or guesses content."""
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else ""
        if body.rstrip().endswith("```"):
            body = body.rstrip()[:-3]
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _describe_gemini_error(exc: genai_errors.APIError) -> str:
    """Status + Google's own error message — never the request or the key."""
    code = getattr(exc, "code", None)
    status = getattr(exc, "status", None) or type(exc).__name__
    message = getattr(exc, "message", None) or ""
    return f"{code} {status}: {message}".strip() if code else f"{status}: {message}".strip()


class GeminiAIClient(AIClient):
    provider = PROVIDER_GEMINI

    def __init__(self) -> None:
        self._client: genai.Client | None = None

    @property
    def is_configured(self) -> bool:
        return bool(get_settings().gemini_api_key)

    @property
    def model(self) -> str:
        return get_settings().gemini_model

    def _get_client(self) -> genai.Client:
        if not self.is_configured:
            raise AIClientError(not_configured_message())
        if self._client is None:
            self._client = genai.Client(api_key=get_settings().gemini_api_key)
        return self._client

    def _generate(self, contents: str, config: genai_types.GenerateContentConfig) -> genai_types.GenerateContentResponse:
        client = self._get_client()
        try:
            return client.models.generate_content(model=self.model, contents=contents, config=config)
        except genai_errors.APIError as exc:
            raise AIClientError(f"Gemini API call failed: {_describe_gemini_error(exc)}") from exc
        except httpx.HTTPError as exc:  # transport-level failure — still an honest AI failure to callers
            raise AIClientError(f"Gemini API call failed: {type(exc).__name__}") from exc

    @staticmethod
    def _text_of(response: genai_types.GenerateContentResponse) -> str:
        """The visible answer only — the SDK's `.text` already excludes
        thinking parts. `None` (no candidates / no text parts) becomes ''."""
        try:
            text = response.text
        except Exception:  # the SDK raises on some malformed/blocked responses rather than returning None
            text = None
        return (text or "").strip()

    @staticmethod
    def _finish_reason(response: genai_types.GenerateContentResponse) -> str:
        candidates = getattr(response, "candidates", None) or []
        if not candidates:
            return "NO_CANDIDATES"
        reason = getattr(candidates[0], "finish_reason", None)
        return getattr(reason, "name", None) or (str(reason) if reason else "UNKNOWN")

    def generate_structured(
        self,
        system: str,
        user: str,
        tool_name: str,
        tool_description: str,
        input_schema: dict[str, Any],
        max_tokens: int = 1024,
    ) -> dict[str, Any]:
        """Gemini structured output: the response is constrained to JSON
        matching `input_schema` and the parsed object is returned directly,
        so callers get exactly what the Anthropic tool-call path gave them.
        `tool_name` has no Gemini equivalent; `tool_description` is folded
        into the instructions so its intent isn't lost. A malformed or empty
        answer is retried once (bounded, cheap) and then raised as
        `AIClientError` — never patched up or guessed."""
        config = genai_types.GenerateContentConfig(
            system_instruction=f"{system}\n\nRespond with exactly one JSON object and nothing else. Purpose of the object: {tool_description}",
            max_output_tokens=max_tokens + _GEMINI_THINKING_HEADROOM,
            response_mime_type="application/json",
            response_json_schema=_gemini_json_schema(input_schema),
        )

        last_error = "Model response was empty"
        for _ in range(2):  # one attempt + one bounded retry
            response = self._generate(user, config)
            parsed = _parse_json_object(self._text_of(response))
            if parsed is not None:
                return parsed
            last_error = f"Model response was not a JSON object matching the schema (finish reason: {self._finish_reason(response)})"

        raise AIClientError(last_error)

    def generate_with_web_search(
        self,
        system: str,
        user: str,
        max_tokens: int = 2048,
        max_uses: int = 5,
    ) -> dict[str, Any]:
        """Gemini Google Search grounding. Returns the same shape as the
        Anthropic path: `{"text", "citations": [{"url", "title"}, ...]}`.

        Citations come only from the grounding metadata the API returned.
        Google supplies them as redirect links, so each one is resolved to
        the real page URL first (the discovery pipeline classifies and
        deduplicates by hostname); a link that cannot be resolved is dropped,
        not guessed at. `max_uses` has no Gemini equivalent — the model
        decides how many searches to run inside one grounded request — so it
        is accepted for signature compatibility and ignored."""
        config = genai_types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens + _GEMINI_THINKING_HEADROOM,
            tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
        )
        response = self._generate(user, config)
        text = self._text_of(response)

        citations: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        unresolved = 0
        for chunk in self._grounding_chunks(response):
            web = getattr(chunk, "web", None)
            uri = getattr(web, "uri", None) if web is not None else None
            if not uri:
                continue  # retrieved_context / maps / image chunks are not public web sources
            url = resolve_redirect_url(uri) if is_google_redirect_url(uri) else uri
            if not url:
                unresolved += 1
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            citations.append({"url": url, "title": getattr(web, "title", None) or ""})

        if unresolved:
            logger.warning("Dropped %d grounding source(s) whose Google redirect could not be resolved to a real page URL.", unresolved)

        return {"text": text, "citations": citations}

    @staticmethod
    def _grounding_chunks(response: genai_types.GenerateContentResponse) -> list[Any]:
        chunks: list[Any] = []
        for candidate in getattr(response, "candidates", None) or []:
            metadata = getattr(candidate, "grounding_metadata", None)
            chunks.extend(getattr(metadata, "grounding_chunks", None) or [])
        return chunks

    def generate_text(self, system: str, user: str, max_tokens: int = 512) -> str:
        config = genai_types.GenerateContentConfig(
            system_instruction=system,
            max_output_tokens=max_tokens + _GEMINI_THINKING_HEADROOM,
        )
        return self._text_of(self._generate(user, config))

    def ping(self) -> dict[str, Any]:
        """Minimal live connectivity check — one tiny real request. The
        returned dict never includes the API key; on failure it reports only
        the exception type + HTTP status, never Google's raw error body."""
        if not self.is_configured:
            return {"provider": self.provider, "configured": False, "reachable": False, "message": not_configured_message()}

        client = self._get_client()
        started = time.monotonic()
        try:
            response = client.models.generate_content(
                model=self.model,
                contents="Reply with exactly one word: pong",
                config=genai_types.GenerateContentConfig(max_output_tokens=8 + _GEMINI_THINKING_HEADROOM),
            )
        except genai_errors.APIError as exc:
            code = getattr(exc, "code", None)
            return {
                "provider": self.provider,
                "configured": True,
                "reachable": False,
                "model": self.model,
                "message": f"Gemini API call failed: {type(exc).__name__}" + (f" (HTTP {code})" if code else ""),
            }
        except Exception as exc:  # network errors etc. — still never leak the key
            return {
                "provider": self.provider,
                "configured": True,
                "reachable": False,
                "model": self.model,
                "message": f"Gemini API call failed: {type(exc).__name__}",
            }

        latency_ms = round((time.monotonic() - started) * 1000)
        reply_text = self._text_of(response)
        return {
            "provider": self.provider,
            "configured": True,
            "reachable": True,
            "model": self.model,
            "latencyMs": latency_ms,
            "message": f"Gemini API reachable — model replied {reply_text!r} in {latency_ms}ms",
        }


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------


def build_ai_client(settings: Settings | None = None) -> AIClient:
    settings = settings or get_settings()
    if settings.ai_provider == PROVIDER_GEMINI:
        return GeminiAIClient()
    if settings.ai_provider == PROVIDER_ANTHROPIC:
        return AnthropicAIClient()
    raise AIClientError(f"Unsupported AI_PROVIDER={settings.ai_provider!r}; expected one of {SUPPORTED_PROVIDERS}")


_singleton: AIClient | None = None


def get_ai_client() -> AIClient:
    """The process-wide client for the configured provider. Rebuilt if
    `AI_PROVIDER` changes underneath it (settings are patched in tests)."""
    global _singleton
    provider = get_settings().ai_provider
    if _singleton is None or _singleton.provider != provider:
        _singleton = build_ai_client()
    return _singleton
