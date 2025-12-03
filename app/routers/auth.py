from fastapi import APIRouter, Depends, HTTPException, Query
from starlette import status

from app.models import User, LoginRequest, DeleteAccountRequest
from app.storage import DataStore, get_store
from app.supabase_client import get_supabase

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=User)
def login(payload: LoginRequest, store: DataStore = Depends(get_store)):
    try:
        return store.get_or_create_user(payload.email, payload.name, payload.supabaseUserId)
    except Exception as exc:
        # Surface a clearer 500 for easier debugging in prod
        raise HTTPException(status_code=500, detail=f"Auth storage error: {exc}")

@router.get("/me", response_model=User)
def current_user(
    store: DataStore = Depends(get_store),
    email: str | None = Query(None, description="Email to fetch a specific user"),
    userId: str | None = Query(None, description="Supabase auth/user id to fetch a specific user"),
):
    if not email and not userId:
        raise HTTPException(status_code=400, detail="userId or email is required")

    user = None
    if userId:
        user = store.find_user(userId)
    if not user and email:
        user = store.find_user(email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.delete("/account", status_code=status.HTTP_200_OK)
def delete_account(payload: DeleteAccountRequest, store: DataStore = Depends(get_store)):
    if not payload.userId and not payload.email:
        raise HTTPException(status_code=400, detail="userId or email is required")

    target = payload.userId or payload.email
    user = store.find_user(target) if target else None

    profile_deleted = False
    if user:
        profile_deleted = store.delete_user(user.id, user.email)

    auth_deleted = False
    auth_error = None
    supabase_user_id = payload.supabaseUserId or (user.id if user else None)

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
        raise HTTPException(
            status_code=502,
            detail=f"Profile deletion: {profile_deleted}. Auth deletion failed: {auth_error}",
        )

    return {
        "deleted": True,
        "profileDeleted": profile_deleted,
        "authDeleted": auth_deleted,
    }
