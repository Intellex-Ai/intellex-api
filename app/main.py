import os
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import check_db_health, init_db
from app.routers import auth, projects
from app.storage import get_storage_mode
from app.supabase_client import check_supabase_health

APP_VERSION = "0.2.0"

def now_ms() -> int:
    return int(time.time() * 1000)

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

@app.on_event("startup")
def on_startup():
    if get_storage_mode() == "sqlite":
        init_db()

@app.get("/")
async def root():
    return {
        "message": "Intellex API is online",
        "status": "system_ready",
        "version": APP_VERSION,
    }

@app.get("/health")
async def health_check():
    supabase = check_supabase_health()
    return {
        "status": "ok",
        "timestamp": now_ms(),
        "storage": get_storage_mode(),
        "db": check_db_health() if get_storage_mode() == "sqlite" else {"status": "skipped", "reason": "Using Supabase storage"},
        "supabase": supabase,
    }

@app.get("/health/db")
async def db_health():
    if get_storage_mode() != "sqlite":
        return {"status": "skipped", "reason": "Using Supabase storage"}
    return check_db_health()

@app.get("/health/supabase")
async def supabase_health():
    return check_supabase_health()
