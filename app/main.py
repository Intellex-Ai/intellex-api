import os
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import init_db
from app.routers import auth, projects

APP_VERSION = "0.2.0"

def now_ms() -> int:
    return int(time.time() * 1000)

app = FastAPI(
    title="Intellex API",
    description="Backend for Intellex Research SaaS",
    version=APP_VERSION,
)

# Configure CORS
frontend_origins = os.getenv("FRONTEND_ORIGINS", "http://localhost:3100,http://localhost:3001").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in frontend_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(projects.router)

@app.on_event("startup")
def on_startup():
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
    return {"status": "ok", "timestamp": now_ms()}
