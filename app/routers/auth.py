from fastapi import APIRouter, Depends, HTTPException, Query

from app.models import User, LoginRequest
from app.storage import DataStore, get_store

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=User)
def login(payload: LoginRequest, store: DataStore = Depends(get_store)):
    return store.get_or_create_user(payload.email, payload.name)

@router.get("/me", response_model=User)
def current_user(
    store: DataStore = Depends(get_store),
    email: str | None = Query(None, description="Optional email to fetch a specific user"),
):
    user = None
    if email:
        user = store.find_user(email)
    if not user:
        user = store.get_first_user()
    if not user:
        raise HTTPException(status_code=404, detail="No users found")
    return user
