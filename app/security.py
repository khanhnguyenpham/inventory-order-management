from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

PBKDF2_ITERATIONS = 240_000


def _encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        actual_salt,
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${_encode(actual_salt)}${_encode(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored_hash.split("$", maxsplit=3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _decode(salt),
            int(iterations),
        )
        return hmac.compare_digest(_encode(digest), expected)
    except (ValueError, TypeError):
        return False


def create_token(subject: str, role: str, secret: str, ttl_minutes: int) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": subject, "role": role, "iat": now, "exp": now + ttl_minutes * 60}
    signing_input = ".".join(
        [
            _encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
            _encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
        ]
    )
    signature = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_encode(signature)}"


def decode_token(token: str, secret: str) -> dict[str, Any]:
    try:
        header, payload, signature = token.split(".", maxsplit=2)
        header_data = json.loads(_decode(header))
        if header_data.get("alg") != "HS256" or header_data.get("typ") != "JWT":
            raise ValueError("Header token không hợp lệ")
        signing_input = f"{header}.{payload}"
        expected = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _decode(signature)):
            raise ValueError("Chữ ký token không hợp lệ")
        data = json.loads(_decode(payload))
        if int(data["exp"]) <= int(time.time()):
            raise ValueError("Token đã hết hạn")
        if not data.get("sub") or data.get("role") not in {"manager", "staff"}:
            raise ValueError("Nội dung token không hợp lệ")
        return data
    except (KeyError, ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Token không hợp lệ") from error
