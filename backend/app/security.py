from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def verify_operator_credentials(operator_id: str, password: str, configured_id: str, configured_password: str) -> bool:
    if not configured_id or not configured_password:
        return False
    id_ok = hmac.compare_digest(operator_id.encode("utf-8"), configured_id.encode("utf-8"))
    password_ok = hmac.compare_digest(password.encode("utf-8"), configured_password.encode("utf-8"))
    return id_ok and password_ok


def create_operator_token(operator_id: str, secret: str, ttl_seconds: int = 28_800, now: int | None = None) -> str:
    if not secret:
        raise ValueError("Operator token secret is not configured")
    issued = int(time.time() if now is None else now)
    payload = {"sub": operator_id, "iat": issued, "exp": issued + ttl_seconds, "scope": "operator"}
    encoded = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64(hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def verify_operator_token(token: str, secret: str, now: int | None = None) -> dict[str, Any] | None:
    if not secret or not token or "." not in token:
        return None
    try:
        encoded, supplied_signature = token.split(".", 1)
        expected = _b64(hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(supplied_signature, expected):
            return None
        payload = json.loads(_unb64(encoded))
        current = int(time.time() if now is None else now)
        if payload.get("scope") != "operator" or not payload.get("sub") or int(payload.get("exp", 0)) <= current:
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return None
