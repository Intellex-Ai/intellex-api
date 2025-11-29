import os
from functools import lru_cache

try:
    from supabase import Client, create_client
except ImportError:  # pragma: no cover - optional dependency in some environments
    Client = None  # type: ignore
    create_client = None  # type: ignore


@lru_cache(maxsize=1)
def get_supabase() -> "Client | None":
    """
    Return a cached Supabase client when env vars are configured.
    """
    if not create_client:
        return None

    url = os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    if not url or not key:
        return None

    try:
        return create_client(url, key)
    except Exception:
        return None


def check_supabase_health() -> dict:
    client = get_supabase()
    if not client:
        return {"status": "not_configured"}

    try:
        response = client.table("users").select("id").limit(1).execute()
        sample_count = len(response.data or []) if hasattr(response, "data") else 0
        return {"status": "ok", "sampleCount": sample_count, "table": "users"}
    except Exception as exc:  # pragma: no cover - runtime guard
        return {"status": "error", "error": str(exc)}
