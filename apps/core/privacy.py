"""Phone number handling: normalise, HMAC for lookup, encrypt for sending."""

from __future__ import annotations

import hashlib
import hmac
import re

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class InvalidPhoneNumber(ValueError):
    pass


_DIGITS = re.compile(r"\D+")


def normalize_ng_phone(raw: str) -> str:
    """Return a Nigerian number in E.164 (+234XXXXXXXXXX) or raise."""
    digits = _DIGITS.sub("", raw or "")
    if digits.startswith("234") and len(digits) == 13:
        national = digits[3:]
    elif digits.startswith("0") and len(digits) == 11:
        national = digits[1:]
    elif len(digits) == 10 and digits[0] in "789":
        national = digits
    else:
        raise InvalidPhoneNumber("Enter a Nigerian phone number, like 0803 123 4567.")
    if national[0] not in "789":
        raise InvalidPhoneNumber("Enter a Nigerian mobile number, like 0803 123 4567.")
    return f"+234{national}"


def phone_hmac(e164: str) -> str:
    key = settings.PHONE_HMAC_KEY.encode()
    return hmac.new(key, e164.encode(), hashlib.sha256).hexdigest()


def _fernet() -> Fernet:
    return Fernet(settings.FIELD_ENCRYPTION_KEY.encode())


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - defensive
        raise ValueError("Could not decrypt value") from exc


def mask_phone(e164: str) -> str:
    return f"{e164[:7]}***{e164[-2:]}" if len(e164) > 9 else "***"
