import json
import re
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
