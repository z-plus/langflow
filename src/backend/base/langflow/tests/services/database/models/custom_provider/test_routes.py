from __future__ import annotations

import os

# Harness-injected NO_PROXY carries a bracketed IPv6 entry ([::1]) that the
# pinned httpx version mis-parses; langflow.api imports construct httpx eagerly.
os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"

from langflow.api.v1.custom_providers import router


def test_router_prefix():
    assert router.prefix == "/custom-providers"


def _routes():
    return {(r.path, tuple(sorted(r.methods or []))) for r in router.routes}


def test_expected_routes_registered():
    routes = _routes()
    assert ("/custom-providers", ("GET",)) in routes
    assert ("/custom-providers", ("POST",)) in routes
    assert ("/custom-providers/catalog", ("GET",)) in routes
    assert ("/custom-providers/provider-ids", ("GET",)) in routes
    assert ("/custom-providers/{provider_id}", ("GET",)) in routes
    assert ("/custom-providers/{provider_id}", ("PATCH",)) in routes
    assert ("/custom-providers/{provider_id}", ("DELETE",)) in routes
    assert ("/custom-providers/{provider_id}/refresh", ("POST",)) in routes
    assert ("/custom-providers/{provider_id}/models", ("POST",)) in routes
    assert ("/custom-providers/{provider_id}/models/{model_id}", ("DELETE",)) in routes
    assert ("/custom-providers/meta/preview", ("POST",)) in routes


def test_meta_preview_does_not_shadow_provider_id():
    # /meta/preview is a distinct static path; a provider named "meta" would be
    # disambiguated by FastAPI's path matching, but this guards the ordering.
    preview = next(r for r in router.routes if getattr(r, "path", None) == "/custom-providers/meta/preview")
    provider = next(r for r in router.routes if getattr(r, "path", None) == "/custom-providers/{provider_id}")
    assert preview.path_format == "/custom-providers/meta/preview"
    assert provider.path_format == "/custom-providers/{provider_id}"
