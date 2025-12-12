import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables for local dev (.env.local) and Vercel prod (.env.production).
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env.local")
if os.getenv("VERCEL_ENV", "").lower() == "production":
    load_dotenv(BASE_DIR / ".env.production")
load_dotenv(BASE_DIR / ".env")

from app.routers import auth, projects, users, devices, orchestrator
from app.storage import get_storage_mode, validate_supabase_schema
from app.supabase_client import check_supabase_health, get_supabase
from app.utils.time import now_ms

APP_VERSION = "0.2.0"
logger = logging.getLogger(__name__)

def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _runtime_env() -> str:
    return (os.getenv("ENV") or os.getenv("VERCEL_ENV") or "").strip().lower()


app = FastAPI(
    title="Intellex API",
    description="Backend for Intellex Research SaaS",
    version=APP_VERSION,
)

# Configure CORS
runtime_env = _runtime_env()
is_dev = runtime_env in {"", "dev", "development", "local"}
allow_any_origin = _truthy(os.getenv("FRONTEND_ALLOW_ANY_ORIGIN"))

frontend_origins_raw = os.getenv("FRONTEND_ORIGINS")
if not frontend_origins_raw and is_dev and not allow_any_origin:
    frontend_origins_raw = "http://localhost:3100,http://localhost:3001"

frontend_origin_regex = (os.getenv("FRONTEND_ORIGIN_REGEX") or "").strip() or None
allow_origins = [origin.strip() for origin in (frontend_origins_raw or "").split(",") if origin.strip()]

if runtime_env == "production" and allow_any_origin:
    logger.warning("FRONTEND_ALLOW_ANY_ORIGIN is enabled in production; this is insecure.")
if runtime_env == "production" and not allow_any_origin and not allow_origins and not frontend_origin_regex:
    logger.warning(
        "No FRONTEND_ORIGINS/FRONTEND_ORIGIN_REGEX configured; cross-origin browser requests will be blocked."
    )

cors_kwargs = {
    "allow_methods": ["*"],
    "allow_headers": ["*"],
}
if allow_any_origin:
    cors_kwargs.update(
        {
            "allow_origins": ["*"],
            "allow_origin_regex": None,
            # Wildcard origins with credentials is insecure and rejected by browsers.
            "allow_credentials": False,
        }
    )
else:
    cors_kwargs.update(
        {
            "allow_origins": allow_origins,
            "allow_origin_regex": frontend_origin_regex,
            "allow_credentials": True,
        }
    )

app.add_middleware(CORSMiddleware, **cors_kwargs)

app.include_router(auth.router)
app.include_router(projects.router)
app.include_router(users.router)
app.include_router(devices.router)
app.include_router(orchestrator.router)

@app.on_event("startup")
async def prewarm_supabase():
    """
    Fail fast (or warn) on missing Supabase configuration and prime the schema check
    so the first request doesn't pay the latency penalty.
    """
    storage_mode = get_storage_mode()
    if not storage_mode.startswith("supabase"):
        return

    client = get_supabase()
    if not client:
        logger.warning("Supabase env vars not configured; API storage will return 503 until set.")
        return

    try:
        validate_supabase_schema(client)
    except Exception as exc:  # pragma: no cover - best-effort guard
        logger.error("Supabase schema validation failed on startup", exc_info=exc)

@app.get("/")
async def root():
    return {
        "message": "Intellex API is online",
        "status": "system_ready",
        "version": APP_VERSION,
    }

@app.get("/health")
async def health_check():
    storage_mode = get_storage_mode()
    supabase = check_supabase_health()
    return {
        "status": "ok",
        "timestamp": now_ms(),
        "storage": storage_mode,
        "db": {"status": "skipped", "reason": "Supabase storage enforced"},
        "supabase": supabase,
    }

@app.get("/health/db")
async def db_health():
    return {"status": "skipped", "reason": "Supabase storage enforced"}

@app.get("/health/supabase")
async def supabase_health():
    return check_supabase_health()
