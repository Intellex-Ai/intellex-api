from typing import TypedDict, Any, Optional

from fastapi import Header, HTTPException

from app.supabase_client import get_supabase


class AuthContext(TypedDict):
    id: str
    email: Optional[str]
    deviceId: Optional[str]


def _extract_token(authorization: str | None) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authorization header must be Bearer token")

    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing access token")
    return token


def _get_attr(obj: Any, key: str) -> Any:
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


def require_supabase_user(
    authorization: str | None = Header(default=None),
    device_id: str | None = Header(default=None, alias="x-device-id"),
    skip_revoked_check: bool = False,
) -> AuthContext:
    client = get_supabase()
    if not client:
        raise HTTPException(status_code=503, detail="Supabase is not configured")

    token = _extract_token(authorization)

    def fetch_user():
        return client.auth.get_user(token)

    try:
        result = fetch_user()
    except Exception:
        # Retry once with a fresh client in case the underlying connection was closed.
        get_supabase.cache_clear()  # type: ignore[attr-defined]
        refreshed = get_supabase()
        if not refreshed:
            raise HTTPException(status_code=503, detail="Authentication service unavailable. Please retry.")
        try:
            result = refreshed.auth.get_user(token)
        except Exception as exc:  # pragma: no cover - runtime guard
            raise HTTPException(status_code=503, detail="Authentication service unavailable. Please retry.") from exc

    error = _get_attr(result, "error")
    if error:
        detail = _get_attr(error, "message") or str(error)
        raise HTTPException(status_code=401, detail=f"Invalid or expired access token: {detail}")

    user = _get_attr(result, "user")
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired access token")

    user_id = _get_attr(user, "id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Auth token missing user id")

    email = _get_attr(user, "email")

    if device_id and not skip_revoked_check:
        try:
            res = (
                client.table("user_devices")
                .select("id, revoked_at")
                .eq("user_id", user_id)
                .eq("device_id", device_id)
                .limit(1)
                .execute()
            )
            if res.data:
                revoked_at = res.data[0].get("revoked_at")
                if revoked_at:
                    raise HTTPException(status_code=403, detail="This device has been signed out. Please sign in again.")
        except HTTPException:
            raise
        except Exception:
            # Non-blocking guard; auth proceeds if the device table is unavailable.
            pass

    return {"id": str(user_id), "email": email if email is None else str(email), "deviceId": device_id}


def require_supabase_user_allow_revoked(
    authorization: str | None = Header(default=None),
    device_id: str | None = Header(default=None, alias="x-device-id"),
) -> AuthContext:
    """
    Dependency variant that allows revoked devices to call device-management endpoints
    so they can clear revocation and refresh tokens.
    """
    return require_supabase_user(authorization=authorization, device_id=device_id, skip_revoked_check=True)
