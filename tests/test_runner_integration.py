import base64
import json

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from playground.receipts import canonical_receipt
from playground.runner import GoldenPathRunner


def make_signed_receipt(version=2):
    private = Ed25519PrivateKey.generate()
    receipt = {
        "nonce": "receipt-1",
        "product_id": "gaia.gateway",
        "capability_id": "gaia.weather.read@v1",
        "price_usd": 0.001,
        "timestamp": "2026-08-20T12:00:00Z",
        "success": True,
        "latency_ms": 15,
        "type": "invoke",
        "verify_score": 0.99,
    }
    signature = private.sign(canonical_receipt(receipt, version).encode())
    receipt["signature"] = {
        "algorithm": "ed25519",
        "version": version,
        "value": base64.b64encode(signature).decode(),
    }
    public = base64.b64encode(private.public_key().public_bytes_raw()).decode()
    return receipt, public


def mock_async_client(monkeypatch, handler):
    real_client = httpx.AsyncClient

    def factory(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr("playground.runner.httpx.AsyncClient", factory)


@pytest.mark.asyncio
async def test_full_route_invokes_verifies_receipt_and_emits_event(monkeypatch):
    receipt, public_key = make_signed_receipt()
    requests = []

    async def handler(request):
        requests.append(request)
        if request.url.path == "/ai-market/v2/invoke":
            payload = json.loads(request.content)
            assert payload["input"] == {"device_id": "om-wx-01"}
            assert request.headers["x-aimarket-sandbox-visitor"].startswith("playground-")
            return httpx.Response(200, json={
                "output": {"temperature_c": 21.5},
                "receipt": receipt,
                "sandbox": {"charged": False},
            })
        if request.url.path == "/v1/verify":
            assert request.headers["authorization"] == "Bearer metis-secret"
            payload = json.loads(request.content)
            assert payload["route"] == "fast"
            assert "internal consistency and physical plausibility" in payload["input"]
            assert "VERDICT (plausible or implausible)" in payload["input"]
            assert "Playground verifies the receipt signature separately" in payload["input"]
            assert '"temperature_c":21.5' in payload["input"]
            return httpx.Response(200, json={
                "answer": "VERDICT: plausible\nCHECKS: values and units\nLIMITATION: not physical proof",
                "status": "complete", "verified": True, "verify_performed": True,
                "verify_score": 0.99, "route": "fast"
            })
        if request.url.path == "/.well-known/ai-market.json":
            return httpx.Response(200, json={"signer_public_key": public_key})
        if request.url.path == "/events":
            assert request.headers["authorization"] == "Bearer event-secret"
            event = json.loads(request.content)
            assert event["receipt_verified"] is True
            return httpx.Response(202, json={"accepted": True})
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    mock_async_client(monkeypatch, handler)
    runner = GoldenPathRunner()
    runner.hub_url = "https://hub.test"
    runner.metis_url = "https://metis.test"
    runner.source_hub = "https://gaia.test"
    runner.monitor_url = "https://monitor.test/view"
    runner.metis_key = "metis-secret"
    runner.event_url = "https://events.test/events"
    runner.event_token = "event-secret"

    progress = []

    async def on_progress(result):
        progress.append(result)

    result = await runner.run(
        run_id="run-1",
        visitor="visitor-secret",
        device_id="om-wx-01",
        on_progress=on_progress,
    )
    assert progress[0]["status"] == "verifying"
    assert progress[0]["verification"] == {"status": "running", "verified": False}
    assert progress[0]["receipt_verification"]["verified"] is True
    assert result["status"] == "completed"
    assert result["verification"]["verified"] is True
    assert result["receipt_signature_present"] is True
    assert result["receipt_verification"] == {
        "verified": True, "reason": "ok", "origin": "https://gaia.test"
    }
    assert result["monitor_url"] == "https://monitor.test/view?run_id=run-1"
    assert [request.url.path for request in requests] == [
        "/ai-market/v2/invoke", "/.well-known/ai-market.json", "/v1/verify", "/events"
    ]

    requests.clear()
    result_without_callback = await runner.run(
        run_id="run-without-progress", visitor="visitor-secret", device_id="om-wx-01"
    )
    assert result_without_callback["status"] == "completed"
    assert [request.url.path for request in requests] == [
        "/ai-market/v2/invoke", "/.well-known/ai-market.json", "/v1/verify", "/events"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (503, {"detail": "down"}, "hub_refused:503"),
        (200, {"receipt": {}}, "hub_returned_no_output"),
    ],
)
async def test_hub_failures_stop_the_route(monkeypatch, status, body, error):
    async def handler(request):
        return httpx.Response(status, json=body)

    mock_async_client(monkeypatch, handler)
    runner = GoldenPathRunner()
    runner.hub_url = "https://hub.test"
    with pytest.raises(RuntimeError, match=error):
        await runner.run(run_id="run-2", visitor="visitor", device_id="device")


