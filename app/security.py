"""
Security helpers shared across blueprints.

Values here are HMAC-hashed (not plain SHA-256) using the app's SECRET_KEY
as the key -- important for phone numbers and OTPs specifically, since both
have small enough keyspaces that an unkeyed hash could be brute-forced back
to the original value. Keying it with a secret the attacker doesn't have
closes that.
"""

import hmac
import hashlib

from flask import current_app


def hash_value(value: str) -> str:
    key = current_app.config["SECRET_KEY"].encode("utf-8")
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()


def hash_phone(phone_number: str) -> str:
    return hash_value(phone_number)


def mask_phone(phone_number: str) -> str:
    if not phone_number or len(phone_number) < 4:
        return "unbound"
    return f"...{phone_number[-4:]}"
