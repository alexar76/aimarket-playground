"""Install and test all four downloaded projects. No public invoke or payment.

Requires Python 3.11+, Node.js 22+, package-registry access and free port 8080.
"""
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((PROJECT / "playground/static/starters/catalog.json").read_text())

for key, entry in CATALOG["kits"].items():
    with tempfile.TemporaryDirectory(prefix=f"{key}-") as temp:
        with zipfile.ZipFile(PROJECT / "playground/static/starters" / f"{key}.zip") as archive:
            archive.extractall(temp)
        root = Path(temp) / f"aimarket-{key.split('-')[0]}"
        commands = entry["commands"][0].splitlines()[1:]
        if key.startswith("provider"):
            commands.extend(entry["commands"][1].splitlines())
        for command in commands:
            print(f"{key}: {command}", flush=True)
            subprocess.run(command, shell=True, cwd=root, executable="/bin/sh", check=True)
        if key.startswith("provider"):
            report = json.loads((root / "report.json").read_text())
            assert report["status"] == "passed", report
            print(f"{key}: real local invocation and signature PASSED", flush=True)
        else:
            assert not (root / "attempt.json").exists()
            print(f"{key}: offline tests PASSED; no public invocation", flush=True)
