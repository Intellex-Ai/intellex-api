import logging
import os
import uuid
from typing import Any, Optional

import httpx


COMMUNICATIONS_BASE_URL = os.getenv("COMMUNICATIONS_BASE_URL")
COMMUNICATIONS_SEND_PATH = os.getenv("COMMUNICATIONS_SEND_PATH", "/send")
COMMUNICATIONS_API_SECRET = os.getenv("COMMUNICATIONS_API_SECRET")
logger = logging.getLogger(__name__)


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
    No-op if COMMUNICATIONS_BASE_URL or COMMUNICATIONS_API_SECRET isn't configured.
    """
    if not COMMUNICATIONS_BASE_URL:
        return
    if not COMMUNICATIONS_API_SECRET:
        logger.warning("COMMUNICATIONS_API_SECRET not set, skipping send")
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

    headers = {"x-communications-secret": COMMUNICATIONS_API_SECRET}

    try:
        url = f"{COMMUNICATIONS_BASE_URL.rstrip('/')}{COMMUNICATIONS_SEND_PATH}"
        with httpx.Client(timeout=10) as client:
            client.post(url, json=payload, headers=headers)
    except Exception as exc:  # pragma: no cover - best-effort
        logger.warning("Communications send failed", exc_info=exc)

