import httpx
import pytest

from playground.runner import GoldenPathRunner


@pytest.mark.asyncio
async def test_string_false_is_not_treated_as_verified():
    runner = GoldenPathRunner()

    async def handler(request):
        return httpx.Response(200, json={"verified": "false", "status": "complete", "verify_score": 0.2})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verdict = await runner._verify(client, {"reading": 1})
    assert verdict["verified"] is False


@pytest.mark.asyncio
async def test_successful_metis_assessment_is_bounded_for_transparent_ui():
    runner = GoldenPathRunner()

    async def handler(request):
        return httpx.Response(200, json={
            "answer": "  VERDICT: plausible\n" + "x" * 3000,
            "verified": True,
            "status": "success",
            "verify_performed": True,
            "verify_score": 0.9,
            "route": "fast",
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verdict = await runner._verify(client, {"reading": 1})
    assert verdict["assessment"].startswith("VERDICT: plausible")
    assert len(verdict["assessment"]) == 2000
    assert verdict["verified"] is True
    assert verdict["assessment_verdict"] == "plausible"
    assert verdict["assessment_verified"] is True


def test_verification_task_has_explicit_success_criteria_and_untrusted_delimiters():
    task = GoldenPathRunner._verification_task({"reading": {"temperature_c": 21.5}})
    assert "VERDICT (plausible or implausible)" in task
    assert "CHECKS (the fields examined)" in task
    assert "LIMITATION" in task
    assert "Trusted Playground request time is" in task
    assert "allow ten minutes of clock skew" in task
    assert "BEGIN GAIA OUTPUT" in task and "END GAIA OUTPUT" in task
    assert '"temperature_c":21.5' in task


@pytest.mark.asyncio
async def test_verified_metis_answer_with_implausible_verdict_does_not_turn_ui_green():
    runner = GoldenPathRunner()

    async def handler(request):
        return httpx.Response(200, json={
            "answer": "VERDICT: implausible\nCHECKS: impossible pressure\nLIMITATION: not proof",
            "verified": True,
            "status": "success",
            "verify_performed": True,
            "verify_score": 1.0,
            "route": "fast",
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verdict = await runner._verify(client, {"reading": 1})
    assert verdict["assessment_verified"] is True
    assert verdict["assessment_verdict"] == "implausible"
    assert verdict["verified"] is False


@pytest.mark.asyncio
async def test_verified_metis_answer_without_structured_verdict_fails_closed():
    runner = GoldenPathRunner()

    async def handler(request):
        return httpx.Response(200, json={
            "answer": "The reading looks fine.",
            "verified": True,
            "status": "success",
            "verify_performed": True,
            "verify_score": 1.0,
            "route": "fast",
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verdict = await runner._verify(client, {"reading": 1})
    assert verdict["assessment_verdict"] == "unknown"
    assert verdict["verified"] is False


@pytest.mark.asyncio
async def test_metis_network_failure_degrades_without_leaking_details():
    runner = GoldenPathRunner()

    async def handler(request):
        raise httpx.ConnectError("secret internal hostname", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verdict = await runner._verify(client, {"reading": 1})
    assert verdict == {"status": "unavailable", "verified": False}


@pytest.mark.asyncio
async def test_metis_timeout_is_distinct_from_unavailability():
    runner = GoldenPathRunner()

    async def handler(request):
        raise httpx.ReadTimeout("slow council", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verdict = await runner._verify(client, {"reading": 1})
    assert verdict == {"status": "timeout", "verified": False, "timeout_source": "playground"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (
            {"status": "error", "error": "timeout", "verify_score": 0, "route": "council"},
            {
                "status": "timeout", "verified": False, "verify_score": 0,
                "route": "council", "timeout_source": "metis",
            },
        ),
        (
            {"status": "error", "error": "SecretProviderFailure", "verify_score": 0, "route": "council"},
                {
                    "status": "error", "verified": False, "verify_performed": False,
                    "verify_score": 0, "route": "council",
                },
        ),
        (
            {"error": "SecretProviderFailure", "verify_score": 0, "route": "council"},
                {
                    "status": "error", "verified": False, "verify_performed": False,
                    "verify_score": 0, "route": "council",
                },
        ),
    ],
)
async def test_metis_error_envelope_is_normalized_without_leaking_details(body, expected):
    runner = GoldenPathRunner()

    async def handler(request):
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        verdict = await runner._verify(client, {"reading": 1})
    assert verdict == expected
    assert "SecretProviderFailure" not in repr(verdict)


@pytest.mark.asyncio
async def test_response_size_is_bounded():
    runner = GoldenPathRunner()
    runner.max_response_bytes = 32
    async def handler(request):
        return httpx.Response(200, content=b'{"value":"' + b"x" * 100 + b'"}')
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError, match="upstream_response_too_large"):
            await runner._get_json(client, "https://example.test/data")


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "http://public.example", "https://user:pass@example.com", "https://example.com/?next=x"
])
def test_public_upstream_urls_fail_closed(url):
    with pytest.raises(ValueError):
        GoldenPathRunner._absolute_url(url, allow_http=False)


def test_event_ingestion_requires_authentication(monkeypatch):
    monkeypatch.setenv("PLAYGROUND_EVENT_URL", "https://events.example.test/ingest")
    monkeypatch.delenv("PLAYGROUND_EVENT_TOKEN", raising=False)
    with pytest.raises(ValueError, match="PLAYGROUND_EVENT_TOKEN"):
        GoldenPathRunner()
