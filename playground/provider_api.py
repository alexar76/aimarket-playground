"""Short-lived, visitor-owned provider checks with explicit endpoint opt-in."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import secrets
import time
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException, Request

from .provider_check import CheckError, check_provider, read_json, validate_manifest
from .provider_http import pin_target, request_json

router = APIRouter(prefix="/api/provider-check")
CHALLENGES: dict[str, dict] = {}
VISITS: dict[str, list[float]] = {}
SLOTS = asyncio.Semaphore(4)
TTL = 900
MAX_CHALLENGES = 250
PROOF_PATH = "/.well-known/aimarket-provider-check.json"


def owner(request):
    visitor = request.headers.get("X-Playground-Visitor", "").strip()
    if not 8 <= len(visitor) <= 128:
        raise HTTPException(400, "X-Playground-Visitor must contain 8-128 characters")
    return hashlib.sha256(visitor.encode()).hexdigest()


def allowance(request):
    now = time.time()
    for key in list(VISITS):
        VISITS[key] = [stamp for stamp in VISITS[key] if now - stamp < 3600]
        if not VISITS[key]:
            del VISITS[key]
    source = request.client.host if request.client else "unknown"
    buckets = [("visitor:" + owner(request), 20), ("source:" + hashlib.sha256(source.encode()).hexdigest(), 60), ("global", 500)]
    if any(len(VISITS.get(key, [])) >= limit for key, limit in buckets):
        raise HTTPException(429, "Provider check hourly allowance used up")
    for key, _ in buckets:
        VISITS.setdefault(key, []).append(now)


def prune():
    for key in list(CHALLENGES):
        if CHALLENGES[key]["expires_at"] < time.time() and not CHALLENGES[key]["running"]:
            del CHALLENGES[key]


@router.post("/challenges")
async def challenge(request: Request):
    visitor = owner(request)
    allowance(request)
    prune()
    if len(CHALLENGES) >= MAX_CHALLENGES:
        raise HTTPException(503, "Provider check capacity reached; try again later")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 65_536:
            raise HTTPException(413, "Request exceeds 65536 bytes")
    try:
        payload = read_json(bytes(body))
        if not isinstance(payload, dict) or payload.get("consent") is not True:
            raise CheckError("Explicit consent to one test invoke is required")
        manifest, input_payload = payload.get("manifest"), payload.get("input")
        if isinstance(manifest, str):
            manifest = read_json(manifest.encode("utf-8"))
        if isinstance(input_payload, str):
            input_payload = read_json(input_payload.encode("utf-8"))
        validate_manifest(manifest, input_payload)
    except CheckError as exc:
        raise HTTPException(422, str(exc)) from exc
    challenge_id = secrets.token_hex(24)
    token = secrets.token_hex(32)
    expires_at = int(time.time()) + TTL
    url = urlsplit(manifest["invoke_url"])
    proof_url = urlunsplit(url._replace(path=PROOF_PATH))
    CHALLENGES[challenge_id] = {
        "owner": visitor, "token": token, "expires_at": expires_at, "proof_url": proof_url,
        "manifest": manifest, "input": input_payload, "running": False, "report": None, "attempts": 0,
    }
    return {"challenge_id": challenge_id, "expires_at": expires_at, "proof_url": proof_url,
            "proof": {"challenge": token}, "profile": "aimarket-provider-invoke/1"}


@router.post("/challenges/{challenge_id}/run")
async def run_check(challenge_id: str, request: Request):
    visitor = owner(request)
    prune()
    item = CHALLENGES.get(challenge_id)
    if item is None or not hmac.compare_digest(item["owner"], visitor):
        raise HTTPException(404, "Challenge expired or not found")
    if item["running"]:
        raise HTTPException(409, "Check is already running")
    if item["report"] is not None:
        return item["report"]
    allowance(request)
    if item["attempts"] >= 3:
        raise HTTPException(409, "Proof attempt limit reached; create a new challenge")
    if SLOTS.locked():
        raise HTTPException(429, "Provider check is busy; try again shortly")
    item["running"] = True
    item["attempts"] += 1
    invoked = False

    async def execute():
        nonlocal invoked
        # Ownership proof and invoke use the same validated IP and TLS hostname.
        pinned, headers, extensions = await pin_target(item["manifest"]["invoke_url"])

        async def send(method, url, **kwargs):
            target = urlunsplit(urlsplit(pinned)._replace(path=urlsplit(url).path))
            return await request_json(method, url, pinned=(target, headers, extensions), **kwargs)

        raw, _ = await send("GET", item["proof_url"])
        proof = read_json(raw)
        if not isinstance(proof, dict) or not isinstance(proof.get("challenge"), str) or not hmac.compare_digest(proof["challenge"].encode(), item["token"].encode()):
            raise CheckError("Endpoint ownership proof does not match this challenge")
        if item["expires_at"] < time.time():
            raise CheckError("Challenge expired; create a new challenge")
        invoked = True
        result = await check_provider(item["manifest"], item["input"], requester=send)
        result["checks"].insert(0, {"id": "endpoint_control", "status": "passed"})
        result["challenge_id"] = challenge_id
        return result

    try:
        async with SLOTS:
            item["report"] = await asyncio.wait_for(execute(), 25)
        return item["report"]
    except (CheckError, TimeoutError) as exc:
        if invoked:
            item["report"] = {"profile": "aimarket-provider-invoke/1", "status": "failed",
                              "checks": [{"id": "invoke", "status": "failed", "detail": "Invoke did not complete; it will not be retried"}]}
            return item["report"]
        raise HTTPException(422, str(exc) or "Ownership check timed out") from exc
    finally:
        # Cancellation after dispatch must also prevent a second invocation.
        if invoked and item["report"] is None:
            item["report"] = {"profile": "aimarket-provider-invoke/1", "status": "failed",
                              "checks": [{"id": "invoke", "status": "failed", "detail": "Invoke interrupted; outcome unknown"}]}
        item["running"] = False
