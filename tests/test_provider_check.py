import asyncio
import base64
import json
import socket
import time
from urllib.parse import urlsplit

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from playground import provider_api as api
from playground import provider_http as network
from playground.app import app
from playground.provider_check import (
    CheckError, canonical, check_provider, envelope, main, read_json, validate_manifest,
)


@pytest.fixture
def identity():
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    manifest = {
        "product_id": "test-agent", "capability_id": "test-agent.invoke@v1", "publisher_id": "community",
        "name": "Test agent", "invoke_url": "https://provider.example/invoke", "price_per_call_usd": 0.001,
        "provider_pubkey": base64.b64encode(private.public_key().public_bytes_raw()).decode(),
        "input_schema": {"type": "object", "properties": {"hello": {"type": "string"}}},
        "output_schema": {"type": "object", "required": ["message"], "properties": {"message": {"type": "string"}}},
    }
    return private, manifest


def signed_reply(private, manifest, payload):
    result = {"message": "Hello"}
    # Independent construction matching the generated provider signing contract.
    import hashlib
    signed = json.dumps({
        "product_id": manifest["product_id"], "capability_id": manifest["capability_id"],
        "input_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest(),
        "result": result,
    }, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return canonical({"success": True, "result": result}), base64.b64encode(private.sign(signed)).decode()


@pytest.mark.asyncio
async def test_profile_passes_independent_request_bound_signature(identity):
    private, manifest = identity
    payload = {"hello": "мир"}
    calls = []

    async def send(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return signed_reply(private, manifest, kwargs["payload"]["input"])

    report = await check_provider(manifest, payload, requester=send)
    assert report["status"] == "passed"
    assert len(calls) == 1
    assert report["evidence"]["envelope"]["input_sha256"] == report["input_sha256"]
    assert {"hub_receipt", "replay_detection", "whole_protocol_conformance"} <= set(report["not_tested"])


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["signature", "key", "input", "identity", "result"])
async def test_signature_rejects_tampering(identity, mutation):
    private, manifest = identity
    body, signature = signed_reply(private, manifest, {"hello": "world"})
    if mutation == "key":
        manifest["provider_pubkey"] = base64.b64encode(Ed25519PrivateKey.generate().public_key().public_bytes_raw()).decode()
    if mutation == "identity":
        manifest["product_id"] = "another"
    if mutation == "result":
        body = canonical({"success": True, "result": {"message": "tampered"}})
    if mutation == "signature":
        signature = "invalid"

    async def send(*args, **kwargs):
        return body, signature

    report = await check_provider(manifest, {"hello": "different" if mutation == "input" else "world"}, requester=send)
    assert report["status"] == "failed"
    assert report["checks"][-1]["id"] == "provider_signature"
    assert "evidence" not in report


@pytest.mark.asyncio
@pytest.mark.parametrize("response,step", [([], "invoke"), ({"success": 1, "result": {}}, "invoke"),
    ({"success": True, "result": []}, "invoke"), ({"success": True, "result": {}}, "output_schema")])
async def test_bad_response_is_not_a_pass(identity, response, step):
    async def send(*args, **kwargs):
        return canonical(response), ""
    report = await check_provider(identity[1], {}, requester=send)
    assert report["checks"][-1]["id"] == step
    assert report["status"] == "failed"


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}',
    b'"\xff"', b'"\\ud800"', b"not json", b" " * 65537, b"[" * 30 + b"0" + b"]" * 30,
    canonical([0] * 4097), '{}'.encode('utf-16')])
def test_ambiguous_or_unbounded_json_rejected(raw):
    with pytest.raises(CheckError):
        read_json(raw)


@pytest.mark.parametrize("field,value", [
    ("product_id", "bad id"), ("capability_id", "bad"), ("publisher_id", "tx-consumed:bad"),
    ("name", ""), ("name", 2), ("price_per_call_usd", True), ("price_per_call_usd", -1),
    ("provider_pubkey", "bad"), ("provider_pubkey", 25), ("provider_pubkey", ""),
    ("input_schema", {"type": "array"}), ("input_schema", {"type": "object", "required": "x"}),
    ("input_schema", {"type": "object", "$ref": "https://internal.example"}),
    ("input_schema", {"type": "object", "properties": {"x": {"pattern": "(a+)+$"}}}),
    ("input_schema", {"type": "object", "$schema": "http://json-schema.org/draft-07/schema#"}),
])
def test_invalid_contract_rejected(identity, field, value):
    manifest = identity[1]
    manifest[field] = value
    with pytest.raises(CheckError):
        validate_manifest(manifest, {})


