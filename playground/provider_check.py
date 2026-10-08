"""Provider invoke profile v1. This is not whole-protocol certification."""
from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from .provider_http import CheckError, parse_target, request_json

PROFILE = "aimarket-provider-invoke/1"
MAX_DOCUMENT = 65_536
SCHEMA_KEYS = {"$schema", "title", "description", "type", "properties", "required", "additionalProperties",
               "items", "enum", "const", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
               "minLength", "maxLength", "minItems", "maxItems", "minProperties", "maxProperties"}


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def read_json(raw: bytes):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise CheckError("JSON contains duplicate object keys")
            result[key] = value
        return result

    def constant(_):
        raise CheckError("JSON numbers must be finite")

    if len(raw) > MAX_DOCUMENT:
        raise CheckError("JSON exceeds 65536 bytes")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique, parse_constant=constant)
        stack = [(value, 0)]
        nodes = 0
        while stack:
            item, depth = stack.pop()
            nodes += 1
            if depth > 16 or nodes > 4096:
                raise CheckError("JSON exceeds the profile depth or node limit")
            if isinstance(item, dict):
                stack.extend((v, depth + 1) for v in item.values())
            elif isinstance(item, list):
                stack.extend((v, depth + 1) for v in item)
        canonical(value)
        return value
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise CheckError(str(exc) if isinstance(exc, CheckError) else "invalid UTF-8 JSON or non-finite number") from exc


def validate_schema(schema, label: str) -> None:
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise CheckError(f"{label}.type must be object")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise CheckError(f"{label} is not a valid JSON Schema") from exc
    stack = [schema]
    while stack:
        item = stack.pop()
        if isinstance(item, bool):
            continue
        unsupported = set(item) - SCHEMA_KEYS
        if unsupported:
            raise CheckError(f"{label}: unsupported profile keywords: {', '.join(sorted(unsupported))}")
        if "$schema" in item and item["$schema"] != "https://json-schema.org/draft/2020-12/schema":
            raise CheckError(f"{label}: only JSON Schema 2020-12 is supported")
        stack.extend(item.get("properties", {}).values())
        for key in ("items", "additionalProperties"):
            if key in item:
                stack.append(item[key])


def validate_instance(instance, schema, label):
    try:
        Draft202012Validator(schema).validate(instance)
    except ValidationError as exc:
        path = "/" + "/".join(str(p) for p in exc.absolute_path)
        raise CheckError(f"{label}{path} failed {exc.validator}") from exc


def validate_manifest(manifest, input_payload, *, allow_loopback=False):
    # Apply identical bounds to Python callers, browser submissions and CLI files.
    manifest = read_json(canonical(manifest))
    read_json(canonical(input_payload))
    if not isinstance(manifest, dict) or not isinstance(input_payload, dict):
        raise CheckError("manifest and input must be JSON objects")
    identifiers = {
        "product_id": r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}",
        "capability_id": r"[A-Za-z0-9][A-Za-z0-9._-]{0,180}@[vV]\d{1,8}",
        "publisher_id": r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}",
    }
    for key, pattern in identifiers.items():
        if not isinstance(manifest.get(key), str) or not re.fullmatch(pattern, manifest[key]):
            raise CheckError(f"{key} is missing or malformed")
    if manifest["publisher_id"].startswith(("tx-consumed:", "unverified-dev-credit")):
        raise CheckError("publisher_id uses a reserved prefix")
    if not isinstance(manifest.get("name"), str) or not 1 <= len(manifest["name"].strip()) <= 128:
        raise CheckError("name must contain 1-128 characters")
    price = manifest.get("price_per_call_usd")
    if isinstance(price, bool) or not isinstance(price, (int, float)) or not 0 <= price <= 1000:
        raise CheckError("price_per_call_usd must be a number between 0 and 1000")
    parse_target(manifest.get("invoke_url"), allow_loopback=allow_loopback)
    try:
        key = base64.b64decode(manifest.get("provider_pubkey", ""), validate=True)
        if len(key) != 32 or base64.b64encode(key).decode() != manifest["provider_pubkey"]:
            raise ValueError()
    except (ValueError, TypeError, binascii.Error) as exc:
        raise CheckError("provider_pubkey must be canonical base64 for 32 Ed25519 bytes") from exc
    for label in ("input_schema", "output_schema"):
        validate_schema(manifest.get(label), label)
    validate_instance(input_payload, manifest["input_schema"], "input")


