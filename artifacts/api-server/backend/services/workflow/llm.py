"""LangChain path for structured LLM calls.

`structured_llm(...)` returns a LangChain Runnable (`str -> Model`) that sends
a prompt through the existing provider-neutral `ai_client` — so Gemini vs
Anthropic selection, key handling and the "only return what the model said"
rule stay in that one place — validates the reply against a Pydantic model,
and retries once when the model's output fails validation. Configuration and
API failures (`AIClientError`) are not retried: they are not transient, and
retrying a missing key would only spend time, never fix anything.

The existing agents keep their own (already working) calls; this is the
LangChain-shaped building block for any new workflow step that needs a
structured answer.
"""

from typing import TypeVar

from langchain_core.runnables import Runnable, RunnableLambda
from pydantic import BaseModel, ValidationError

from backend.services.social_agent.ai_client import AIClientError, get_ai_client, not_configured_message

ModelT = TypeVar("ModelT", bound=BaseModel)


def structured_llm(
    schema: type[ModelT],
    *,
    system: str,
    tool_name: str,
    tool_description: str,
    max_tokens: int = 1024,
    max_attempts: int = 2,
) -> Runnable[str, ModelT]:
    """A Runnable whose input is the user prompt and whose output is a
    validated `schema` instance. `tool_name`/`tool_description` are the same
    hints the rest of the codebase passes to `generate_structured`."""

    def call(user: str) -> ModelT:
        client = get_ai_client()
        if not client.is_configured:
            raise AIClientError(not_configured_message())
        raw = client.generate_structured(
            system=system,
            user=user,
            tool_name=tool_name,
            tool_description=tool_description,
            input_schema=schema.model_json_schema(),
            max_tokens=max_tokens,
        )
        return schema.model_validate(raw)

    return RunnableLambda(call, name=f"structured:{tool_name}").with_retry(
        retry_if_exception_type=(ValidationError,),
        wait_exponential_jitter=False,
        stop_after_attempt=max_attempts,
    )