def test_schema_values_checked_and_supported_nested_schemas(identity):
    manifest = identity[1]
    with pytest.raises(CheckError, match="input/hello failed type"):
        validate_manifest(manifest, {"hello": 42})
    with pytest.raises(CheckError, match="JSON objects"):
        validate_manifest([], {})
    manifest["input_schema"] = {"type": "object", "additionalProperties": False,
        "properties": {"nested": {"type": "array", "items": {"type": "integer", "minimum": 0}}}}
    validate_manifest(manifest, {"nested": [1, 2]})


@pytest.mark.parametrize("url", [None, "https://", "http://public.example/invoke", "https://x:bad/i",
    "https://x:8443/i", "https://a:b@x/i", "https://@x/i", "https://x/i?q=1", "https://x/i#f",
    "https://x/\ni", "https://x\\@y/i", "https://[fe80::1%eth0]/i", "file:///tmp/file", "https://пример.рф/invoke"])
def test_public_url_policy(url):
    with pytest.raises(CheckError):
        network.parse_target(url)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "192.0.2.1", "224.0.0.1",
    "::1", "::", "fe80::1", "ff02::1", "64:ff9b::7f00:1", "2002:0808:0808::1", "::ffff:8.8.8.8"])
def test_nonpublic_or_transition_addresses_blocked(address):
    assert not network.public_address(address)


@pytest.mark.asyncio
async def test_dns_pinning_and_mixed_answers(monkeypatch):
    loop = asyncio.get_running_loop()

    async def dns(*args, **kwargs):
        return [(None, None, None, None, ("8.8.8.8", 443))]

    monkeypatch.setattr(loop, "getaddrinfo", dns)
    target, headers, ext = await network.pin_target("https://provider.example:443/invoke")
    assert target == "https://8.8.8.8:443/invoke"
    assert headers == {"Host": "provider.example:443"}
    assert ext["sni_hostname"] == "provider.example"

    async def mixed(*args, **kwargs):
        return [(None, None, None, None, (ip, 443)) for ip in ["8.8.8.8", "127.0.0.1"]]
    monkeypatch.setattr(loop, "getaddrinfo", mixed)
    with pytest.raises(CheckError, match="public addresses"):
        await network.pin_target("https://provider.example/invoke")


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", [[], None])
async def test_dns_failures_closed(monkeypatch, answer):
    async def dns(*args, **kwargs):
        if answer is None:
            raise socket.gaierror()
        return answer
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns)
    with pytest.raises(CheckError):
        await network.pin_target("https://provider.example/invoke")


