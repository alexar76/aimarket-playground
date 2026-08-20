import asyncio
import threading
import time

from fastapi.testclient import TestClient

from playground import app as module


class FakeRunner:
    async def run(self, *, run_id, visitor, device_id, on_progress=None):
        result = {"run_id": run_id, "status": "verifying", "capability_id": "gaia.weather.read@v1",
                  "output": {"device_id": device_id}, "verification": {"status": "running", "verified": False},
                  "receipt_nonce": "nonce-1", "receipt_signature_present": True,
                  "receipt_verification": {"verified": True, "reason": "ok"},
                  "monitor_url": f"https://monitor.test/?run_id={run_id}"}
        if on_progress:
            await on_progress(dict(result))
            await asyncio.sleep(0.01)
        result["status"] = "completed"
        result["verification"] = {"status": "complete", "verified": True}
        return result


class LeakyRunner:
    async def run(self, **kwargs):
        raise RuntimeError("postgres://admin:secret@internal-db/private")


class GatedRunner(FakeRunner):
    def __init__(self):
        self.verifying = threading.Event()
        self.release = threading.Event()

    async def run(self, *, run_id, visitor, device_id, on_progress=None):
        result = {
            "run_id": run_id,
            "status": "verifying",
            "capability_id": "gaia.weather.read@v1",
            "verification": {"status": "running", "verified": False},
            "receipt_verification": {"verified": True, "reason": "ok"},
        }
        await on_progress(dict(result))
        self.verifying.set()
        await asyncio.to_thread(self.release.wait, 1)
        result["status"] = "completed"
        result["verification"] = {"status": "complete", "verified": True}
        return result


def wait_for_terminal(client, run_id, visitor):
    for _ in range(100):
        response = client.get(
            f"/api/playground/runs/{run_id}", headers={"X-Playground-Visitor": visitor}
        )
        body = response.json()
        if body["status"] not in {"running", "verifying"}:
            return response
        time.sleep(0.01)
    raise AssertionError("background run did not finish")


def test_golden_path(monkeypatch):
    monkeypatch.setattr(module, "runner", FakeRunner())
    module.RUNS.clear(); module.RUN_OWNERS.clear(); module.VISITS.clear()
    with TestClient(module.app) as client:
        response = client.post("/api/playground/runs", json={"device_id": "om-wx-01"},
                               headers={"X-Playground-Visitor": "visitor-123456"})
        assert response.status_code == 200
        body = response.json()
        assert body == {"run_id": body["run_id"], "status": "running", "stage": "gaia"}
        fetched = wait_for_terminal(client, body["run_id"], "visitor-123456")
    assert fetched.json()["verification"]["verified"] is True
    assert fetched.status_code == 200
    assert fetched.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in fetched.headers["content-security-policy"]


def test_background_run_exposes_verifying_before_terminal(monkeypatch):
    gated = GatedRunner()
    monkeypatch.setattr(module, "runner", gated)
    module.RUNS.clear(); module.RUN_OWNERS.clear(); module.VISITS.clear()
    visitor = "visitor-async-status"
    with TestClient(module.app) as client:
        created = client.post(
            "/api/playground/runs", json={}, headers={"X-Playground-Visitor": visitor}
        ).json()
        assert gated.verifying.wait(1)
        progress = client.get(
            f"/api/playground/runs/{created['run_id']}",
            headers={"X-Playground-Visitor": visitor},
        ).json()
        assert progress["status"] == "verifying"
        assert progress["verification"] == {"status": "running", "verified": False}
        assert progress["receipt_verification"]["verified"] is True
        gated.release.set()
        completed = wait_for_terminal(client, created["run_id"], visitor).json()
    assert completed["status"] == "completed"


def test_rejects_missing_visitor():
    client = TestClient(module.app)
    assert client.post("/api/playground/runs", json={}).status_code == 400


def test_rate_limit_is_bound_to_hashed_visitor(monkeypatch):
    monkeypatch.setattr(module, "runner", FakeRunner())
    monkeypatch.setattr(module, "MAX_RUNS", 1)
    module.RUNS.clear(); module.RUN_OWNERS.clear(); module.VISITS.clear()
    client = TestClient(module.app)
    assert client.post("/api/playground/runs", json={}, headers={"X-Playground-Visitor": "visitor-one"}).status_code == 200
    assert client.post("/api/playground/runs", json={}, headers={"X-Playground-Visitor": "visitor-one"}).status_code == 429
    assert all("visitor-one" not in key for key in module.VISITS)


def test_rotating_visitor_header_cannot_bypass_source_rate_limit(monkeypatch):
    monkeypatch.setattr(module, "runner", FakeRunner())
    monkeypatch.setattr(module, "MAX_RUNS", 5)
    monkeypatch.setattr(module, "MAX_SOURCE_RUNS", 1)
    module.RUNS.clear(); module.RUN_OWNERS.clear(); module.VISITS.clear()
    client = TestClient(module.app)
    assert client.post(
        "/api/playground/runs", json={}, headers={"X-Playground-Visitor": "visitor-source-one"}
    ).status_code == 200
    assert client.post(
        "/api/playground/runs", json={}, headers={"X-Playground-Visitor": "visitor-source-two"}
    ).status_code == 429
    assert "testclient" not in repr(module.VISITS)


def test_assets_are_allow_listed():
    client = TestClient(module.app)
    assert client.get("/assets/playground.css").status_code == 200
    assert client.get("/assets/i18n.js").status_code == 200
    assert client.get("/assets/anything.env").status_code == 404
    assert client.get("/locales/ru.json").status_code == 200
    assert client.get("/locales/de.json").status_code == 404


def test_oversized_request_is_rejected_before_json_parsing():
    response = TestClient(module.app).post(
        "/api/playground/runs",
        content=b"x" * 4097,
        headers={"content-type": "application/json", "X-Playground-Visitor": "visitor-size-test"},
    )
    assert response.status_code == 413


def test_upstream_error_details_are_not_returned(monkeypatch):
    monkeypatch.setattr(module, "runner", LeakyRunner())
    monkeypatch.setattr(module, "MAX_RUNS", 5)
    module.RUNS.clear(); module.RUN_OWNERS.clear(); module.VISITS.clear()
    with TestClient(module.app) as client:
        created = client.post(
            "/api/playground/runs", json={}, headers={"X-Playground-Visitor": "visitor-no-leak"}
        ).json()
        response = wait_for_terminal(client, created["run_id"], "visitor-no-leak")
    text = response.text
    assert "secret" not in text
    assert response.json()["error_code"] == "upstream_unavailable"


def test_run_result_is_private_to_visitor(monkeypatch):
    monkeypatch.setattr(module, "runner", FakeRunner())
    monkeypatch.setattr(module, "MAX_RUNS", 5)
    module.RUNS.clear(); module.RUN_OWNERS.clear(); module.VISITS.clear()
    client = TestClient(module.app)
    created = client.post(
        "/api/playground/runs", json={}, headers={"X-Playground-Visitor": "visitor-owner-123"}
    ).json()
    url = f"/api/playground/runs/{created['run_id']}"
    assert client.get(url, headers={"X-Playground-Visitor": "visitor-owner-123"}).status_code == 200
    assert client.get(url, headers={"X-Playground-Visitor": "visitor-other-456"}).status_code == 404
    assert client.get(url).status_code == 404
