import os
import uuid
from typing import Any, Optional

import httpx


COMMUNICATIONS_BASE_URL = os.getenv("COMMUNICATIONS_BASE_URL")
COMMUNICATIONS_SEND_PATH = os.getenv("COMMUNICATIONS_SEND_PATH", "/send")


def send_email(
    to: str,
    template: str,
    data: dict[str, Any],
    subject: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    callback_url: Optional[str] = None,
) -> None:
    """
    Best-effort send through intellex-communications.
    No-op if COMMUNICATIONS_BASE_URL isn't configured.
    """
    if not COMMUNICATIONS_BASE_URL:
        return

    payload = {
        "id": f"send-{uuid.uuid4().hex[:8]}",
        "channel": "email",
        "template": template,
        "to": to,
        "subject": subject,
        "data": data,
        "metadata": metadata,
        "callbackUrl": callback_url,
    }

    try:
        url = f"{COMMUNICATIONS_BASE_URL.rstrip('/')}{COMMUNICATIONS_SEND_PATH}"
        with httpx.Client(timeout=10) as client:
            client.post(url, json=payload)
    except Exception as exc:  # pragma: no cover - best-effort
        print(f"Communications send failed: {exc}")

