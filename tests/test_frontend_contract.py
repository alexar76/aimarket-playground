import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "playground" / "static"


def test_javascript_id_selectors_exist_in_html():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    javascript = (STATIC / "playground.js").read_text(encoding="utf-8")
    html_ids = set(re.findall(r'\bid="([^"]+)"', html))
    selected_ids = set(re.findall(r'\$\("#([A-Za-z0-9_-]+)"\)', javascript))
    assert selected_ids
    assert selected_ids <= html_ids, f"missing DOM nodes: {sorted(selected_ids - html_ids)}"


def test_csp_compatible_markup_has_no_inline_scripts_or_styles():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"<script(?![^>]+\bsrc=)[^>]*>", html, re.IGNORECASE)
    assert " style=" not in html.lower()
    for tag in re.findall(r'<a\b[^>]*target="_blank"[^>]*>', html, re.IGNORECASE):
        assert re.search(r'\brel="[^"]*noopener[^"]*"', tag, re.IGNORECASE)
    assert "/assets/playground.css?v=" in html
    assert "/assets/i18n.js?v=" in html
    assert "/assets/playground.js?v=" in html
    assert 'id="copy-command" type="button" disabled aria-disabled="true"' in html
    assert "uvx searches PyPI by default" in html
    assert "github.com/alexar76/create-aimarket-agent" not in html


def test_localized_kicker_and_mobile_headers_are_not_fixed_height_text_boxes():
    css = (STATIC / "playground.css").read_text(encoding="utf-8")

    assert ".kicker>span:first-child" in css
    assert ".kicker>span:last-child{min-width:0;overflow-wrap:anywhere}" in css
    assert ".kicker span{" not in css
    assert "font-size:clamp(2.9rem,15vw,3.6rem)" in css
    assert "@media(max-width:480px){.workspace-head{display:grid" in css
    assert "grid-template-columns:auto minmax(0,1fr) auto" in css
    assert ".run-button span{min-width:0;overflow-wrap:anywhere" in css


def test_visible_metis_example_uses_server_side_bearer_auth_without_a_secret():
    html = (STATIC / "index.html").read_text(encoding="utf-8")

    assert "METIS_API_KEY" in html
    assert 'class="str">"Authorization"' in html
    assert "os.environ['METIS_API_KEY']" in html
    assert "PLAYGROUND_METIS_KEY=" not in html


def test_locale_values_are_plain_text_not_markup():
    for path in (STATIC / "locales").glob("*.json"):
        values = json.loads(path.read_text(encoding="utf-8")).values()
        assert all("<script" not in value.casefold() and "javascript:" not in value.casefold() for value in values)


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
@pytest.mark.parametrize("filename", ["i18n.js", "playground.js"])
def test_browser_javascript_parses(filename):
    result = subprocess.run(
        [shutil.which("node"), "--check", str(STATIC / filename)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_frontend_polls_async_run_and_renders_metis_progress():
    javascript = (STATIC / "playground.js").read_text(encoding="utf-8")
    assert "async function pollRun" in javascript
    assert "/api/playground/runs/${encodeURIComponent(runId)}" in javascript
    assert 'body.status === "verifying"' in javascript
    assert "showVerifying(body, elapsed)" in javascript
    assert 't("metric.pending", "PENDING")' in javascript
    assert 'body.verification?.timeout_source === "metis"' in javascript
    assert 't("step.metis.unavailable"' in javascript
    assert 'format("step.metis.rejected"' in javascript
    assert 'body.verification?.assessment_verdict === "implausible"' in javascript
    assert 't("step.metis.unstructured"' in javascript


def test_timeout_budgets_and_fast_route_are_consistent_across_runtime_files():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    javascript = (STATIC / "playground.js").read_text(encoding="utf-8")

    for text in (compose, env_example):
        assert "PLAYGROUND_RUN_TIMEOUT_S" in text and "640" in text
        assert "PLAYGROUND_METIS_TIMEOUT_S" in text and "620" in text
        assert "PLAYGROUND_METIS_ROUTE" in text and "fast" in text
        assert "PLAYGROUND_METIS_KEY" in text
        assert "PLAYGROUND_MAX_RUNS_PER_SOURCE_PER_HOUR" in text
    assert 'class="str">"fast"' in html
    assert "const deadlineMs = 650000" in javascript


def test_upstream_hub_rate_limit_is_presented_as_a_rate_limit():
    javascript = (STATIC / "playground.js").read_text(encoding="utf-8")

    assert 'code === "hub_refused:429" ? "hub_rate_limited" : code' in javascript
    assert 'response.status === 429 ? "local_rate_limited"' in javascript
    assert '"hub_rate_limited": ["error.hubRateLimited"' in javascript
    assert '"local_rate_limited": ["error.localRateLimited"' in javascript


def test_negative_verdict_is_not_presented_as_a_service_error():
    javascript = (STATIC / "playground.js").read_text(encoding="utf-8")

    assert 't("step.rejected", "NOT VERIFIED")' in javascript
    assert '["timeout", "unavailable", "error"].includes(metisStatus)' in javascript
    assert 'markStep("metis", metisState, metisDetail)' in javascript


def test_missing_verifier_is_distinct_from_a_negative_verdict():
    javascript = (STATIC / "playground.js").read_text(encoding="utf-8")

    assert 'metisStatus === "not_performed"' in javascript
    assert 't("step.metis.notPerformed"' in javascript
    assert 't("step.notPerformed", "NOT CHECKED")' in javascript
    assert 'body.verification?.verify_performed === false' in javascript


def test_metis_assessment_is_rendered_as_bounded_plain_text():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    javascript = (STATIC / "playground.js").read_text(encoding="utf-8")

    assert 'id="assessment-card"' in html
    assert 'id="assessment"' in html
    assert 'body.verification?.assessment?.trim()' in javascript
    assert '$("#assessment").textContent = assessment || ""' in javascript
