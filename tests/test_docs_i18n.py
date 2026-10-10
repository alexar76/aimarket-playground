from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = {
    "en": ROOT / "README.md",
    "ru": ROOT / "docs" / "README.ru.md",
    "es": ROOT / "docs" / "README.es.md",
    "fr": ROOT / "docs" / "README.fr.md",
    "zh": ROOT / "docs" / "README.zh.md",
}


def test_github_readme_and_five_language_navigation_are_complete():
    for lang, path in DOCS.items():
        assert path.is_file(), lang
        text = path.read_text(encoding="utf-8")
        assert "localization-glossary.md" in text
        assert "AIMarket" in text and "GAIA" in text and "Metis" in text and "Hub" in text
        assert "LIVE" in text and "PARTIAL" in text and "VERIFIED" in text
    root = DOCS["en"].read_text(encoding="utf-8")
    assert "<!-- aicom-readme-badges -->" in root
    assert (ROOT / ".github" / "workflows" / "ci.yml").is_file()


def test_documentation_uses_canonical_glossary_terms():
    required = {
        "ru": ("показание", "квитанц", "верификац", "рельс"),
        "es": ("lectura", "recibo", "verificaci", "rails"),
        "fr": ("lecture", "reçu", "vérific", "rails"),
        "zh": ("读数", "收据", "验证", "轨道"),
    }
    for lang, terms in required.items():
        text = DOCS[lang].read_text(encoding="utf-8").casefold()
        assert all(term.casefold() in text for term in terms), lang
