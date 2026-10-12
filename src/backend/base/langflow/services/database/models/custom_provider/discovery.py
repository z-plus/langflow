"""Endpoint probing and model discovery for custom providers.

Custom providers speak the OpenAI HTTP API shape, so this mirrors
``lfx_openai_compatible.discovery`` but probes an explicit ``(base_url,
api_key)`` pair instead of reading user Variables -- the supplier row is the
source of truth.
"""

from __future__ import annotations

from typing import Any

import httpx
from lfx.utils.ssrf_httpx import ssrf_safe_httpx_get

_TIMEOUT_SECONDS = 5
_ICON = "Plug"


def _models_url(base_url: str) -> str:
    """Return the ``/v1/models`` URL, tolerating a base that already ends in /v1."""
    base_url = base_url.rstrip("/")
    return f"{base_url}/models" if base_url.endswith("/v1") else f"{base_url}/v1/models"


def _parse_model_names(data: object) -> list[str]:
    """Parse model ids from an OpenAI-compatible ``{"data": [...]}`` or a plain list."""
    if isinstance(data, list):
        return sorted(str(m) for m in data if m)
    if isinstance(data, dict) and isinstance(data.get("data"), list):
        return sorted(m.get("id", "") for m in data["data"] if isinstance(m, dict) and m.get("id"))
    return []


def fetch_models(base_url: str, api_key: str | None) -> list[str]:
    """Fetch model ids from the supplier's ``/v1/models``.

    Raises ``ValueError`` with an actionable message on connection,
    authentication, or HTTP failures.
    """
    models_url = _models_url(base_url)
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        response = ssrf_safe_httpx_get(models_url, headers=headers, timeout=_TIMEOUT_SECONDS, follow_redirects=False)
    except httpx.ConnectError as e:
        msg = f"Could not connect to {base_url.rstrip('/')}. Check that the server is running."
        raise ValueError(msg) from e
    except httpx.TimeoutException as e:
        msg = f"Connection to {base_url.rstrip('/')} timed out."
        raise ValueError(msg) from e
    except httpx.RequestError as e:
        msg = f"Could not reach {base_url.rstrip('/')}: {e}"
        raise ValueError(msg) from e
    if response.status_code in (401, 403):
        msg = "Authentication failed. Check the API key."
        raise ValueError(msg)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        msg = f"The endpoint at {base_url.rstrip('/')} returned HTTP {status}."
        raise ValueError(msg) from e
    return _parse_model_names(response.json())


def to_stored_models(base_url: str, api_key: str | None, *, model_type: str) -> list[dict[str, Any]]:
    """Fetch model ids and return them shaped for ``discovered_models`` storage."""
    return [{"model_id": name, "model_type": model_type} for name in fetch_models(base_url, api_key)]