@pytest.mark.asyncio
async def test_metis_http_failure_is_a_bounded_partial_result():
    runner = GoldenPathRunner()
    runner.metis_url = "https://metis.test"

    async def handler(request):
        return httpx.Response(429, json={"detail": "secret internal reason"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verdict = await runner._verify(client, {"reading": 1})
    assert verdict == {"status": "unavailable", "verified": False, "http_status": 429}
    assert "secret" not in repr(verdict)


@pytest.mark.asyncio
async def test_legacy_fast_response_without_verifier_is_indeterminate_not_zero_score():
    runner = GoldenPathRunner()
    runner.metis_url = "https://metis.test"

    async def handler(request):
        return httpx.Response(
            200,
            json={
                "answer": "The reading is physically plausible.",
                "status": "success",
                "verified": False,
                "verify_score": 0.0,
                "route": "fast",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verdict = await runner._verify(client, {"reading": 1})

    assert verdict == {
        "status": "not_performed",
        "verified": False,
        "verify_performed": False,
        "verify_score": None,
        "route": "fast",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["network", "http"])
async def test_origin_key_failures_fail_closed(mode):
    runner = GoldenPathRunner()
    runner.source_hub = "https://gaia.test"

    async def handler(request):
        if mode == "network":
            raise httpx.ConnectError("private origin", request=request)
        return httpx.Response(404, json={"detail": "missing"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await runner._verify_receipt_origin(client, {})
    assert result == {
        "verified": False,
        "reason": "origin-key-unavailable",
        "origin": "https://gaia.test",
    }


@pytest.mark.asyncio
async def test_nested_origin_signing_key_is_supported():
    receipt, public_key = make_signed_receipt(version=1)
    runner = GoldenPathRunner()
    runner.source_hub = "https://gaia.test"

    async def handler(request):
        return httpx.Response(200, json={"signing": {"public_key": public_key}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await runner._verify_receipt_origin(client, receipt)
    assert result["verified"] is True


@pytest.mark.asyncio
async def test_origin_receipt_is_bound_to_expected_product_and_capability():
    receipt, public_key = make_signed_receipt(version=2)
    runner = GoldenPathRunner()
    runner.source_hub = "https://gaia.test"

    async def handler(request):
        return httpx.Response(200, json={"signer_public_key": public_key})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        wrong_product = await runner._verify_receipt_origin(
            client,
            receipt,
            product_id="another-product",
            capability_id=receipt["capability_id"],
        )
        wrong_capability = await runner._verify_receipt_origin(
            client,
            receipt,
            product_id=receipt["product_id"],
            capability_id="another.capability@v1",
        )

    assert wrong_product["reason"] == "product-mismatch"
    assert wrong_capability["reason"] == "capability-mismatch"


@pytest.mark.asyncio
async def test_event_failure_never_changes_successful_result():
    runner = GoldenPathRunner()
    runner.event_url = "https://events.test/ingest"
    runner.event_token = "token"
    result = {
        "run_id": "r",
        "capability_id": "c@v1",
        "verification": {"verified": True},
        "receipt_nonce": "n",
        "receipt_verification": {"verified": True},
    }

    async def handler(request):
        raise httpx.ConnectError("events down", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await runner._emit(client, result) is None

    runner.event_url = ""
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await runner._emit(client, result) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"", {"detail": "non-json response"}),
        (b"not json", {"detail": "non-json response"}),
        (b"[1,2]", {"body": [1, 2]}),
        (b'{"ok":true}', {"ok": True}),
    ],
)
async def test_response_decoding_is_total(content, expected):
    runner = GoldenPathRunner()

    async def handler(request):
        return httpx.Response(200, content=content)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        status, body = await runner._get_json(client, "https://example.test/data")
    assert status == 200
    assert body == expected


@pytest.mark.asyncio
async def test_response_with_no_stream_chunks_is_handled():
    class EmptyResponse:
        async def aiter_bytes(self):
            if False:
                yield b""

    runner = GoldenPathRunner()
    assert await runner._read_json(EmptyResponse()) == {"detail": "non-json response"}


def test_environment_configuration_is_normalized_and_bounded(monkeypatch):
    monkeypatch.setenv("PLAYGROUND_ALLOW_INSECURE_UPSTREAMS", "1")
    monkeypatch.setenv("PLAYGROUND_HUB_URL", "http://hub.test/root/")
    monkeypatch.setenv("PLAYGROUND_METIS_URL", "http://metis.test/")
    monkeypatch.setenv("PLAYGROUND_GAIA_URL", "http://gaia.test/")
    monkeypatch.setenv("PLAYGROUND_MONITOR_URL", "http://monitor.test/view")
    monkeypatch.setenv("PLAYGROUND_MAX_RESPONSE_BYTES", "1")
    monkeypatch.setenv("PLAYGROUND_METIS_TIMEOUT_S", "999")
    runner = GoldenPathRunner()
    assert runner.hub_url == "http://hub.test/root"
    assert runner.max_response_bytes == 4096
    assert runner.metis_timeout_s == 620.0
    assert runner.metis_route == "fast"
    assert len(runner.trial_id("visitor")) == len("playground-") + 24


def test_metis_route_is_allow_listed(monkeypatch):
    monkeypatch.setenv("PLAYGROUND_METIS_ROUTE", "arbitrary")
    with pytest.raises(ValueError, match="must be fast, thinking, or council"):
        GoldenPathRunner()


@pytest.mark.parametrize("url", ["https://example.test/path?x=1", "https://example.test/#frag"])
def test_queries_and_fragments_are_rejected(url):
    with pytest.raises(ValueError, match="query strings or fragments"):
        GoldenPathRunner._absolute_url(url, allow_http=False)
