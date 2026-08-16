"""Băm mật khẩu cho tài khoản demo.

Dùng PBKDF2-HMAC-SHA256 của thư viện chuẩn để không phải thêm phụ thuộc.
Đủ cho hệ thống demo với tài khoản do BTC cấp; nếu sau này có người dùng thật
thì chuyển sang bcrypt/argon2.
"""

from __future__ import annotations

import hashlib
import hmac
import os

_ITERATIONS = 200_000
_ALGO = "pbkdf2_sha256"


def hash_password(password: str) -> str:
    """Trả về chuỗi ``pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>``."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGO}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    """So khớp mật khẩu với chuỗi đã băm, dùng so sánh chống timing attack."""
    try:
        algo, iterations, salt_hex, digest_hex = encoded.split("$")
    except ValueError:
        return False
    if algo != _ALGO:
        return False

    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
    return hmac.compare_digest(digest.hex(), digest_hex)
