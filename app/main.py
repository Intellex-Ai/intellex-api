import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, projects
from app.storage import get_storage_mode
from app.supabase_client import check_supabase_health
from app.utils.time import now_ms

APP_VERSION = "0.2.0"

app = FastAPI(
    title="Intellex API",
    description="Backend for Intellex Research SaaS",
    version=APP_VERSION,
)

# Configure CORS
frontend_origins = os.getenv(
    "FRONTEND_ORIGINS",
    "http://localhost:3100,http://localhost:3001,https://intellex-web.vercel.app",
).split(",")
frontend_origin_regex = os.getenv("FRONTEND_ORIGIN_REGEX", r"https://.*\.vercel\.app")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in frontend_origins if origin.strip()],
    allow_origin_regex=frontend_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(projects.router)

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
