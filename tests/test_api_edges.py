import asyncio
import hashlib
import time

import pytest
from fastapi.testclient import TestClient

from playground import app as module


class FakeRunner:
    async def run(self, *, run_id, visitor, device_id, on_progress=None):
        return {"run_id": run_id, "status": "completed", "device_id": device_id}


class SlowRunner:
    async def run(self, **kwargs):
        await asyncio.sleep(1)
        return {"status": "completed"}


class RefusingRunner:
    async def run(self, **kwargs):
        raise RuntimeError("hub_refused:402")


@pytest.fixture(autouse=True)
def isolated_state():
    module.RUNS.clear()
    module.RUN_OWNERS.clear()
    module.VISITS.clear()
    yield
    module.RUNS.clear()
    module.RUN_OWNERS.clear()
    module.VISITS.clear()


def wait_for_terminal(client, run_id, visitor):
    for _ in range(100):
        response = client.get(
            f"/api/playground/runs/{run_id}", headers={"X-Playground-Visitor": visitor}
        )
        if response.json()["status"] not in {"running", "verifying"}:
            return response.json()
        time.sleep(0.01)
    raise AssertionError("background run did not finish")


def test_health_examples_and_index_contract():
    client = TestClient(module.app)
    health = client.get("/health")
    assert health.json() == {
        "ok": True,
        "golden_path": "gaia→metis→receipt",
        "arbitrary_code": False,
    }
    assert health.headers["x-frame-options"] == "DENY"
    assert "cache-control" not in health.headers

    example = client.get("/api/playground/examples")
    assert example.status_code == 200
    assert example.headers["cache-control"] == "no-store"
    assert example.json()["examples"][0]["default_input"] == {"device_id": "om-wx-01"}

    index = client.get("/")
    assert index.status_code == 200
    assert "AIMarket Playground" in index.text
    assert index.headers["referrer-policy"] == "no-referrer"
    assert index.headers["cross-origin-opener-policy"] == "same-origin"
    assert client.get("/docs").status_code == 404


@pytest.mark.parametrize("content_length", ["invalid", "-1", "4097"])
def test_invalid_content_length_is_rejected(content_length):
    response = TestClient(module.app).post(
        "/api/playground/runs",
        content=b"{}",
        headers={
            "content-type": "application/json",
            "content-length": content_length,
            "X-Playground-Visitor": "visitor-length-test",
        },
    )
    assert response.status_code == 413
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["detail"] == "request body must be 0-4096 bytes"


@pytest.mark.parametrize("device_id", ["", "bad/device", "x" * 65, "snowman-☃"])
def test_device_id_validation_fails_before_runner(device_id, monkeypatch):
    monkeypatch.setattr(module, "runner", FakeRunner())
    response = TestClient(module.app).post(
        "/api/playground/runs",
        json={"device_id": device_id},
        headers={"X-Playground-Visitor": "visitor-device-test"},
    )
    assert response.status_code == 422
    assert module.RUNS == {}


@pytest.mark.parametrize("visitor", ["1234567", "x" * 129])
def test_visitor_length_boundaries(visitor):
    response = TestClient(module.app).post(
        "/api/playground/runs", json={}, headers={"X-Playground-Visitor": visitor}
    )
    assert response.status_code == 400


def test_global_rate_limit_applies_across_visitors(monkeypatch):
    monkeypatch.setattr(module, "runner", FakeRunner())
    monkeypatch.setattr(module, "MAX_RUNS", 5)
    monkeypatch.setattr(module, "MAX_GLOBAL_RUNS", 1)
    client = TestClient(module.app)
    assert client.post(
        "/api/playground/runs", json={}, headers={"X-Playground-Visitor": "visitor-global-one"}
    ).status_code == 200
    assert client.post(
        "/api/playground/runs", json={}, headers={"X-Playground-Visitor": "visitor-global-two"}
    ).status_code == 429


def test_timeout_is_sanitized(monkeypatch):
    monkeypatch.setattr(module, "runner", SlowRunner())
    monkeypatch.setattr(module, "RUN_TIMEOUT_S", 0.001)
    with TestClient(module.app) as client:
        response = client.post(
            "/api/playground/runs", json={}, headers={"X-Playground-Visitor": "visitor-timeout"}
        )
        assert response.status_code == 200
        body = wait_for_terminal(client, response.json()["run_id"], "visitor-timeout")
    assert body["status"] == "failed"
    assert body["error_code"] == "upstream_timeout"


def test_allow_listed_hub_refusal_code_is_preserved(monkeypatch):
    monkeypatch.setattr(module, "runner", RefusingRunner())
    with TestClient(module.app) as client:
        response = client.post(
            "/api/playground/runs", json={}, headers={"X-Playground-Visitor": "visitor-refusal"}
        )
        assert response.status_code == 200
        body = wait_for_terminal(client, response.json()["run_id"], "visitor-refusal")
    assert body["error_code"] == "hub_refused:402"


def test_unknown_run_is_indistinguishable_from_foreign_run():
    response = TestClient(module.app).get(
        "/api/playground/runs/not-real",
        headers={"X-Playground-Visitor": "visitor-unknown"},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "run not found"}


def test_run_storage_trims_owner_mapping_together(monkeypatch):
    monkeypatch.setattr(module, "MAX_STORED_RUNS", 2)
    module.RUNS.update({"old": {}, "middle": {}, "new": {}})
    module.RUN_OWNERS.update({"old": "a", "middle": "b", "new": "c"})
    module._trim_runs()
    assert list(module.RUNS) == ["middle", "new"]
    assert module.RUN_OWNERS == {"middle": "b", "new": "c"}

    module.RUNS.clear()
    module.RUN_OWNERS.clear()
    module.RUNS.update({
        "running": {"status": "running"},
        "verifying": {"status": "verifying"},
        "complete": {"status": "completed"},
    })
    module.RUN_OWNERS.update({"running": "a", "verifying": "b", "complete": "c"})
    module._trim_runs()
    assert list(module.RUNS) == ["running", "verifying"]
    assert module.RUN_OWNERS == {"running": "a", "verifying": "b"}

    module.RUNS["running-2"] = {"status": "running"}
    module.RUN_OWNERS["running-2"] = "c"
    module._trim_runs()
    assert list(module.RUNS) == ["running", "verifying", "running-2"]
    assert module.RUN_OWNERS == {"running": "a", "verifying": "b", "running-2": "c"}


@pytest.mark.asyncio
async def test_orphaned_background_run_does_not_restore_private_result(monkeypatch):
    monkeypatch.setattr(module, "runner", FakeRunner())
    await module._execute_run(run_id="orphan", visitor="visitor-orphan", device_id="om-wx-01")
    assert "orphan" not in module.RUNS
    assert "orphan" not in module.RUN_OWNERS


def test_visit_pruning_removes_expired_entries_and_keeps_recent_ones():
    now = 10_000.0
    module.VISITS.update({"expired": [now - 3600], "mixed": [now - 4000, now - 10]})
    module._prune_visits(now)
    assert "expired" not in module.VISITS
    assert module.VISITS["mixed"] == [now - 10]


def test_owner_key_is_a_hash_not_the_visitor(monkeypatch):
    monkeypatch.setattr(module, "runner", FakeRunner())
    visitor = "visitor-private-value"
    body = TestClient(module.app).post(
        "/api/playground/runs", json={}, headers={"X-Playground-Visitor": visitor}
    ).json()
    assert module.RUN_OWNERS[body["run_id"]] == (
        "visitor:" + hashlib.sha256(visitor.encode()).hexdigest()
    )
    assert visitor not in repr(module.RUN_OWNERS)
