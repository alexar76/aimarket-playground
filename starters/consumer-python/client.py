"""Read-only discovery by default; one explicit, price-capped A2A invocation."""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import uuid

from aimarket_agent.a2a import A2AClient, COMPLETED, task_receipt, task_state

HUB = "https://modelmarket.dev"
PRODUCT = "gaia.gateway"
CAPABILITY = "gaia.weather.read@v1"
SOURCE = "https://iot.modelmarket.dev"


class OnboardingError(Exception):
    pass


def run(client, *, invoke=False, budget=0.01, directory=Path(".")):
    if not math.isfinite(budget) or not 0 <= budget <= 1:
        raise ValueError("Budget must be finite and between 0 and 1 USD")
    offers = client.search("GAIA weather", budget=budget, limit=10)
    if not invoke:
        return offers
    candidates = [offer for offer in offers.get("matches", [])
                  if offer.get("product_id") == PRODUCT and offer.get("capability_id") == CAPABILITY
                  and offer.get("source_hub") == SOURCE]
    if not candidates:
        raise OnboardingError("GAIA weather offer not found; no invocation was sent")
    price = float(candidates[0].get("routed_price_usd", candidates[0].get("price_per_call_usd", "nan")))
    if not math.isfinite(price) or not 0 <= price <= budget:
        raise OnboardingError("Offer exceeds budget or has no valid price; no invocation was sent")
    payload = json.loads((directory / "input.json").read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("input.json must contain an object")
    # The marker survives lost responses. A second run must never silently charge again.
    marker = directory / "attempt.json"
    message_id = str(uuid.uuid4())
    with marker.open("x", encoding="utf-8") as file:
        json.dump({"message_id": message_id, "hub": HUB, "max_price_usd": budget}, file)
    task = client.invoke(PRODUCT, CAPABILITY, payload, source_hub=SOURCE,
                         max_price_usd=budget, message_id=message_id)
    (directory / "report.json").write_text(json.dumps(task, indent=2, ensure_ascii=False), encoding="utf-8")
    if task_state(task) != COMPLETED:
        raise OnboardingError("Task did not complete; inspect report.json. No automatic payment or retry was made")
    if task.get("receipt_verified") is not True:
        raise OnboardingError("Receipt verification failed; do not trust the result. Inspect report.json")
    receipt = task_receipt(task) or {}
    price = receipt.get("price_usd")
    if (receipt.get("product_id") != PRODUCT or receipt.get("capability_id") != CAPABILITY
            or receipt.get("success") is not True or type(price) not in (int, float)
            or not math.isfinite(price) or not 0 <= price <= budget):
        raise OnboardingError("Receipt does not match this successful, price-capped invocation; inspect report.json")
    return task


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--invoke", action="store_true")
    parser.add_argument("--budget", type=float, default=0.01)
    args = parser.parse_args()
    client = A2AClient(HUB, api_key=os.getenv("AIMARKET_API_KEY", ""), verify_receipts=True)
    try:
        print(json.dumps(run(client, invoke=args.invoke, budget=args.budget), indent=2, ensure_ascii=False))
    except OnboardingError as error:
        print(str(error))
        raise SystemExit(1) from None
    except FileExistsError:
        print("attempt.json already exists. Reconcile that attempt before authorizing another invocation.")
        raise SystemExit(1) from None
    except Exception as error:
        # Do not print arbitrary transport messages that could include credentials.
        print(f"Stopped ({type(error).__name__}). Inspect attempt.json / report.json; do not retry blindly.")
        raise SystemExit(1) from None
    finally:
        client.session.close()


if __name__ == "__main__":
    main()
