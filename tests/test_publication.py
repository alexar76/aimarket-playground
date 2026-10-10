import json
import re
from pathlib import Path

from fastapi.testclient import TestClient
from playground.app import app

STATIC = Path(__file__).resolve().parents[1] / "playground" / "static"


def test_publication_page_and_all_five_locales():
    with TestClient(app) as client:
        response = client.get("/publish?lang=ru")
    assert response.status_code == 200
    html = response.text
    keys = set(re.findall(r'data-i18n="([^"]+)"', html))
    for lang in ("en", "ru", "es", "fr", "zh"):
        copy = json.loads((STATIC / "locales" / f"{lang}.json").read_text())
        assert keys <= copy.keys()
        assert f'data-lang="{lang}"' in html
    assert "https://modelmarket.dev/ai-market/v2/supply/register" in html
    assert "X-API-Key:" in html
    assert "AIMARKET_PUBLISH_TOKEN" not in html
    assert "/supply/policy" in html
    assert "/supply/stake" in html
    assert "AIMARKET_STAKE_USD:?" in html
    assert "https://modelmarket.dev/start?role=provider" in html
    assert "<form" not in html
    assert "playground.css" in html


def test_start_links_separate_registration_and_account():
    script = (STATIC / "start.js").read_text()
    assert "'/publish' : 'https://modelmarket.dev/start'" in script
    assert 'id="after-link"' in (STATIC / "start.html").read_text()
