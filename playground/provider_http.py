"""Bounded, DNS-pinned HTTP for developer-controlled provider endpoints."""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit

import httpx

MAX_RESPONSE = 65_536


class CheckError(ValueError):
    pass


def parse_target(raw: str, *, allow_loopback: bool = False):
    if not isinstance(raw, str) or len(raw) > 2048 or any(ord(c) < 33 for c in raw):
        raise CheckError("invoke_url must be an absolute HTTPS URL without whitespace")
    try:
        url = urlsplit(raw)
        port = url.port
    except ValueError as exc:
        raise CheckError("invoke_url has an invalid host or port") from exc
    if not url.hostname or url.username is not None or url.password is not None or url.query or url.fragment:
        raise CheckError("invoke_url must have a host and no credentials, query or fragment")
    if "%" in url.netloc or "\\" in raw:
        raise CheckError("invoke_url contains an unsupported host")
    if not url.netloc.isascii():
        raise CheckError("invoke_url host must use ASCII / punycode")
    local = url.hostname == "localhost"
    try:
        local = local or ipaddress.ip_address(url.hostname).is_loopback
    except ValueError:
        pass
    if not (allow_loopback and local):
        if url.scheme != "https" or port not in (None, 443):
            raise CheckError("public endpoints require HTTPS on port 443")
    elif url.scheme not in {"http", "https"}:
        raise CheckError("local endpoints require HTTP or HTTPS")
    return url


def public_address(address: str) -> bool:
    addr = ipaddress.ip_address(address)
    if not addr.is_global or addr.is_multicast or addr.is_reserved:
        return False
    if addr.version == 6:
        # Reject transition mechanisms rather than allowing embedded private IPv4.
        if addr.ipv4_mapped or addr.sixtofour or addr.teredo:
            return False
        if addr in ipaddress.ip_network("64:ff9b::/96") or addr in ipaddress.ip_network("64:ff9b:1::/48"):
            return False
    return True


async def pin_target(raw: str, *, allow_loopback: bool = False):
    url = parse_target(raw, allow_loopback=allow_loopback)
    port = url.port or (443 if url.scheme == "https" else 80)
    try:
        infos = await asyncio.wait_for(
            asyncio.get_running_loop().getaddrinfo(url.hostname, port, type=socket.SOCK_STREAM), 3
        )
        addresses = [row[4][0] for row in infos]
        if not addresses:
            raise CheckError("endpoint DNS returned no addresses")
        for address in addresses:
            addr = ipaddress.ip_address(address)
            if not public_address(address) and not (allow_loopback and addr.is_loopback):
                raise CheckError("endpoint DNS must resolve only to public addresses")
    except (socket.gaierror, UnicodeError, TimeoutError) as exc:
        raise CheckError("endpoint DNS could not be resolved") from exc
    host = addresses[0]
    netloc = f"[{host}]" if ":" in host else host
    if url.port:
        netloc += f":{port}"
    target = urlunsplit(url._replace(netloc=netloc))
    return target, {"Host": url.netloc}, {"sni_hostname": url.hostname}


async def request_json(method: str, url: str, *, payload=None, allow_loopback=False, pinned=None):
    target, pin_headers, extensions = pinned or await pin_target(url, allow_loopback=allow_loopback)
    headers = dict(pin_headers)
    headers.update({"Accept": "application/json", "Accept-Encoding": "identity",
                    "User-Agent": "AIMarket-Provider-Check/1", "X-AIMarket-Test-Mode": "provider-invoke-v1"})
    try:
        async with httpx.AsyncClient(timeout=8, trust_env=False, follow_redirects=False) as client:
            async with client.stream(method, target, headers=headers, extensions=extensions, json=payload) as response:
                if response.status_code != 200:
                    raise CheckError(f"endpoint returned HTTP {response.status_code}; expected 200 (redirects are not followed)")
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise CheckError("endpoint must return uncompressed JSON")
                if response.headers.get("content-type", "").split(";")[0].strip() != "application/json":
                    raise CheckError("endpoint must return Content-Type: application/json")
                body = bytearray()
                async for chunk in response.aiter_raw(chunk_size=8192):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE:
                        raise CheckError("endpoint response exceeds 65536 bytes")
                return bytes(body), response.headers.get("X-Provider-Signature", "")
    except httpx.TimeoutException as exc:
        raise CheckError("endpoint timed out; the invoke is never retried automatically") from exc
    except httpx.HTTPError as exc:
        raise CheckError("endpoint connection or TLS verification failed") from exc
