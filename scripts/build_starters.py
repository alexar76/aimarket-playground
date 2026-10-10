"""Build reproducible offline-source starter ZIPs from the canonical generators/SDKs.

Run with Node.js on PATH. --check rebuilds and compares without writing artifacts.
Only build-time code executes here; the public server serves four fixed ZIP files.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parent
OUTPUT = PROJECT / "playground/static/starters"
sys.path.insert(0, str(ROOT / "create-aimarket-agent/src"))
from create_aimarket_agent.cli import scaffold  # noqa: E402


def copy_tree(source, target):
    shutil.copytree(source, target, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))


def inputs():
    paths = [Path(__file__), *sorted((PROJECT / "starters").rglob("*"))]
    for folder in ["create-aimarket-agent/src", "create-aimarket-agent/npm/src",
                   "create-aimarket-agent/npm/templates", "aimarket-agent/aimarket_agent"]:
        paths.extend(sorted((ROOT / folder).rglob("*")))
    for name in ["provider_check.py", "provider_http.py"]:
        paths.append(PROJECT / "playground" / name)
    for name in ["market.ts", "models.ts", "errors.ts"]:
        paths.append(ROOT / "aimarket-sdks/typescript/src" / name)
    for name in ["pyproject.toml", "README.md", "LICENSE"]:
        paths.append(ROOT / "aimarket-agent" / name)
    paths.extend([ROOT / "aimarket-sdks/LICENSE", PROJECT / "LICENSE"])
    paths.extend(sorted((PROJECT / "playground/static/locales").glob("*.json")))
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(set(paths)) if path.is_file()
            and "__pycache__" not in path.parts and path.suffix != ".pyc" and path.name != ".DS_Store"}


def archive(tree):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as file:
        for path in sorted(tree.rglob("*")):
            if path.is_file():
                info = zipfile.ZipInfo(str(Path(tree.name) / path.relative_to(tree)), (2026, 1, 1, 0, 0, 0))
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                file.writestr(info, path.read_bytes())
    return stream.getvalue()


def build():
    config = json.loads((PROJECT / "starters/catalog.json").read_text())
    source_hashes = inputs()
    artifacts = {}
    for key, entry in config.items():
        role, language = key.split("-")
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / f"aimarket-{role}"
            if role == "provider":
                if language == "python":
                    scaffold(target, name="my-provider", kind="tool", metis=False)
                else:
                    module = (ROOT / "create-aimarket-agent/npm/src/scaffold.mjs").as_uri()
                    subprocess.run(["node", "--input-type=module", "-e",
                                    f"import {{ scaffold }} from {json.dumps(module)}; "
                                    "scaffold(process.argv[1], {name:'my-provider',kind:'tool',metis:false});",
                                    str(target)], check=True)
                copy_tree(PROJECT / "starters/provider", target)
                checker = target / "onboarding_check"
                checker.mkdir()
                (checker / "__init__.py").write_text("")
                for name in ["provider_check.py", "provider_http.py"]:
                    shutil.copyfile(PROJECT / "playground" / name, checker / name)
                with (target / ".gitignore").open("a") as file:
                    file.write("\nreport.json\nprovider.log\n")
            else:
                copy_tree(PROJECT / "starters" / key, target)
                (target / ".gitignore").write_text(".venv/\nnode_modules/\ndist/\n__pycache__/\n.env\nattempt.json\nreport.json\n")
                if language == "python":
                    vendor = target / "vendor/aimarket-agent"
                    copy_tree(ROOT / "aimarket-agent/aimarket_agent", vendor / "aimarket_agent")
                    for name in ["pyproject.toml", "README.md", "LICENSE"]:
                        shutil.copyfile(ROOT / "aimarket-agent" / name, vendor / name)
                else:
                    vendor = target / "src/sdk"
                    vendor.mkdir()
                    for name in ["market.ts", "models.ts", "errors.ts"]:
                        shutil.copyfile(ROOT / "aimarket-sdks/typescript/src" / name, vendor / name)
                    shutil.copyfile(ROOT / "aimarket-sdks/LICENSE", vendor / "LICENSE")
            shutil.copyfile(PROJECT / "LICENSE", target / "LICENSE")
            workflow = target / ".github/workflows/onboarding.yml"
            workflow.parent.mkdir(parents=True, exist_ok=True)
            setup = entry["commands"][0].splitlines()[1:]
            checks = entry["commands"][1].splitlines() if role == "provider" else []
            workflow.write_text(
                "name: Onboarding\non: [push, pull_request]\npermissions:\n  contents: read\n"
                "jobs:\n  check:\n    runs-on: ubuntu-latest\n    steps:\n"
                "      - uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683  # v4.2.2\n        with:\n          persist-credentials: false\n"
                "      - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065  # v5.6.0\n        with:\n          python-version: '3.12'\n"
                "      - uses: actions/setup-node@49933ea5288caeca8642d1e84afbd3f7d6820020  # v4.4.0\n        with:\n          node-version: '22'\n"
                "      - run: |\n" + "".join(f"          {line}\n" for line in setup + checks))
            (target / "SOURCES.json").write_text(json.dumps(source_hashes, indent=2) + "\n")
            for lang in ["en", "ru", "es", "fr", "zh"]:
                messages = json.loads((PROJECT / f"playground/static/locales/{lang}.json").read_text())
                lines = [f"# AIMarket / {messages['start.' + role]}", "", messages[f"start.{role}.summary"], ""]
                for step in range(1, 4):
                    lines.extend([f"## {step}. {messages[f'start.{role}.step{step}']}", "",
                                  messages[f"start.{role}.note{step}"], "", "```sh",
                                  entry["commands"][step - 1], "```", ""])
                lines.extend([messages[f"start.{role}.scope"], "", messages["start.snapshot"], "",
                              f"https://play.modelmarket.dev/start?role={role}&stack={language}&lang={lang}", ""])
                (target / f"START.{lang}.md").write_text("\n".join(lines), encoding="utf-8")
            contents = archive(target)
            filename = f"{key}.zip"
            artifacts[filename] = contents
            entry.update({"url": f"/starters/{filename}", "sha256": hashlib.sha256(contents).hexdigest(),
                          "bytes": len(contents), "files": sorted(str(path.relative_to(target)) for path in target.rglob("*") if path.is_file())})
    artifacts["catalog.json"] = (json.dumps({"version": 1, "sources": source_hashes, "kits": config}, ensure_ascii=False, indent=2) + "\n").encode()
    return artifacts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, contents in build().items():
        path = OUTPUT / name
        if args.check:
            if not path.exists() or path.read_bytes() != contents:
                raise SystemExit(f"Stale starter: {name}; run scripts/build_starters.py")
        else:
            OUTPUT.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        print(name)
