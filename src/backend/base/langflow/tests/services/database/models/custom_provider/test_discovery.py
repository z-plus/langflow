from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# The harness injects NO_PROXY with a bracketed IPv6 entry ([::1]) that the
# pinned httpx version mis-parses into an InvalidURL at client construction.
# Normalize it in-process before any httpx import.
os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"

import pytest
from langflow.services.database.models.custom_provider.discovery import fetch_models, to_stored_models


class _ModelsHandler(BaseHTTPRequestHandler):
    """Serves GET /v1/models with configurable status/body."""

    status = 200
    body = None

    def do_GET(self):
        if self.path not in ("/v1/models", "/models"):
            self._send(404, b"{}")
            return
        self._send(self.__class__.status, self.__class__.body)

    def _send(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


@pytest.fixture(name="base_url")
def base_url_fixture():
    server = HTTPServer(("127.0.0.1", 0), _ModelsHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    thread.join(timeout=2)
    server.server_close()


def test_fetch_models_success(base_url: str):
    _ModelsHandler.status = 200
    _ModelsHandler.body = json.dumps({"data": [{"id": "model-b"}, {"id": "model-a"}]}).encode()
    assert fetch_models(base_url, api_key=None) == ["model-a", "model-b"]


def test_fetch_models_plain_list_success(base_url: str):
    _ModelsHandler.status = 200
    _ModelsHandler.body = json.dumps(["x", "y"]).encode()
    assert fetch_models(base_url, api_key="sk-test") == ["x", "y"]


def test_fetch_models_auth_failure(base_url: str):
    _ModelsHandler.status = 401
    _ModelsHandler.body = b"{}"
    with pytest.raises(ValueError, match="Authentication failed"):
        fetch_models(base_url, api_key=None)


def test_fetch_models_http_error(base_url: str):
    _ModelsHandler.status = 500
    _ModelsHandler.body = b"{}"
    with pytest.raises(ValueError, match="HTTP 500"):
        fetch_models(base_url, api_key=None)


def test_models_url_suffix_tolerance(base_url: str):
    # A base that already ends in /v1 must not get /v1 appended twice; the stub
    # serves both /v1/models and /models so either path parses the same body.
    _ModelsHandler.status = 200
    _ModelsHandler.body = json.dumps({"data": [{"id": "m"}]}).encode()
    with_suffix = f"{base_url}/v1"
    without_suffix = base_url
    assert fetch_models(with_suffix, None) == ["m"]
    assert fetch_models(without_suffix, None) == ["m"]


def test_to_stored_models_tags_model_type(base_url: str):
    _ModelsHandler.status = 200
    _ModelsHandler.body = json.dumps({"data": [{"id": "embed-x"}]}).encode()
    stored = to_stored_models(base_url, api_key=None, model_type="embeddings")
    assert stored == [{"model_id": "embed-x", "model_type": "embeddings"}]
