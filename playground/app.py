from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .runner import GoldenPathRunner

app = FastAPI(
    title="AIMarket Playground",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
logger = logging.getLogger(__name__)
runner = GoldenPathRunner()
RUNS: dict[str, dict[str, Any]] = {}
RUN_OWNERS: dict[str, str] = {}
VISITS: dict[str, list[float]] = {}
MAX_RUNS = max(1, min(int(os.getenv("PLAYGROUND_MAX_RUNS_PER_HOUR", "5")), 100))
MAX_SOURCE_RUNS = max(
    MAX_RUNS,
    min(int(os.getenv("PLAYGROUND_MAX_RUNS_PER_SOURCE_PER_HOUR", "25")), 500),
)
MAX_GLOBAL_RUNS = max(MAX_RUNS, min(int(os.getenv("PLAYGROUND_MAX_GLOBAL_RUNS_PER_HOUR", "500")), 10000))
MAX_CONCURRENCY = max(1, min(int(os.getenv("PLAYGROUND_MAX_CONCURRENCY", "8")), 64))
RUN_TIMEOUT_S = max(5.0, min(float(os.getenv("PLAYGROUND_RUN_TIMEOUT_S", "640")), 650.0))
MAX_STORED_RUNS = max(1, min(int(os.getenv("PLAYGROUND_MAX_STORED_RUNS", "100")), 500))
RUN_SLOTS = asyncio.Semaphore(MAX_CONCURRENCY)
ACTIVE_TASKS: set[asyncio.Task[Any]] = set()
STATIC = Path(__file__).with_name("static")


class RunRequest(BaseModel):
    device_id: str = Field(default="om-wx-01", pattern=r"^[A-Za-z0-9._-]{1,64}$")


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "golden_path": "gaia→metis→receipt", "arbitrary_code": False}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = None
    if request.method == "POST" and request.url.path == "/api/playground/runs":
        raw_length = request.headers.get("content-length")
        try:
            content_length = int(raw_length) if raw_length is not None else -1
        except ValueError:
            content_length = -1
        if content_length < 0 or content_length > 4096:
            response = JSONResponse({"detail": "request body must be 0-4096 bytes"}, status_code=413)
    if response is None:
        response = await call_next(request)
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/playground/examples")
def examples() -> dict[str, Any]:
    return {"examples": [{
        "id": "gaia-weather",
        "title": "Verify a live GAIA weather reading",
        "capability_id": "gaia.weather.read@v1",
        "default_input": {"device_id": "om-wx-01"},
    }]}


@app.post("/api/playground/runs")
async def create_run(
    request: Request,
    payload: RunRequest,
    x_playground_visitor: str = Header(default=""),
) -> dict[str, Any]:
    visitor = x_playground_visitor.strip()
    if not (8 <= len(visitor) <= 128):
        raise HTTPException(400, "X-Playground-Visitor must contain 8-128 characters")
    now = time.time()
    visitor_key = f"visitor:{hashlib.sha256(visitor.encode('utf-8')).hexdigest()}"
    source = request.client.host if request.client is not None else "unknown"
    source_key = f"source:{hashlib.sha256(source.encode('utf-8')).hexdigest()}"
    global_key = "global"
    _prune_visits(now)
    recent = VISITS.get(visitor_key, [])
    source_recent = VISITS.get(source_key, [])
    global_recent = VISITS.get(global_key, [])
    if (
        len(recent) >= MAX_RUNS
        or len(source_recent) >= MAX_SOURCE_RUNS
        or len(global_recent) >= MAX_GLOBAL_RUNS
    ):
        raise HTTPException(429, "Playground hourly run allowance used up")
    VISITS[visitor_key] = recent + [now]
    VISITS[source_key] = source_recent + [now]
    VISITS[global_key] = global_recent + [now]
    run_id = uuid.uuid4().hex
    RUNS[run_id] = {"run_id": run_id, "status": "running", "stage": "gaia"}
    RUN_OWNERS[run_id] = visitor_key
    task = asyncio.create_task(
        _execute_run(run_id=run_id, visitor=visitor, device_id=payload.device_id),
        name=f"playground-run-{run_id[:12]}",
    )
    ACTIVE_TASKS.add(task)
    task.add_done_callback(ACTIVE_TASKS.discard)
    _trim_runs()
    return RUNS[run_id]


async def _execute_run(*, run_id: str, visitor: str, device_id: str) -> None:
    def store_result(result: dict[str, Any]) -> None:
        if run_id not in RUN_OWNERS:
            return
        RUNS[run_id] = result
        _trim_runs()

    async def publish_progress(result: dict[str, Any]) -> None:
        store_result(result)

    async def execute() -> dict[str, Any]:
        async with RUN_SLOTS:
            return await runner.run(
                run_id=run_id,
                visitor=visitor,
                device_id=device_id,
                on_progress=publish_progress,
            )

    try:
        result = await asyncio.wait_for(execute(), timeout=RUN_TIMEOUT_S)
    except asyncio.TimeoutError:
        result = {"run_id": run_id, "status": "failed", "error_code": "upstream_timeout"}
    except Exception as exc:
        logger.warning("playground run failed run_id=%s error=%s", run_id, str(exc)[:300])
        code = str(exc) if str(exc).startswith(("hub_refused:", "hub_returned_")) else "upstream_unavailable"
        result = {"run_id": run_id, "status": "failed", "error_code": code}
    store_result(result)


@app.get("/api/playground/runs/{run_id}")
def get_run(run_id: str, x_playground_visitor: str = Header(default="")) -> dict[str, Any]:
    if run_id not in RUNS:
        raise HTTPException(404, "run not found")
    visitor_key = f"visitor:{hashlib.sha256(x_playground_visitor.strip().encode('utf-8')).hexdigest()}"
    if not hmac.compare_digest(RUN_OWNERS.get(run_id, ""), visitor_key):
        # Deliberately hide whether another visitor's run exists.
        raise HTTPException(404, "run not found")
    return RUNS[run_id]


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/assets/{name}", include_in_schema=False)
def asset(name: str) -> FileResponse:
    if name not in {"playground.css", "playground.js", "i18n.js"}:
        raise HTTPException(404, "asset not found")
    return FileResponse(STATIC / name)


@app.get("/locales/{lang}.json", include_in_schema=False)
def locale(lang: str) -> FileResponse:
    if lang not in {"en", "ru", "es", "fr", "zh"}:
        raise HTTPException(404, "locale not found")
    return FileResponse(STATIC / "locales" / f"{lang}.json", media_type="application/json")


def _trim_runs() -> None:
    while len(RUNS) > MAX_STORED_RUNS:
        oldest = next(
            (run_id for run_id, result in RUNS.items()
             if result.get("status") not in {"running", "verifying"}),
            None,
        )
        if oldest is None:
            break
        RUNS.pop(oldest)
        RUN_OWNERS.pop(oldest, None)


def _prune_visits(now: float) -> None:
    for key in list(VISITS):
        recent = [stamp for stamp in VISITS[key] if now - stamp < 3600]
        if recent:
            VISITS[key] = recent
        else:
            VISITS.pop(key, None)
