import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from playground.receipts import canonical_receipt, verify_receipt


def signed_receipt(version=1):
    private = Ed25519PrivateKey.generate()
    public = base64.b64encode(private.public_key().public_bytes_raw()).decode()
    receipt = {
        "nonce": "n-1", "product_id": "gaia.gateway", "capability_id": "gaia.weather.read@v1",
        "price_usd": 0.001, "timestamp": "2026-08-20T12:00:00Z", "success": True, "latency_ms": 42,
    }
    value = base64.b64encode(private.sign(canonical_receipt(receipt, version).encode())).decode()
    receipt["signature"] = {"algorithm": "ed25519", "version": version, "value": value}
    return receipt, public


def test_valid_origin_receipt_verifies():
    receipt, public = signed_receipt()
    assert verify_receipt(receipt, public).verified is True


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"expected_product_id": "another-product"}, "product-mismatch"),
        ({"expected_capability_id": "another.capability@v1"}, "capability-mismatch"),
        ({"require_success": True}, "invoke-not-successful"),
    ],
)
def test_valid_signature_must_also_match_the_expected_invoke(kwargs, reason):
    receipt, public = signed_receipt()
    if kwargs.get("require_success"):
        receipt["success"] = False
        private = Ed25519PrivateKey.generate()
        public = base64.b64encode(private.public_key().public_bytes_raw()).decode()
        receipt["signature"]["value"] = base64.b64encode(
            private.sign(canonical_receipt(receipt, 1).encode())
        ).decode()
    check = verify_receipt(receipt, public, **kwargs)
    assert check.verified is False
    assert check.reason == reason


def test_tampered_receipt_fails_closed():
    receipt, public = signed_receipt()
    receipt["price_usd"] = 999
    check = verify_receipt(receipt, public)
    assert check.verified is False
    assert check.reason == "invalid-signature"


def test_malformed_signature_never_raises():
    receipt, public = signed_receipt()
    receipt["signature"]["value"] = "!!!!"
    assert verify_receipt(receipt, public).reason == "malformed-signature-material"


def test_v2_signature_covers_extended_receipt_fields():
    receipt, public = signed_receipt(version=2)
    assert verify_receipt(receipt, public).reason == "ok"
    receipt["trace_id"] = "tampered"
    assert verify_receipt(receipt, public).reason == "invalid-signature"


def test_v1_signature_does_not_depend_on_v2_fields():
    receipt, public = signed_receipt(version=1)
    receipt["trace_id"] = "not-signed-by-v1"
    assert verify_receipt(receipt, public).verified is True


def test_receipt_shape_errors_return_specific_reasons():
    assert verify_receipt([], "").reason == "receipt-not-an-object"
    assert verify_receipt({}, "").reason == "missing-signature"
    assert verify_receipt({"signature": {}}, "").reason == "unsupported-signature-version"
    assert verify_receipt({"signature": {"algorithm": "rsa", "value": "x"}}, "").reason == (
        "unsupported-signature-algorithm"
    )


@pytest.mark.parametrize("version", [0, 3, "bad", None])
def test_unsupported_signature_versions_fail_closed(version):
    receipt = {"signature": {"algorithm": "ed25519", "version": version, "value": "x"}}
    assert verify_receipt(receipt, "").reason == "unsupported-signature-version"


@pytest.mark.parametrize(
    ("public_key", "signature"),
    [
        (base64.b64encode(b"short").decode(), base64.b64encode(b"x" * 64).decode()),
        (base64.b64encode(b"x" * 32).decode(), base64.b64encode(b"short").decode()),
        ("not-base64", base64.b64encode(b"x" * 64).decode()),
    ],
)
def test_malformed_key_or_signature_lengths_fail_closed(public_key, signature):
    receipt = {"signature": {"algorithm": "ed25519", "version": 1, "value": signature}}
    assert verify_receipt(receipt, public_key).reason == "malformed-signature-material"
