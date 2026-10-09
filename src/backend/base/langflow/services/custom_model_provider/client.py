from __future__ import annotations

import json
from typing import Any

import httpx
from lfx.utils.ssrf_httpx import ssrf_protected_strict_httpx_client_kwargs_for_url

from .service import normalize_base_url

DISCOVERY_TIMEOUT_SECONDS = 5.0
MAX_DISCOVERY_BYTES = 1_000_000


class ModelDiscoveryError(RuntimeError):
    """A safe, user-facing model discovery failure."""


def models_url(base_url: str) -> str:
    normalized = normalize_base_url(base_url)
    return f"{normalized}/models" if normalized.endswith("/v1") else f"{normalized}/v1/models"


def parse_model_ids(payload: Any) -> list[str]:
    entries = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        msg = "The models endpoint returned an unsupported payload"
        raise ModelDiscoveryError(msg)
    model_ids: set[str] = set()
    for entry in entries:
        value = entry.get("id") if isinstance(entry, dict) else entry
        if isinstance(value, str) and value.strip():
            model_ids.add(value.strip())
    return sorted(model_ids)


def discover_model_ids(base_url: str, api_key: str) -> list[str]:
    url = models_url(base_url)
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        sync_kwargs, _ = ssrf_protected_strict_httpx_client_kwargs_for_url(url)
        with (
            httpx.Client(**sync_kwargs) as client,
            client.stream(
                "GET",
                url,
                headers=headers,
                timeout=DISCOVERY_TIMEOUT_SECONDS,
                follow_redirects=False,
            ) as response,
        ):
            if response.is_redirect:
                msg = "The models endpoint returned a redirect; redirects are not allowed"
                raise ModelDiscoveryError(msg)
            if response.status_code in {401, 403}:
                msg = "Authentication failed while fetching models; check the API key"
                raise ModelDiscoveryError(msg)
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_DISCOVERY_BYTES:
                    msg = "The models endpoint response is too large"
                    raise ModelDiscoveryError(msg)
        return parse_model_ids(json.loads(body))
    except ModelDiscoveryError:
        raise
    except httpx.TimeoutException as exc:
        msg = "The models endpoint timed out"
        raise ModelDiscoveryError(msg) from exc
    except httpx.HTTPStatusError as exc:
        msg = f"The models endpoint returned HTTP {exc.response.status_code}"
        raise ModelDiscoveryError(msg) from exc
    except (httpx.RequestError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        msg = f"Could not fetch models: {exc}"
        raise ModelDiscoveryError(msg) from exc
