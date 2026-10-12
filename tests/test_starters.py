import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import zipfile

from fastapi.testclient import TestClient
import pytest

from playground.app import app

PROJECT = Path(__file__).resolve().parents[1]
STATIC = PROJECT / "playground/static"
CATALOG = json.loads((STATIC / "starters/catalog.json").read_text())


def test_developer_routes_are_fixed_and_safe():
    with TestClient(app) as client:
        page = client.get("/start")
        assert page.status_code == 200
        assert "script-src 'self'" in page.headers["content-security-policy"]
        for file in ["start.css", "start.js", "copy.svg"]:
            assert client.get(f"/assets/{file}").status_code == 200
        response = client.get("/starters/catalog.json")
        assert response.json() == CATALOG
        assert response.headers["cache-control"] == "no-cache"
        for name in ["secret.zip", "provider-ruby.zip", "../app.py", "%2e%2e%2fapp.py", ".env", "provider-python.zip/extra"]:
            assert client.get(f"/starters/{name}").status_code == 404


@pytest.mark.parametrize("key", CATALOG["kits"])
def test_starter_archives_have_sources_tests_and_no_keys(key):
    entry = CATALOG["kits"][key]
    with TestClient(app) as client:
        response = client.get(entry["url"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert 'attachment;' in response.headers["content-disposition"]
    assert len(response.content) == entry["bytes"]
    assert hashlib.sha256(response.content).hexdigest() == entry["sha256"]
    role, stack = key.split("-")
    prefix = f"aimarket-{role}/"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert sorted(name.removeprefix(prefix) for name in names) == entry["files"]
        assert all(name.startswith(prefix) and ".." not in Path(name).parts for name in names)
        assert all(not name.endswith((".key", "/.env", ".pyc")) for name in names)
        assert all("node_modules" not in name and "__pycache__" not in name for name in names)
        assert json.loads(archive.read(prefix + "SOURCES.json")) == CATALOG["sources"]
        assert prefix + ".github/workflows/onboarding.yml" in names
        for lang in ["en", "ru", "es", "fr", "zh"]:
            readme = archive.read(prefix + f"START.{lang}.md").decode()
            for command in entry["commands"]:
                assert command in readme
        if role == "provider":
            assert json.loads(archive.read(prefix + "capability.json"))["provider_pubkey"] == ""
            assert archive.read(prefix + "onboarding_check/provider_check.py") == (PROJECT / "playground/provider_check.py").read_bytes()
            assert archive.read(prefix + "onboarding_check/provider_http.py") == (PROJECT / "playground/provider_http.py").read_bytes()
        elif stack == "typescript":
            for name in ["market.ts", "models.ts", "errors.ts"]:
                source = f"aimarket-sdks/typescript/src/{name}"
                assert hashlib.sha256(archive.read(prefix + f"src/sdk/{name}")).hexdigest() == CATALOG["sources"][source]


def test_starters_are_current_with_canonical_sources():
    if not (PROJECT.parent / "create-aimarket-agent/src").is_dir():
        pytest.skip("Canonical generator/SDK freshness is checked in the monorepo; ZIP integrity is always tested")
    spec = importlib.util.spec_from_file_location("build_starters", PROJECT / "scripts/build_starters.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.inputs() == CATALOG["sources"], "Run scripts/build_starters.py after changing starter inputs"
    assert json.loads((PROJECT / "starters/catalog.json").read_text()) == {
        key: {field: entry[field] for field in ["requirements", "commands"]}
        for key, entry in CATALOG["kits"].items()
    }


def test_starter_languages_and_shared_shell():
    html = (STATIC / "start.html").read_text()
    for component in ["playground.css", 'class="scene"', 'class="scene-grid"', 'class="noise"', 'class="workspace"', 'class="command-card"']:
        assert component in html
    required = set(re.findall(r'data-i18n(?:-aria-label)?="([^"]+)"', html))
    for lang, provider, consumer in [("en", "Provider", "Consumer"), ("ru", "Поставщик", "Потребитель"),
                                     ("es", "Proveedor", "Consumidor"), ("fr", "Fournisseur", "Consommateur"),
                                     ("zh", "提供方", "消费方")]:
        messages = json.loads((STATIC / f"locales/{lang}.json").read_text())
        assert required <= messages.keys()
        assert messages["start.provider"] == provider
        assert messages["start.consumer"] == consumer
        for role in ["provider", "consumer"]:
            for key in ["summary", "step1", "step2", "step3", "note1", "note2", "note3", "scope", "next", "after", "afterNote"]:
                assert messages[f"start.{role}.{key}"]
        assert "attempt.json" in messages["start.consumer.scope"]
        assert "$0.01" in messages["start.consumer.note3"]
