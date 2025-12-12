import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette import status

from app.models import User, LoginRequest, DeleteAccountRequest
from app.storage import DataStore, get_store
from app.supabase_client import get_supabase, fetch_auth_metadata
from app.deps.auth import AuthContext, require_supabase_user

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)

@router.post("/login", response_model=User)
def login(
    payload: LoginRequest,
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
):
    try:
        name = payload.name
        # Seed name from auth metadata if not provided.
        supabase_user_id = auth_user["id"]
        authed_email = (auth_user.get("email") or "").lower()

        if payload.email and authed_email and payload.email.lower() != authed_email:
            raise HTTPException(status_code=403, detail="Email does not match authenticated user")

        if not name and supabase_user_id:
            meta = fetch_auth_metadata(supabase_user_id) or {}
            name = (
                meta.get("display_name")
                or meta.get("full_name")
                or meta.get("name")
            )
        email = (payload.email or authed_email or "").strip()
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")

        return store.get_or_create_user(email, name, supabase_user_id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Auth storage error", exc_info=exc)
        raise HTTPException(status_code=500, detail="Auth storage error")

@router.get("/me", response_model=User)
def current_user(
    store: DataStore = Depends(get_store),
    email: str | None = Query(None, description="Email to fetch a specific user"),
    userId: str | None = Query(None, description="Supabase auth/user id to fetch a specific user"),
    auth_user: AuthContext = Depends(require_supabase_user),
):
    if userId and userId != auth_user["id"]:
        raise HTTPException(status_code=403, detail="Cannot fetch a different user than the authenticated session")
    if email and auth_user.get("email") and email.lower() != auth_user["email"].lower():
        raise HTTPException(status_code=403, detail="Cannot fetch a different user than the authenticated session")

    target_id = userId or auth_user["id"]
    target_email = email or auth_user.get("email")

    user = None
    if target_id:
        user = store.find_user(target_id)
    if not user and target_email:
        user = store.find_user(target_email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.delete("/account", status_code=status.HTTP_200_OK)
def delete_account(
    payload: DeleteAccountRequest,
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
):
    if payload.userId and payload.userId != auth_user["id"]:
        raise HTTPException(status_code=403, detail="Cannot delete a different user than the authenticated session")
    if payload.email and auth_user.get("email") and payload.email.lower() != auth_user["email"].lower():
        raise HTTPException(status_code=403, detail="Cannot delete a different user than the authenticated session")

    target = payload.userId or payload.email
    user = store.find_user(target or auth_user["id"])

    profile_deleted = False
    if user:
        profile_deleted = store.delete_user(user.id, user.email)

    auth_deleted = False
    auth_error = None
    supabase_user_id = auth_user["id"]

    if supabase_user_id:
        client = get_supabase()
        if client:
            try:
                admin = getattr(client.auth, "admin", None)
                if admin and hasattr(admin, "delete_user"):
                    result = admin.delete_user(supabase_user_id)
                    if getattr(result, "error", None):
                        auth_error = str(result.error)
                    else:
                        auth_deleted = True
                else:
                    auth_error = "Supabase admin client unavailable"
            except Exception as exc:  # pragma: no cover - runtime guard
                auth_error = str(exc)

    if auth_error:
        # Surface auth deletion errors but do not roll back app deletion.
        logger.warning("Supabase auth deletion failed", extra={"error": auth_error})
        raise HTTPException(
            status_code=502,
            detail="Auth deletion failed after profile deletion. Please contact support.",
        )

    return {
        "deleted": True,
        "profileDeleted": profile_deleted,
        "authDeleted": auth_deleted,
    }
