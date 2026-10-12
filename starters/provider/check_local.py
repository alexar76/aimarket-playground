"""Run the generated provider and the Playground invoke profile locally."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

from onboarding_check.provider_check import main


def check() -> int:
    root = Path(__file__).resolve().parent
    os.chdir(root)
    command = [sys.executable, "agent.py"] if (root / "agent.py").exists() else ["node", "dist/src/agent.js"]
    env = {**os.environ, "HOST": "127.0.0.1", "PORT": "8080"}
    with open("provider.log", "w", encoding="utf-8") as log:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=log)
        try:
            for _ in range(100):
                if process.poll() is not None:
                    raise RuntimeError("Provider stopped; inspect provider.log (port 8080 must be free)")
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                raise RuntimeError("Provider did not become ready; inspect provider.log")
            return main(["capability.json", "--input", "test-input.json", "--allow-loopback"])
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    raise SystemExit(check())
