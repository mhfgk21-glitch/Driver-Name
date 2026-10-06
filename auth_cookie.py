import base64
import binascii
import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping


def _signing_key(password_hash: str) -> bytes:
    return hashlib.sha256(
        b"driver-name-auth-cookie-v1\0" + password_hash.encode("utf-8")
    ).digest()


def create_auth_cookie(
    username: str,
    password_hash: str,
    issued_at: int,
    max_age: int,
) -> tuple[str, int]:
    expires_at = issued_at + max_age
    payload = {
        "v": 1,
        "u": username,
        "i": issued_at,
        "e": expires_at,
        "n": secrets.token_urlsafe(16),
    }
    encoded_payload = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = hmac.new(
        _signing_key(password_hash),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return f"{encoded_payload}.{signature}", expires_at


def verify_auth_cookie(
    token: str,
    accounts: Mapping[str, Mapping[str, str]],
    now: int,
    max_age: int,
) -> tuple[str, int] | None:
    if not isinstance(token, str) or len(token) > 2048:
        return None
    try:
        encoded_payload, supplied_signature = token.split(".", 1)
        padded_payload = encoded_payload + "=" * (-len(encoded_payload) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded_payload))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None
    username = payload.get("u")
    issued_at = payload.get("i")
    expires_at = payload.get("e")
    nonce = payload.get("n")
    if (
        type(payload.get("v")) is not int
        or payload["v"] != 1
        or not isinstance(username, str)
        or type(issued_at) is not int
        or type(expires_at) is not int
        or not isinstance(nonce, str)
        or len(nonce) < 16
        or expires_at <= now
        or issued_at > now + 60
        or expires_at - issued_at > max_age
        or expires_at <= issued_at
    ):
        return None

    account = accounts.get(username)
    if account is None:
        return None
    password_hash = account.get("password")
    if not isinstance(password_hash, str) or not password_hash.startswith("pbkdf2_sha256$"):
        return None

    expected_signature = hmac.new(
        _signing_key(password_hash),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        return None
    return username, expires_at
