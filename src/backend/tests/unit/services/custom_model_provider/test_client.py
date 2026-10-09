from __future__ import annotations

import httpx
import pytest
from langflow.services.custom_model_provider import client


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://example.test", "https://example.test/v1/models"),
        ("https://example.test/v1/", "https://example.test/v1/models"),
    ],
)
def test_models_url(base_url, expected):
    assert client.models_url(base_url) == expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"data": [{"id": "qwen"}, {"id": " llama "}]}, ["llama", "qwen"]),
        (["qwen", "qwen", "llama"], ["llama", "qwen"]),
    ],
)
def test_discovery_accepts_supported_payloads(monkeypatch, payload, expected):
    seen = {}

    def handler(request):
        seen["request"] = request
        return httpx.Response(200, json=payload)

    monkeypatch.setattr(
        client,
        "ssrf_protected_strict_httpx_client_kwargs_for_url",
        lambda _url: ({"transport": httpx.MockTransport(handler)}, {}),
    )
    assert client.discover_model_ids("https://example.test", "top-secret") == expected
    assert seen["request"].url == "https://example.test/v1/models"
    assert seen["request"].headers["Authorization"] == "Bearer top-secret"


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(401), "Authentication failed"),
        (httpx.Response(302, headers={"location": "https://other.test/models"}), "redirect"),
        (httpx.Response(200, content=b"not-json"), "Could not fetch models"),
        (httpx.Response(200, json={"models": []}), "unsupported payload"),
    ],
)
def test_discovery_reports_actionable_failures(monkeypatch, response, message):
    monkeypatch.setattr(
        client,
        "ssrf_protected_strict_httpx_client_kwargs_for_url",
        lambda _url: ({"transport": httpx.MockTransport(lambda _request: response)}, {}),
    )
    with pytest.raises(client.ModelDiscoveryError, match=message):
        client.discover_model_ids("https://example.test", "secret")


def test_discovery_rejects_oversized_response(monkeypatch):
    response = httpx.Response(200, content=b"x" * (client.MAX_DISCOVERY_BYTES + 1))
    monkeypatch.setattr(
        client,
        "ssrf_protected_strict_httpx_client_kwargs_for_url",
        lambda _url: ({"transport": httpx.MockTransport(lambda _request: response)}, {}),
    )
    with pytest.raises(client.ModelDiscoveryError, match="too large"):
        client.discover_model_ids("https://example.test", "secret")


def test_discovery_propagates_strict_ssrf_rejection(monkeypatch):
    def blocked(_url):
        msg = "SSRF Protection: Blocked private IP address"
        raise ValueError(msg)

    monkeypatch.setattr(client, "ssrf_protected_strict_httpx_client_kwargs_for_url", blocked)
    with pytest.raises(client.ModelDiscoveryError, match="Blocked private IP"):
        client.discover_model_ids("http://127.0.0.1:8000", "secret")


def test_discovery_reports_timeout(monkeypatch):
    def handler(request):
        msg = "late"
        raise httpx.ReadTimeout(msg, request=request)

    monkeypatch.setattr(
        client,
        "ssrf_protected_strict_httpx_client_kwargs_for_url",
        lambda _url: ({"transport": httpx.MockTransport(handler)}, {}),
    )
    with pytest.raises(client.ModelDiscoveryError, match="timed out"):
        client.discover_model_ids("https://example.test", "secret")
