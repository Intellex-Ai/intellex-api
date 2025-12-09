import base64
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException


def get_cipher() -> Fernet:
    key = os.getenv("API_KEY_ENCRYPTION_KEY")
    if not key:
        raise HTTPException(status_code=503, detail="API key encryption key is missing (set API_KEY_ENCRYPTION_KEY)")

    try:
        # Allow raw 32-byte keys or urlsafe base64-encoded keys.
        raw = key.encode()
        if len(raw) == 32:
            raw = base64.urlsafe_b64encode(raw)
        return Fernet(raw)
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=503, detail=f"Invalid API_KEY_ENCRYPTION_KEY: {exc}")


def encrypt_secret(secret: str) -> str:
    cipher = get_cipher()
    return cipher.encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> Optional[str]:
    cipher = get_cipher()
    try:
        return cipher.decrypt(token.encode()).decode()
    except InvalidToken:
        return None
    except Exception:
        return None
