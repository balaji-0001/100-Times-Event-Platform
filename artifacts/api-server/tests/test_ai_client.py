"""Unit tests for the provider-neutral AI wrapper (`ai_client.py`).

Every vendor SDK call is stubbed at the client boundary — nothing here touches
the network, and no test can spend API credits. The Gemini tests build real
`google.genai.types` response objects so the parsing code is exercised against
the SDK's actual data model, not a hand-rolled imitation of it."""

from types import SimpleNamespace

import anthropic
import httpx
import pytest
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from backend.core.config import get_settings
from backend.services.social_agent import ai_client as ai
from backend.services.social_agent.ai_client import (
    AIClientError,
    AnthropicAIClient,
    GeminiAIClient,
    build_ai_client,
    get_ai_client,
    is_google_redirect_url,
    not_configured_message,
    resolve_redirect_url,
)

REDIRECT_A = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEaaa"
REDIRECT_B = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEbbb"
DIRECT = "https://www.iitb.ac.in/techfest-2026"
RESOLVED_A = "https://www.example-expo.in/events/expo-2026"


# --- stubs -----------------------------------------------------------------


class _StubModels:
    """Stands in for `genai.Client().models`; records every call, returns the
    queued responses in order, or raises a queued exception."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _StubGenaiClient:
    def __init__(self, responses):
        self.models = _StubModels(responses)


def _gemini_response(text=None, *, chunks=(), finish=genai_types.FinishReason.STOP, thought=None, extra_chunks=()):
    parts = []
    if thought:
        parts.append(genai_types.Part(text=thought, thought=True))
    if text is not None:
        parts.append(genai_types.Part(text=text))
    grounding = None
    if chunks or extra_chunks:
        web_chunks = [genai_types.GroundingChunk(web=genai_types.GroundingChunkWeb(uri=uri, title=title)) for uri, title in chunks]
        grounding = genai_types.GroundingMetadata(grounding_chunks=web_chunks + list(extra_chunks))
    return genai_types.GenerateContentResponse(
        candidates=[genai_types.Candidate(content=genai_types.Content(role="model", parts=parts), finish_reason=finish, grounding_metadata=grounding)]
    )


@pytest.fixture()
def gemini(monkeypatch):
    """A GeminiAIClient wired to a stub SDK client. Redirect resolution is
    blocked by default so a test must opt in to it explicitly."""
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-key-never-sent")
    monkeypatch.setattr(settings, "gemini_model", "gemini-test-model")
    monkeypatch.setattr(ai, "resolve_redirect_url", lambda url: pytest.fail(f"unexpected redirect resolution for {url}"))

    def factory(responses):
        client = GeminiAIClient()
        stub = _StubGenaiClient(responses)
        monkeypatch.setattr(client, "_get_client", lambda: stub)
        return client, stub.models

    return factory


# --- Gemini: text generation -----------------------------------------------


def test_gemini_text_generation(gemini):
    client, models = gemini([_gemini_response("Hello from Gemini")])

    assert client.generate_text(system="be brief", user="say hi", max_tokens=100) == "Hello from Gemini"

    call = models.calls[0]
    assert call["model"] == "gemini-test-model"
    assert call["contents"] == "say hi"
    assert call["config"].system_instruction == "be brief"
    assert call["config"].max_output_tokens > 100  # thinking headroom on top of the caller's budget


def test_gemini_text_ignores_thought_parts_and_treats_empty_as_empty(gemini):
    client, _ = gemini([
        _gemini_response("visible", thought="hidden reasoning"),
        _gemini_response(None, thought="only thinking"),
        genai_types.GenerateContentResponse(candidates=[]),
    ])

    assert client.generate_text(system="s", user="u") == "visible"
    assert client.generate_text(system="s", user="u") == ""
    assert client.generate_text(system="s", user="u") == ""


# --- Gemini: structured extraction -----------------------------------------


SCHEMA = {
    "type": "object",
    "properties": {"event_name": {"type": "string", "default": ""}, "confidence_score": {"type": "integer", "minimum": 0, "maximum": 100}},
    "required": ["confidence_score"],
}


def test_gemini_structured_extraction_returns_parsed_object(gemini):
    client, models = gemini([_gemini_response('{"event_name": "Pune Tech Expo", "confidence_score": 82}')])

    result = client.generate_structured(system="extract", user="page text", tool_name="extract_event", tool_description="Facts about one event", input_schema=SCHEMA)

    assert result == {"event_name": "Pune Tech Expo", "confidence_score": 82}
    config = models.calls[0]["config"]
    assert config.response_mime_type == "application/json"
    assert "Facts about one event" in config.system_instruction
    assert config.response_json_schema["required"] == ["confidence_score"]
    assert "default" not in config.response_json_schema["properties"]["event_name"]
    assert "default" in SCHEMA["properties"]["event_name"]  # the caller's schema is not mutated


def test_gemini_structured_tolerates_code_fence(gemini):
    client, _ = gemini([_gemini_response('```json\n{"confidence_score": 5}\n```')])

    assert client.generate_structured(system="s", user="u", tool_name="t", tool_description="d", input_schema=SCHEMA) == {"confidence_score": 5}


def test_gemini_structured_retries_once_on_malformed_output(gemini):
    client, models = gemini([_gemini_response("not json at all"), _gemini_response('{"confidence_score": 1}')])

    assert client.generate_structured(system="s", user="u", tool_name="t", tool_description="d", input_schema=SCHEMA) == {"confidence_score": 1}
    assert len(models.calls) == 2


def test_gemini_structured_raises_after_second_malformed_output(gemini):
    client, models = gemini([_gemini_response("[1, 2, 3]"), _gemini_response("still not an object")])

    with pytest.raises(AIClientError, match="not a JSON object"):
        client.generate_structured(system="s", user="u", tool_name="t", tool_description="d", input_schema=SCHEMA)
    assert len(models.calls) == 2


def test_gemini_structured_empty_response_reports_finish_reason(gemini):
    truncated = _gemini_response(None, thought="ran out of budget", finish=genai_types.FinishReason.MAX_TOKENS)
    client, _ = gemini([truncated, truncated])

    with pytest.raises(AIClientError, match="MAX_TOKENS"):
        client.generate_structured(system="s", user="u", tool_name="t", tool_description="d", input_schema=SCHEMA)


# --- Gemini: web research / grounding --------------------------------------


def test_gemini_grounding_sources_are_resolved_deduplicated_and_never_invented(gemini, monkeypatch):
    resolutions = {REDIRECT_A: RESOLVED_A, REDIRECT_B: None}
    monkeypatch.setattr(ai, "resolve_redirect_url", lambda url: resolutions[url])
    client, models = gemini([
        _gemini_response("Found two expos.", chunks=[(REDIRECT_A, "Expo 2026"), (DIRECT, "Techfest"), (REDIRECT_B, "Unresolvable"), (REDIRECT_A, "Expo 2026 again")])
    ])

    result = client.generate_with_web_search(system="find events", user="Search query: tech expo Pune 2026", max_uses=3)

    assert result["text"] == "Found two expos."
    assert result["citations"] == [
        {"url": RESOLVED_A, "title": "Expo 2026"},  # redirect resolved to the real host
        {"url": DIRECT, "title": "Techfest"},  # direct URL passed through untouched
    ]  # REDIRECT_B dropped (unresolvable), duplicate of REDIRECT_A dropped
    config = models.calls[0]["config"]
    assert config.tools and config.tools[0].google_search is not None
    assert config.system_instruction == "find events"


def test_gemini_grounding_with_no_metadata_or_non_web_chunks_yields_no_citations(gemini):
    non_web = genai_types.GroundingChunk(retrieved_context=genai_types.GroundingChunkRetrievedContext(uri="gs://bucket/doc", title="internal doc"))
    client, _ = gemini([_gemini_response("nothing found"), _gemini_response("only internal", extra_chunks=[non_web])])

    assert client.generate_with_web_search(system="s", user="u") == {"text": "nothing found", "citations": []}
    assert client.generate_with_web_search(system="s", user="u") == {"text": "only internal", "citations": []}


# --- redirect resolution ---------------------------------------------------


def test_is_google_redirect_url():
    assert is_google_redirect_url(REDIRECT_A)
    assert is_google_redirect_url("https://other.google.com/grounding-api-redirect/xyz")
    assert not is_google_redirect_url(DIRECT)
    assert not is_google_redirect_url("https://www.google.com/search?q=events")


_REAL_HTTPX_CLIENT = httpx.Client  # captured once, so patching twice in one test never wraps the previous patch


def _patch_httpx_client(monkeypatch, handler):
    monkeypatch.setattr(ai.httpx, "Client", lambda **kwargs: _REAL_HTTPX_CLIENT(transport=httpx.MockTransport(handler), **kwargs))


def test_resolve_redirect_url_follows_to_final_page(monkeypatch):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.host == "vertexaisearch.cloud.google.com":
            return httpx.Response(302, headers={"location": RESOLVED_A})
        return httpx.Response(403, text="bot blocked")  # destination status must not matter

    _patch_httpx_client(monkeypatch, handler)

    assert resolve_redirect_url(REDIRECT_A) == RESOLVED_A
    assert seen == [REDIRECT_A, RESOLVED_A]


def test_resolve_redirect_url_returns_none_when_it_cannot_leave_google_or_on_error(monkeypatch):
    _patch_httpx_client(monkeypatch, lambda request: httpx.Response(500, text="redirect service error"))
    assert resolve_redirect_url(REDIRECT_A) is None

    def broken(request):
        raise httpx.ConnectError("network down", request=request)

    _patch_httpx_client(monkeypatch, broken)
    assert resolve_redirect_url(REDIRECT_A) is None


# --- Gemini: failures --------------------------------------------------------


def test_gemini_api_error_becomes_ai_client_error_without_leaking_the_key(gemini):
    api_error = genai_errors.ClientError(400, {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT"}})
    client, _ = gemini([api_error])

    with pytest.raises(AIClientError) as excinfo:
        client.generate_text(system="s", user="u")

    message = str(excinfo.value)
    assert message.startswith("Gemini API call failed: 400 INVALID_ARGUMENT")
    assert "test-key-never-sent" not in message


def test_gemini_network_error_becomes_ai_client_error(gemini):
    client, _ = gemini([httpx.ConnectError("boom")])

    with pytest.raises(AIClientError, match="Gemini API call failed: ConnectError"):
        client.generate_structured(system="s", user="u", tool_name="t", tool_description="d", input_schema=SCHEMA)


def test_gemini_missing_api_key(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", None)
    client = GeminiAIClient()

    assert client.is_configured is False
    with pytest.raises(AIClientError, match=r"AI provider is not configured \(AI_PROVIDER=gemini requires GEMINI_API_KEY\)"):
        client.generate_text(system="s", user="u")
    with pytest.raises(AIClientError):
        client.generate_with_web_search(system="s", user="u")
    assert client.ping() == {"provider": "gemini", "configured": False, "reachable": False, "message": not_configured_message()}


# --- Gemini: connectivity ping ------------------------------------------------


def test_gemini_ping_success(gemini):
    client, models = gemini([_gemini_response("pong")])

    result = client.ping()

    assert result["provider"] == "gemini"
    assert result["configured"] is True and result["reachable"] is True
    assert result["model"] == "gemini-test-model"
    assert isinstance(result["latencyMs"], int)
    assert "'pong'" in result["message"]
    assert models.calls[0]["contents"] == "Reply with exactly one word: pong"


def test_gemini_ping_failure_is_sanitized(gemini):
    client, _ = gemini([genai_errors.ClientError(403, {"error": {"message": "secret-ish raw body", "status": "PERMISSION_DENIED"}})])

    result = client.ping()

    assert result["configured"] is True and result["reachable"] is False
    assert result["message"] == "Gemini API call failed: ClientError (HTTP 403)"
    assert "secret-ish" not in result["message"]


# --- provider selection ------------------------------------------------------


def test_provider_selection_follows_settings(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(ai, "_singleton", None)

    monkeypatch.setattr(settings, "ai_provider", "gemini")
    first = get_ai_client()
    assert isinstance(first, GeminiAIClient) and first.provider == "gemini"
    assert get_ai_client() is first  # cached while the provider is unchanged

    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    second = get_ai_client()
    assert isinstance(second, AnthropicAIClient) and second.provider == "anthropic"

    monkeypatch.setattr(settings, "ai_provider", "openai")
    with pytest.raises(AIClientError, match="Unsupported AI_PROVIDER"):
        build_ai_client()


def test_not_configured_message_names_the_selected_provider(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    assert not_configured_message() == "AI provider is not configured (AI_PROVIDER=anthropic requires ANTHROPIC_API_KEY)"
    monkeypatch.setattr(settings, "ai_provider", "gemini")
    assert not_configured_message() == "AI provider is not configured (AI_PROVIDER=gemini requires GEMINI_API_KEY)"


def test_settings_reject_unknown_provider():
    from backend.core.config import Settings

    with pytest.raises(ValueError, match="AI_PROVIDER must be"):
        Settings(ai_provider="openai")
    assert Settings(ai_provider=" Gemini ").ai_provider == "gemini"


# --- Anthropic provider still works ------------------------------------------


class _StubMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture()
def anthropic_client(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "ai_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key-never-sent")
    monkeypatch.setattr(settings, "anthropic_model", "claude-test-model")

    def factory(responses):
        client = AnthropicAIClient()
        stub = SimpleNamespace(messages=_StubMessages(responses))
        monkeypatch.setattr(client, "_get_client", lambda: stub)
        return client, stub.messages

    return factory


def test_anthropic_structured_text_and_web_search_still_work(anthropic_client):
    tool_call = SimpleNamespace(content=[SimpleNamespace(type="tool_use", name="extract_event", input={"confidence_score": 77})])
    plain = SimpleNamespace(content=[SimpleNamespace(type="text", text="  hello  ")])
    searched = SimpleNamespace(content=[
        SimpleNamespace(type="text", text="Found it."),
        SimpleNamespace(type="web_search_tool_result", content=SimpleNamespace(type="web_search_tool_result_error", error_code="max_uses_exceeded")),
        SimpleNamespace(type="web_search_tool_result", content=[SimpleNamespace(url=DIRECT, title="Techfest"), SimpleNamespace(url=DIRECT, title="dup")]),
    ])
    client, messages = anthropic_client([tool_call, plain, searched])

    assert client.generate_structured(system="s", user="u", tool_name="extract_event", tool_description="d", input_schema=SCHEMA) == {"confidence_score": 77}
    assert messages.calls[0]["tool_choice"] == {"type": "tool", "name": "extract_event"}
    assert messages.calls[0]["model"] == "claude-test-model"
    assert client.generate_text(system="s", user="u") == "hello"
    assert client.generate_with_web_search(system="s", user="u", max_uses=2) == {"text": "Found it.", "citations": [{"url": DIRECT, "title": "Techfest"}]}
    assert messages.calls[2]["tools"][0]["max_uses"] == 2


def test_anthropic_errors_and_missing_key(anthropic_client, monkeypatch):
    api_error = anthropic.APIError("upstream failure", httpx.Request("POST", "https://api.anthropic.com/v1/messages"), body=None)
    client, _ = anthropic_client([api_error])
    with pytest.raises(AIClientError, match="Anthropic API call failed"):
        client.generate_text(system="s", user="u")

    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    assert client.is_configured is False
    assert client.ping() == {"provider": "anthropic", "configured": False, "reachable": False, "message": "AI provider is not configured (AI_PROVIDER=anthropic requires ANTHROPIC_API_KEY)"}
