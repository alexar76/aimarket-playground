import json
import re
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "playground" / "static"
LANGS = ("en", "ru", "es", "fr", "zh")


def load_locale(lang: str) -> dict[str, str]:
    path = STATIC / "locales" / f"{lang}.json"

    def unique(pairs):
        result = {}
        for key, value in pairs:
            assert key not in result, f"{path.name}: duplicate key {key}"
            result[key] = value
        return result

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)


def test_five_locales_have_the_same_contract():
    locales = {lang: load_locale(lang) for lang in LANGS}
    expected = set(locales["en"])
    assert len(expected) >= 70
    for lang in LANGS[1:]:
        assert set(locales[lang]) == expected
        assert all(isinstance(value, str) and value.strip() for value in locales[lang].values())


def test_static_and_runtime_i18n_keys_exist():
    keys = set(load_locale("en"))
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    referenced = set(re.findall(r'data-i18n(?:-aria-label)?="([^"]+)"', html))
    javascript = (STATIC / "playground.js").read_text(encoding="utf-8")
    referenced |= set(re.findall(r'(?<!\w)(?:t|format)\("([^"]+)"', javascript))
    referenced |= set(re.findall(r'\["(error\.[A-Za-z]+)"\s*,', javascript))
    assert referenced <= keys, f"missing locale keys: {sorted(referenced - keys)}"


def test_glossary_canonical_terms_are_used():
    locales = {lang: load_locale(lang) for lang in LANGS}
    expected = {
        "ru": {"reading": "показание", "receipt": "квитанц", "verify": "верификац", "rails": "рельс"},
        "es": {"reading": "lectura", "receipt": "recibo", "verify": "verificaci", "rails": "rails"},
        "fr": {"reading": "lecture", "receipt": "reçu", "verify": "vérific", "rails": "rails"},
        "zh": {"reading": "读数", "receipt": "收据", "verify": "验证", "rails": "轨道"},
    }
    key_for = {
        "reading": "hero.lead",
        "receipt": "hero.lead",
        "verify": "hero.lead",
        "rails": "next.body",
    }
    for lang, terms in expected.items():
        for concept, term in terms.items():
            assert term.casefold() in locales[lang][key_for[concept]].casefold(), (lang, concept)


def test_identifiers_and_brands_are_never_translated():
    for lang in LANGS:
        locale = load_locale(lang)
        combined = "\n".join(locale.values())
        for token in ("AIMarket", "GAIA", "Hub", "Metis", "Ed25519", "Alien Monitor", "CLI", "LIVE"):
            assert token in combined, (lang, token)
        assert locale["metric.capability"] == "capability_id"


class GuideParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.articles = {}
        self.current = None
        self.in_code = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "article":
            self.current = {"text": [], "code": [], "headings": 0, "links": []}
            self.articles[attrs["lang"]] = self.current
            assert attrs["id"] == f'guide-{attrs["lang"]}'
        if self.current is not None:
            if tag == "h2":
                self.current["headings"] += 1
            if tag == "a":
                self.current["links"].append(attrs["href"])
            if tag == "code":
                self.in_code = True

    def handle_endtag(self, tag):
        if tag == "article":
            self.current = None
        if tag == "code":
            self.in_code = False

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"].append(data)
            if self.in_code:
                self.current["code"].append(data)


def test_guide_has_five_complete_locales_and_identical_code_contracts():
    parser = GuideParser()
    parser.feed((STATIC / "provider-guide.html").read_text(encoding="utf-8"))
    assert set(parser.articles) == set(LANGS)
    # Only placeholders in examples are translated, not CLI/API identifiers.
    def code_contract(article):
        return [re.sub(r"<[^>]+>", "<placeholder>", code) for code in article["code"]]

    expected_code = code_contract(parser.articles["en"])
    for lang, article in parser.articles.items():
        assert article["headings"] == 6
        assert len("".join(article["text"])) > 1800
        assert article["links"] == [f"/connect?lang={lang}"] * 3
        assert code_contract(article) == expected_code, lang
        for limit in ("443", "32", "64", "15", "16", "4096", "250", "20", "60", "500"):
            assert limit in "".join(article["text"]), (lang, limit)


def test_onboarding_uses_glossary_and_shared_playground_shell():
    parser = GuideParser()
    parser.feed((STATIC / "provider-guide.html").read_text(encoding="utf-8"))
    terms = {
        "ru": ("поставщик", "эндпоинт", "залог", "верификац", "Квитанци"),
        "es": ("proveedor", "endpoint", "garantía", "verificación", "recibos"),
        "fr": ("fournisseur", "point de terminaison (endpoint)", "dépôt de garantie", "vérification", "reçus"),
        "zh": ("提供方", "端点", "保证金", "验证", "收据"),
    }
    for lang, required in terms.items():
        text = "".join(parser.articles[lang]["text"])
        assert all(term in text for term in required), lang
    russian = "".join(parser.articles["ru"]["text"])
    assert not re.search(r"провайдер|стейк|endpoint", russian, re.I)
    assert "поставщик" in load_locale("ru")["nav.connect"]
    for name in ("connect.html", "provider-guide.html"):
        html = (STATIC / name).read_text(encoding="utf-8")
        assert "/assets/playground.css" in html
        assert "/assets/i18n.js" in html
        assert 'class="nav onboarding-nav"' in html
        assert 'class="scene"' in html
        assert 'class="scene-grid"' in html
        assert 'class="noise"' in html
        assert 'class="command-card"' in html
        assert set(re.findall(r'data-lang="([^"]+)"', html)) == set(LANGS)
