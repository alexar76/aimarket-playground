from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

RECEIPT_V2_FIELDS = (
    "type", "channel_id", "category", "plugin", "reason", "verify_score",
    "delivery_reasons", "trace_id", "refunded",
)


@dataclass(frozen=True)
class ReceiptCheck:
    verified: bool
    reason: str


def _signed_version(receipt: dict[str, Any]) -> int:
    signature = receipt.get("signature")
    if not isinstance(signature, dict) or not signature.get("value"):
        return 0
    try:
        version = int(signature.get("version", 1))
    except (TypeError, ValueError):
        return 0
    return version if 1 <= version <= 2 else 0


def _fields_digest(receipt: dict[str, Any]) -> str:
    payload = {name: receipt.get(name) for name in RECEIPT_V2_FIELDS}
    encoded = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def canonical_receipt(receipt: dict[str, Any], version: int) -> str:
    base = (
        f"nonce:{receipt.get('nonce', '')}"
        f"|product_id:{receipt.get('product_id', '')}"
        f"|capability_id:{receipt.get('capability_id', '')}"
        f"|price_usd:{receipt.get('price_usd', 0)}"
        f"|timestamp:{receipt.get('timestamp', '')}"
        f"|success:{1 if receipt.get('success') else 0}"
        f"|latency_ms:{receipt.get('latency_ms', 0)}"
    )
    return base if version == 1 else f"{base}|v:2|fields:{_fields_digest(receipt)}"


def verify_receipt(
    receipt: Any,
    public_key_b64: str,
    *,
    expected_product_id: str | None = None,
    expected_capability_id: str | None = None,
    require_success: bool = False,
) -> ReceiptCheck:
    if not isinstance(receipt, dict):
        return ReceiptCheck(False, "receipt-not-an-object")
    signature = receipt.get("signature")
    if not isinstance(signature, dict):
        return ReceiptCheck(False, "missing-signature")
    if signature.get("algorithm") not in (None, "ed25519"):
        return ReceiptCheck(False, "unsupported-signature-algorithm")
    version = _signed_version(receipt)
    if version == 0:
        return ReceiptCheck(False, "unsupported-signature-version")
    try:
        key = base64.b64decode(public_key_b64, validate=True)
        sig = base64.b64decode(str(signature.get("value", "")), validate=True)
        if len(key) != 32 or len(sig) != 64:
            return ReceiptCheck(False, "malformed-signature-material")
        Ed25519PublicKey.from_public_bytes(key).verify(sig, canonical_receipt(receipt, version).encode())
        # A valid signature proves only what the signed receipt says. The caller
        # must also bind it to the invocation it just made; otherwise a genuine
        # receipt for another capability could be displayed as proof of this run.
        if expected_product_id is not None and receipt.get("product_id") != expected_product_id:
            return ReceiptCheck(False, "product-mismatch")
        if expected_capability_id is not None and receipt.get("capability_id") != expected_capability_id:
            return ReceiptCheck(False, "capability-mismatch")
        if require_success and receipt.get("success") is not True:
            return ReceiptCheck(False, "invoke-not-successful")
        return ReceiptCheck(True, "ok")
    except InvalidSignature:
        return ReceiptCheck(False, "invalid-signature")
    except (ValueError, TypeError, binascii.Error):
        return ReceiptCheck(False, "malformed-signature-material")