@pytest.mark.asyncio
async def test_local_option_and_ipv6_pin(monkeypatch):
    async def dns(*args, **kwargs):
        return [(None, None, None, None, ("::1", 8099))]
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns)
    target, _, _ = await network.pin_target("http://localhost:8099/invoke", allow_loopback=True)
    assert target == "http://[::1]:8099/invoke"
    with pytest.raises(CheckError):
        network.parse_target("ftp://localhost/invoke", allow_loopback=True)
    assert network.public_address("2606:4700:4700::1111")


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["ok", "redirect", "compressed", "html", "large", "timeout", "tls"])
async def test_bounded_transport(monkeypatch, case):
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * (65537 if case == "large" else 2)

    async def handler(request):
        assert request.url.host == "8.8.8.8"
        assert request.headers["host"] == "provider.example"
        assert request.extensions["sni_hostname"] == "provider.example"
        assert "authorization" not in request.headers
        if case == "timeout":
            raise httpx.ReadTimeout("private error details")
        if case == "tls":
            raise httpx.ConnectError("private error details")
        headers = {"content-type": "text/html" if case == "html" else "application/json"}
        if case == "compressed":
            headers["content-encoding"] = "gzip"
        return httpx.Response(302 if case == "redirect" else 200, headers=headers, stream=Stream())

    original = httpx.AsyncClient
    def client(**kwargs):
        assert kwargs["trust_env"] is False and kwargs["follow_redirects"] is False
        return original(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(network.httpx, "AsyncClient", client)
    pinned = ("https://8.8.8.8/invoke", {"Host": "provider.example"}, {"sni_hostname": "provider.example"})
    if case == "ok":
        assert await network.request_json("GET", "https://provider.example/invoke", pinned=pinned) == (b"xx", "")
    else:
        with pytest.raises(CheckError) as error:
            await network.request_json("GET", "https://provider.example/invoke", pinned=pinned)
        assert "private error" not in str(error.value)


@pytest.fixture
def client():
    api.CHALLENGES.clear()
    api.VISITS.clear()
    with TestClient(app) as value:
        yield value


HEADERS = {"X-Playground-Visitor": "provider-test-visitor"}


def prepare(client, manifest):
    response = client.post("/api/provider-check/challenges", headers=HEADERS,
                           json={"manifest": manifest, "input": {}, "consent": True})
    assert response.status_code == 200, response.text
    return response.json()


def fake_network(monkeypatch, identity, proof, calls, *, bad_signature=False):
    async def pin(url):
        calls.append("DNS")
        return "https://8.8.8.8/invoke", {"Host": "provider.example"}, {"sni_hostname": "provider.example"}
    async def send(method, url, **kwargs):
        calls.append(method)
        assert urlsplit(kwargs["pinned"][0]).hostname == "8.8.8.8"
        if method == "GET":
            return canonical(proof), ""
        body, signature = signed_reply(identity[0], identity[1], kwargs["payload"]["input"])
        return body, "bad" if bad_signature else signature
    monkeypatch.setattr(api, "pin_target", pin)
    monkeypatch.setattr(api, "request_json", send)


def test_browser_checks_control_and_never_reinvokes(client, monkeypatch, identity):
    challenge = prepare(client, identity[1])
    calls = []
    fake_network(monkeypatch, identity, challenge["proof"], calls)
    url = f"/api/provider-check/challenges/{challenge['challenge_id']}/run"
    assert client.post(url).status_code == 400
    assert client.post(url, headers={"X-Playground-Visitor": "another-visitor"}).status_code == 404
    first = client.post(url, headers=HEADERS)
    assert first.status_code == 200
    assert first.json()["status"] == "passed"
    assert first.json()["checks"][0]["id"] == "endpoint_control"
    assert client.post(url, headers=HEADERS).json() == first.json()
    assert calls == ["DNS", "GET", "POST"]
    assert first.headers["cache-control"] == "no-store"


def test_failed_signature_also_cached(client, monkeypatch, identity):
    challenge = prepare(client, identity[1])
    calls = []
    fake_network(monkeypatch, identity, challenge["proof"], calls, bad_signature=True)
    url = f"/api/provider-check/challenges/{challenge['challenge_id']}/run"
    assert client.post(url, headers=HEADERS).json()["status"] == "failed"
    assert client.post(url, headers=HEADERS).json()["status"] == "failed"
    assert calls.count("POST") == 1


@pytest.mark.asyncio
async def test_cancellation_after_dispatch_never_reinvokes(monkeypatch, identity):
    api.CHALLENGES.clear()
    api.VISITS.clear()
    monkeypatch.setattr(api, "SLOTS", asyncio.Semaphore(4))
    calls = []
    started = asyncio.Event()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/provider-check/challenges", headers=HEADERS,
            json={"manifest":identity[1], "input":{}, "consent":True})
        challenge = response.json()
        fake_network(monkeypatch, identity, challenge["proof"], calls)
        send = api.request_json

        async def gated(method, *args, **kwargs):
            if method == "POST":
                started.set()
                await asyncio.Event().wait()
            return await send(method, *args, **kwargs)
        monkeypatch.setattr(api, "request_json", gated)
        url = f"/api/provider-check/challenges/{challenge['challenge_id']}/run"
        running = asyncio.create_task(client.post(url, headers=HEADERS))
        await asyncio.wait_for(started.wait(), 1)
        assert (await client.post(url, headers=HEADERS)).status_code == 409
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        report = (await client.post(url, headers=HEADERS)).json()
        assert report["status"] == "failed"
        assert "outcome unknown" in report["checks"][-1]["detail"]


