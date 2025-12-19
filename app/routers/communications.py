import os

from fastapi import APIRouter, Depends, Header, HTTPException

from app.models import CommunicationEventIn, CommunicationMessageIn
from app.storage import DataStore, get_store

router = APIRouter(prefix="/communications", tags=["communications"])

COMMUNICATIONS_API_SECRET = os.getenv("COMMUNICATIONS_API_SECRET")


def require_communications_secret(secret: str | None) -> None:
    if not COMMUNICATIONS_API_SECRET:
        raise HTTPException(status_code=503, detail="COMMUNICATIONS_API_SECRET not configured")
    if secret != COMMUNICATIONS_API_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing communications secret")


@router.post("/messages", status_code=204)
def record_message(
    payload: CommunicationMessageIn,
    store: DataStore = Depends(get_store),
    x_communications_secret: str | None = Header(None, alias="x-communications-secret"),
):
    require_communications_secret(x_communications_secret)
    store.record_communication_message(payload)
    return None


@router.post("/events", status_code=204)
def record_event(
    payload: CommunicationEventIn,
    store: DataStore = Depends(get_store),
    x_communications_secret: str | None = Header(None, alias="x-communications-secret"),
):
    require_communications_secret(x_communications_secret)
    store.record_communication_event(payload)
    return None
