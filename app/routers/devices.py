from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.deps.auth import AuthContext, require_supabase_user
from app.models import DeviceListResponse, DeviceRecord, DeviceRevokeRequest, DeviceUpsertRequest
from app.storage import DataStore, get_store

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/devices", response_model=DeviceListResponse)
def list_devices(
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
):
    devices = store.list_devices(auth_user["id"])
    return {"devices": devices}


@router.post("/devices", response_model=DeviceRecord)
def upsert_device(
    payload: DeviceUpsertRequest,
    request: Request,
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
    device_header: str | None = Header(default=None, alias="x-device-id"),
):
    device_id = payload.deviceId or device_header
    if not device_id:
        raise HTTPException(status_code=400, detail="deviceId is required")

    normalized = payload.model_copy(update={"deviceId": device_id})
    request_ip = request.client.host if request.client else None
    return store.upsert_device(auth_user["id"], normalized, request_ip)


@router.post("/devices/revoke")
def revoke_devices(
    payload: DeviceRevokeRequest,
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
    device_header: str | None = Header(default=None, alias="x-device-id"),
):
    device_id = payload.deviceId or device_header
    if payload.scope in ("single", "others") and not device_id:
        raise HTTPException(status_code=400, detail="deviceId is required for this scope")

    revoked = store.revoke_devices(auth_user["id"], payload.scope, device_id)
    return {"revoked": revoked}
