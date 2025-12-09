from fastapi import APIRouter, Depends

from app.deps.auth import AuthContext, require_supabase_user
from app.models import ApiKeyPayload, ApiKeysResponse
from app.storage import DataStore, get_store

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/api-keys", response_model=ApiKeysResponse)
def get_api_keys(
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
):
    return store.get_api_keys(auth_user["id"])


@router.post("/api-keys", response_model=ApiKeysResponse)
def save_api_keys(
    payload: ApiKeyPayload,
    auth_user: AuthContext = Depends(require_supabase_user),
    store: DataStore = Depends(get_store),
):
    return store.save_api_keys(auth_user["id"], payload)
