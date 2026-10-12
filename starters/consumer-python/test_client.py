import json
from pathlib import Path
import tempfile
import unittest

from client import CAPABILITY, PRODUCT, SOURCE, OnboardingError, run


class FakeClient:
    def __init__(self, *, verified=True, state="TASK_STATE_COMPLETED", price=0.001, receipt=None, timeout=False):
        self.calls = []
        self.verified, self.state, self.price = verified, state, price
        self.receipt = receipt if receipt is not None else {"product_id": PRODUCT, "capability_id": CAPABILITY, "success": True, "price_usd": 0.001}
        self.timeout = timeout

    def search(self, *args, **kwargs):
        return {"matches": [{"product_id": PRODUCT, "capability_id": CAPABILITY,
                             "source_hub": SOURCE, "price_per_call_usd": self.price}]}

    def invoke(self, *args, **kwargs):
        self.calls.append(kwargs)
        if self.timeout:
            raise TimeoutError("lost response")
        return {"status": {"state": self.state}, "receipt_verified": self.verified,
                "artifacts": [{"name": "aimarket-receipt", "parts": [{"data": self.receipt}]}]}


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        (self.directory / "input.json").write_text('{}')

    def test_discovery_never_invokes(self):
        client = FakeClient()
        run(client, directory=self.directory)
        self.assertEqual(client.calls, [])

    def test_one_call_and_no_automatic_repeat(self):
        client = FakeClient()
        run(client, invoke=True, directory=self.directory)
        self.assertEqual(client.calls[0]["max_price_usd"], 0.01)
        with self.assertRaises(FileExistsError):
            run(client, invoke=True, directory=self.directory)
        self.assertEqual(len(client.calls), 1)

    def test_price_and_budget_rejections(self):
        for price in [2, float("nan"), -1]:
            client = FakeClient(price=price)
            with self.assertRaises(OnboardingError):
                run(client, invoke=True, directory=self.directory)
            self.assertEqual(client.calls, [])
        with self.assertRaises(ValueError):
            run(FakeClient(), invoke=True, budget=float("nan"), directory=self.directory)

    def test_receipt_and_payment_fail_closed(self):
        for client in [FakeClient(verified=False), FakeClient(state="TASK_STATE_INPUT_REQUIRED")]:
            with self.subTest(state=client.state, verified=client.verified):
                with self.assertRaises(OnboardingError):
                    run(client, invoke=True, directory=self.directory)
                self.assertEqual(len(client.calls), 1)
                self.assertTrue((self.directory / "report.json").exists())
                (self.directory / "attempt.json").unlink()

    def test_valid_signature_for_wrong_receipt_is_not_success(self):
        for change in [{"product_id": "other"}, {"capability_id": "other"}, {"price_usd": 1},
                       {"price_usd": float("nan")}, {"price_usd": True}, {"success": False}]:
            receipt = {"product_id": PRODUCT, "capability_id": CAPABILITY, "success": True, "price_usd": 0.001, **change}
            with self.assertRaises(OnboardingError):
                run(FakeClient(receipt=receipt), invoke=True, directory=self.directory)
            (self.directory / "attempt.json").unlink()

    def test_lost_response_keeps_marker_and_never_retries(self):
        client = FakeClient(timeout=True)
        with self.assertRaises(TimeoutError):
            run(client, invoke=True, directory=self.directory)
        with self.assertRaises(FileExistsError):
            run(client, invoke=True, directory=self.directory)
        self.assertEqual(len(client.calls), 1)


if __name__ == "__main__":
    unittest.main()
