from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, Literal, cast

import httpx
from pydantic import BaseModel, ValidationError

from app.llm.provider import (
    LLMMessage,
    LLMProviderError,
    LLMResponse,
    LLMUsage,
)

StructuredOutputMode = Literal["json_schema", "json_object", "prompt"]


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        api_base: str,
        api_key: str,
        structured_output_mode: StructuredOutputMode = "json_schema",
        max_retries: int = 2,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_base.startswith(("http://", "https://")):
            raise ValueError("api_base must be an HTTP(S) URL")
        if not api_key:
            raise ValueError("api_key must not be empty")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        self._endpoint = f"{api_base.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._structured_output_mode = structured_output_mode
        self._max_retries = max_retries
        self._client = client or httpx.Client()
        self._owns_client = client is None
        self._sleep = sleep

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def generate_structured[ResponseT: BaseModel](
        self,
        *,
        messages: list[LLMMessage],
        response_schema: type[ResponseT],
        model: str,
        temperature: float,
        timeout_seconds: int,
        max_output_tokens: int,
    ) -> LLMResponse[ResponseT]:
        if not messages:
            raise ValueError("messages must not be empty")
        payload = self._build_payload(
            messages=messages,
            response_schema=response_schema,
            model=model,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        started = time.monotonic()
        response = self._post_with_retry(payload, timeout_seconds=timeout_seconds)
        latency_ms = round((time.monotonic() - started) * 1000)
        return self._parse_response(
            response,
            response_schema=response_schema,
            fallback_model=model,
            latency_ms=latency_ms,
        )

    def _build_payload(
        self,
        *,
        messages: list[LLMMessage],
        response_schema: type[BaseModel],
        model: str,
        temperature: float,
        max_output_tokens: int,
    ) -> dict[str, Any]:
        serialized_messages = [message.model_dump(exclude_none=True) for message in messages]
        schema = response_schema.model_json_schema()
        if self._structured_output_mode == "prompt":
            serialized_messages.insert(
                0,
                {
                    "role": "system",
                    "content": (
                        "Return only one JSON object matching this JSON Schema. "
                        f"Do not wrap it in Markdown: {schema}"
                    ),
                },
            )
            response_format: dict[str, Any] | None = None
        elif self._structured_output_mode == "json_object":
            response_format = {"type": "json_object"}
        else:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema.__name__,
                    "strict": True,
                    "schema": schema,
                },
            }
        payload: dict[str, Any] = {
            "model": model,
            "messages": serialized_messages,
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
        if response_format is not None:
            payload["response_format"] = response_format
        return payload

    def _post_with_retry(
        self,
        payload: dict[str, Any],
        *,
        timeout_seconds: int,
    ) -> httpx.Response:
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(
                    self._endpoint,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=timeout_seconds,
                )
            except httpx.TimeoutException as exc:
                if attempt < self._max_retries:
                    self._sleep(self._retry_delay(attempt, None))
                    continue
                raise LLMProviderError(
                    "LLM_TIMEOUT",
                    "LLM provider request timed out",
                    retryable=True,
                ) from exc
            except httpx.TransportError as exc:
                if attempt < self._max_retries:
                    self._sleep(self._retry_delay(attempt, None))
                    continue
                raise LLMProviderError(
                    "LLM_NETWORK_ERROR",
                    "LLM provider is unreachable",
                    retryable=True,
                ) from exc

            error = self._http_error(response)
            if error is None:
                return response
            if error.retryable and attempt < self._max_retries:
                self._sleep(self._retry_delay(attempt, response.headers.get("Retry-After")))
                continue
            raise error
        raise AssertionError("retry loop did not return or raise")

    @staticmethod
    def _http_error(response: httpx.Response) -> LLMProviderError | None:
        status = response.status_code
        if status < 400:
            return None
        if status in {401, 403}:
            return LLMProviderError(
                "LLM_AUTHENTICATION_FAILED",
                "LLM provider rejected the configured credentials",
                retryable=False,
                status_code=status,
            )
        if status == 429:
            return LLMProviderError(
                "LLM_RATE_LIMITED",
                "LLM provider rate limit was reached",
                retryable=True,
                status_code=status,
            )
        if status >= 500:
            return LLMProviderError(
                "LLM_PROVIDER_UNAVAILABLE",
                "LLM provider is temporarily unavailable",
                retryable=True,
                status_code=status,
            )
        return LLMProviderError(
            "LLM_REQUEST_REJECTED",
            f"LLM provider rejected the request with status {status}",
            retryable=False,
            status_code=status,
        )

    @staticmethod
    def _retry_delay(attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(max(float(retry_after), 0.0), 10.0)
            except ValueError:
                pass
        return min(0.5 * (2.0**attempt), 4.0)

    @staticmethod
    def _parse_response[ResponseT: BaseModel](
        response: httpx.Response,
        *,
        response_schema: type[ResponseT],
        fallback_model: str,
        latency_ms: int,
    ) -> LLMResponse[ResponseT]:
        try:
            body = response.json()
            if not isinstance(body, dict):
                raise TypeError
            choices = body["choices"]
            if not isinstance(choices, list) or not choices:
                raise TypeError
            choice = choices[0]
            if not isinstance(choice, dict):
                raise TypeError
            message = choice["message"]
            if not isinstance(message, dict):
                raise TypeError
            content = message["content"]
            if not isinstance(content, str):
                raise TypeError
            parsed = response_schema.model_validate_json(content)
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            raise LLMProviderError(
                "LLM_INVALID_RESPONSE",
                "LLM provider returned a response that does not match the required schema",
                retryable=False,
                status_code=response.status_code,
            ) from exc

        usage_raw = body.get("usage", {})
        usage = cast(dict[str, object], usage_raw) if isinstance(usage_raw, dict) else {}
        request_id = response.headers.get("x-request-id")
        if request_id is None and isinstance(body.get("id"), str):
            request_id = cast(str, body["id"])
        model = body.get("model") if isinstance(body.get("model"), str) else fallback_model
        finish_reason = choice.get("finish_reason")
        return LLMResponse(
            provider="openai_compatible",
            model=cast(str, model),
            request_id=request_id,
            content=parsed,
            usage=LLMUsage(
                input_tokens=_non_negative_int(usage.get("prompt_tokens")),
                output_tokens=_non_negative_int(usage.get("completion_tokens")),
            ),
            finish_reason=finish_reason if isinstance(finish_reason, str) else "unknown",
            latency_ms=latency_ms,
        )


def _non_negative_int(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else 0
