from __future__ import annotations

import json

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from app.llm.factory import get_llm_provider
from app.llm.openai_compatible import OpenAICompatibleProvider
from app.llm.provider import FakeLLMProvider, LLMMessage, LLMProviderError


class ExampleResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str


MESSAGES = [LLMMessage(role="user", content="Summarize the evidence")]


def provider_with_handler(
    handler,
    *,
    max_retries: int = 0,
    sleeps: list[float] | None = None,
) -> OpenAICompatibleProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenAICompatibleProvider(
        api_base="https://provider.example/v1",
        api_key="private-key",
        max_retries=max_retries,
        client=client,
        sleep=(sleeps.append if sleeps is not None else lambda _: None),
    )


def generate(provider: OpenAICompatibleProvider):
    return provider.generate_structured(
        messages=MESSAGES,
        response_schema=ExampleResponse,
        model="analysis-model",
        temperature=0.1,
        timeout_seconds=30,
        max_output_tokens=256,
    )


def success_response(*, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        headers=headers,
        json={
            "id": "provider-request",
            "model": "resolved-model",
            "choices": [
                {
                    "message": {"role": "assistant", "content": '{"answer":"ok"}'},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 11, "completion_tokens": 4},
        },
    )


def test_fake_provider_validates_and_records_structured_response() -> None:
    provider = FakeLLMProvider([{"answer": "grounded"}])

    response = provider.generate_structured(
        messages=MESSAGES,
        response_schema=ExampleResponse,
        model="fake-analysis",
        temperature=0.1,
        timeout_seconds=20,
        max_output_tokens=100,
    )

    assert response.content.answer == "grounded"
    assert response.provider == "fake"
    assert provider.calls[0].schema_name == "ExampleResponse"


def test_provider_factory_returns_none_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("LLM_ENABLED", "false")
    get_settings.cache_clear()
    get_llm_provider.cache_clear()
    try:
        assert get_llm_provider() is None
    finally:
        get_llm_provider.cache_clear()
        get_settings.cache_clear()


def test_provider_factory_builds_configured_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_API_BASE", "https://provider.example/v1")
    monkeypatch.setenv("LLM_API_KEY", "private-key")
    monkeypatch.setenv("LLM_MODEL", "analysis-model")
    get_settings.cache_clear()
    get_llm_provider.cache_clear()
    try:
        provider = get_llm_provider()
        assert isinstance(provider, OpenAICompatibleProvider)
        provider.close()
    finally:
        get_llm_provider.cache_clear()
        get_settings.cache_clear()


def test_fake_provider_rejects_schema_mismatch() -> None:
    provider = FakeLLMProvider([{"unexpected": "value"}])

    with pytest.raises(LLMProviderError) as captured:
        provider.generate_structured(
            messages=MESSAGES,
            response_schema=ExampleResponse,
            model="fake-analysis",
            temperature=0.1,
            timeout_seconds=20,
            max_output_tokens=100,
        )

    assert captured.value.code == "LLM_INVALID_RESPONSE"
    assert captured.value.retryable is False


def test_openai_compatible_provider_sends_json_schema_and_parses_usage() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return success_response(headers={"x-request-id": "header-request"})

    response = generate(provider_with_handler(handler))

    payload = json.loads(requests[0].content)
    assert requests[0].url == "https://provider.example/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer private-key"
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert response.content.answer == "ok"
    assert response.request_id == "header-request"
    assert response.model == "resolved-model"
    assert response.usage.total_tokens == 15


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [
        (401, "LLM_AUTHENTICATION_FAILED", False),
        (403, "LLM_AUTHENTICATION_FAILED", False),
        (400, "LLM_REQUEST_REJECTED", False),
        (429, "LLM_RATE_LIMITED", True),
        (503, "LLM_PROVIDER_UNAVAILABLE", True),
    ],
)
def test_provider_maps_safe_http_errors(status: int, code: str, retryable: bool) -> None:
    provider = provider_with_handler(
        lambda _: httpx.Response(status, text="response body must not leak")
    )

    with pytest.raises(LLMProviderError) as captured:
        generate(provider)

    assert captured.value.code == code
    assert captured.value.retryable is retryable
    assert "response body must not leak" not in captured.value.message
    assert "private-key" not in captured.value.message


def test_rate_limit_retries_and_honors_retry_after() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "1.25"})
        return success_response()

    response = generate(provider_with_handler(handler, max_retries=1, sleeps=sleeps))

    assert response.content.answer == "ok"
    assert attempts == 2
    assert sleeps == [1.25]


@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (httpx.ReadTimeout("slow provider"), "LLM_TIMEOUT"),
        (httpx.ConnectError("offline"), "LLM_NETWORK_ERROR"),
    ],
)
def test_transport_errors_are_safe_and_retryable(
    exception: httpx.TransportError,
    code: str,
) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise exception

    with pytest.raises(LLMProviderError) as captured:
        generate(provider_with_handler(handler))

    assert captured.value.code == code
    assert captured.value.retryable is True
    assert str(exception) not in captured.value.message


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not-json"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": '{"unexpected":"value"}'}, "finish_reason": "stop"}
                ]
            },
        ),
    ],
)
def test_malformed_or_schema_invalid_response_is_rejected(response: httpx.Response) -> None:
    with pytest.raises(LLMProviderError) as captured:
        generate(provider_with_handler(lambda _: response))

    assert captured.value.code == "LLM_INVALID_RESPONSE"
    assert captured.value.retryable is False