def test_no_invoke_before_ownership_and_bounded_attempts(client, monkeypatch, identity):
    challenge = prepare(client, identity[1])
    calls = []
    fake_network(monkeypatch, identity, {"challenge": "неверный"}, calls)
    url = f"/api/provider-check/challenges/{challenge['challenge_id']}/run"
    for _ in range(3):
        assert client.post(url, headers=HEADERS).status_code == 422
    assert client.post(url, headers=HEADERS).status_code == 409
    assert "POST" not in calls


def test_public_api_rejects_bad_input_and_body_before_network(client, identity):
    assert client.post("/api/provider-check/challenges", json={}).status_code == 400
    assert client.post("/api/provider-check/challenges", headers=HEADERS, json={}).status_code == 422
    assert client.post("/api/provider-check/challenges", headers=HEADERS, content=b'x' * 65537).status_code == 413
    assert client.post("/api/provider-check/challenges", headers=HEADERS,
        content=b'{"consent":true,"consent":false}').status_code == 422
    assert client.post("/api/provider-check/challenges", headers=HEADERS,
        json={"manifest": json.dumps(identity[1]), "input": '{"x":1,"x":2}', "consent": True}).status_code == 422
    assert client.post("/api/provider-check/challenges", headers=HEADERS,
        json={"manifest": json.dumps(identity[1]), "input": '{}', "consent": True}).status_code == 200
    identity[1]["invoke_url"] = "http://localhost:8080/invoke"
    assert client.post("/api/provider-check/challenges", headers=HEADERS,
        json={"manifest": identity[1], "input": {}, "consent": True, "allow_loopback": True}).status_code == 422


def test_challenge_expiry_capacity_busy_and_rate_limit(client, monkeypatch, identity):
    challenge = prepare(client, identity[1])
    item = api.CHALLENGES[challenge["challenge_id"]]
    url = f"/api/provider-check/challenges/{challenge['challenge_id']}/run"
    item["running"] = True
    assert client.post(url, headers=HEADERS).status_code == 409
    item["running"] = False
    monkeypatch.setattr(api, "SLOTS", asyncio.Semaphore(0))
    assert client.post(url, headers=HEADERS).status_code == 429
    monkeypatch.setattr(api, "MAX_CHALLENGES", 1)
    assert client.post("/api/provider-check/challenges", headers=HEADERS, json={}).status_code == 503
    item["expires_at"] = time.time() - 1
    assert client.post(url, headers=HEADERS).status_code == 404
    api.VISITS["old"] = [0]
    api.VISITS["global"] = [time.time()] * 500
    assert client.post("/api/provider-check/challenges", headers=HEADERS, json={}).status_code == 429
    assert "old" not in api.VISITS


def test_source_allowance_cannot_be_rotated(client):
    import hashlib
    api.VISITS["source:" + hashlib.sha256(b"testclient").hexdigest()] = [time.time()] * 60
    assert client.post("/api/provider-check/challenges", headers={"X-Playground-Visitor": "rotated-visitor"}, json={}).status_code == 429


def test_frontend_routes(client):
    assert client.get("/connect").status_code == 200
    assert client.get("/assets/connect.js").status_code == 200
    assert client.get("/assets/connect.css").status_code == 200


def test_provider_guide_link_resolves_inside_deployed_app(client):
    page = client.get("/connect").text
    assert 'href="/connect/guide"' in page
    assert "github.com/alexar76/aimarket-playground/blob/main/docs/provider-check.md" not in page
    guide = client.get("/connect/guide?lang=ru")
    assert guide.status_code == 200
    assert "Подключение поставщика" in guide.text
    assert "aimarket-provider-check" in guide.text
    assert client.get("/assets/provider-guide.css").status_code == 200
    assert client.get("/assets/provider-guide.js").status_code == 200


def test_cli_exit_codes_and_json_report(tmp_path, identity, monkeypatch, capsys):
    manifest_file = tmp_path / "capability.json"
    input_file = tmp_path / "input.json"
    manifest_file.write_bytes(canonical(identity[1]))
    input_file.write_bytes(b"{}")
    from playground import provider_check as module

    async def success(*args, **kwargs):
        assert kwargs["allow_loopback"] is True
        return {"status": "passed"}
    monkeypatch.setattr(module, "check_provider", success)
    assert main([str(manifest_file), "--input", str(input_file), "--allow-loopback"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "passed"
    input_file.write_bytes(b"bad")
    assert main([str(manifest_file), "--input", str(input_file)]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "failed"