def envelope(manifest, input_payload, result):
    return {"capability_id": manifest["capability_id"], "product_id": manifest["product_id"],
            "input_sha256": digest(input_payload), "result": result}


def verify_signature(manifest, signed_envelope, signature):
    try:
        key = Ed25519PublicKey.from_public_bytes(base64.b64decode(manifest["provider_pubkey"], validate=True))
        key.verify(base64.b64decode(signature, validate=True), canonical(signed_envelope))
    except (ValueError, TypeError, InvalidSignature, binascii.Error) as exc:
        raise CheckError("X-Provider-Signature does not verify against the manifest key and request-bound envelope") from exc


async def check_provider(manifest, input_payload, *, allow_loopback=False, requester=request_json):
    report = {
        "report_version": 1, "profile": PROFILE, "status": "failed",
        "checked_at": datetime.now(timezone.utc).isoformat(), "checks": [],
        "scope": "One direct provider invoke; no Hub registration or payment",
        "not_tested": ["hub_receipt", "discovery", "federation", "payments", "replay_detection", "load", "whole_protocol_conformance"],
    }
    step = "manifest"
    try:
        validate_manifest(manifest, input_payload, allow_loopback=allow_loopback)
        report.update(manifest_sha256=digest(manifest), input_sha256=digest(input_payload),
                      endpoint=manifest["invoke_url"], capability_id=manifest["capability_id"])
        report["checks"].append({"id": step, "status": "passed"})
        step = "invoke"
        body, signature = await requester(
            "POST", manifest["invoke_url"], payload={"product_id": manifest["product_id"],
            "capability_id": manifest["capability_id"], "input": input_payload}, allow_loopback=allow_loopback
        )
        response = read_json(body)
        if not isinstance(response, dict) or response.get("success") is not True or not isinstance(response.get("result"), dict):
            raise CheckError("invoke must return success: true and a result object")
        report["checks"].append({"id": step, "status": "passed"})
        step = "output_schema"
        validate_instance(response["result"], manifest["output_schema"], "result")
        report["checks"].append({"id": step, "status": "passed"})
        step = "provider_signature"
        signed = envelope(manifest, input_payload, response["result"])
        verify_signature(manifest, signed, signature)
        report["checks"].append({"id": step, "status": "passed"})
        report["evidence"] = {"envelope": signed, "signature": signature, "provider_pubkey": manifest["provider_pubkey"]}
        report["status"] = "passed"
    except CheckError as exc:
        report["checks"].append({"id": step, "status": "failed", "detail": str(exc)})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check the AIMarket provider invoke profile (one real call, no payment).")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--input", type=Path, required=True, help="JSON input file; use a harmless test fixture")
    parser.add_argument("--allow-loopback", action="store_true", help="CLI only: permit local development endpoints")
    args = parser.parse_args(argv)
    try:
        with args.manifest.open("rb") as handle:
            manifest = read_json(handle.read(MAX_DOCUMENT + 1))
        with args.input.open("rb") as handle:
            payload = read_json(handle.read(MAX_DOCUMENT + 1))
        report = asyncio.run(asyncio.wait_for(check_provider(manifest, payload, allow_loopback=args.allow_loopback), 20))
    except (OSError, CheckError, TimeoutError) as exc:
        print(json.dumps({"profile": PROFILE, "status": "failed", "error": str(exc) or "check timed out"}), file=sys.stdout)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
