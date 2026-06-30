# File Path: backend/app/services/gateway_provider.py
# Timestamp: 2026-05-25T12:00:00+08:00
# Version: v0.1

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings


class ProviderCallError(Exception):
    def __init__(self, message: str, retryable: bool, provider_status: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.provider_status = provider_status


@dataclass
class ProviderCallResult:
    answer: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int
    raw_payload: dict


class ProviderGatewayClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        timeout = httpx.Timeout(
            timeout=float(self.settings.gateway_provider_timeout_seconds),
            connect=float(self.settings.gateway_connect_timeout_seconds),
        )
        self.http_client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self.http_client.aclose()

    @retry(
        stop=stop_after_attempt(get_settings().gateway_retry_max + 1),
        wait=wait_exponential(multiplier=0.2, min=0.2, max=2),
        retry=retry_if_exception_type(ProviderCallError),
        reraise=True,
    )
    async def call_model(
        self,
        *,
        provider_base_url: str,
        model_code: str,
        api_key: str,
        message: str,
    ) -> ProviderCallResult:
        if self.settings.gateway_mock_provider:
            input_tokens = max(1, len(message) // 4)
            output_tokens = max(16, input_tokens // 3)
            latency_ms = 120
            answer = f"[mock:{model_code}] {message[:256]}"
            payload = {
                "model": model_code,
                "mock": True,
                "created_at": datetime.now(UTC).isoformat(),
            }
            return ProviderCallResult(
                answer=answer,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=input_tokens + output_tokens,
                latency_ms=latency_ms,
                raw_payload=payload,
            )

        endpoint = provider_base_url.rstrip("/") + "/chat/completions"
        body = {
            "model": model_code,
            "messages": [{"role": "user", "content": message}],
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        start_at = datetime.now(UTC)
        try:
            response = await self.http_client.post(endpoint, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise ProviderCallError("Provider timeout", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise ProviderCallError("Provider network error", retryable=True) from exc

        latency_ms = int((datetime.now(UTC) - start_at).total_seconds() * 1000)

        if response.status_code in {429, 500, 502, 503, 504}:
            raise ProviderCallError("Provider transient error", retryable=True, provider_status=response.status_code)
        if response.status_code >= 400:
            raise ProviderCallError("Provider request failed", retryable=False, provider_status=response.status_code)

        payload = response.json()
        choices = payload.get("choices") or []
        answer = ""
        if choices:
            answer = choices[0].get("message", {}).get("content", "") or ""

        usage = payload.get("usage") or {}
        input_tokens = int(usage.get("prompt_tokens") or 0)
        output_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (input_tokens + output_tokens))

        return ProviderCallResult(
            answer=answer,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            latency_ms=latency_ms,
            raw_payload=payload,
        )
