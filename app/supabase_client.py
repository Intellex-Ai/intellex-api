import os
from functools import lru_cache

try:
    from supabase import Client, create_client
except ImportError:  # pragma: no cover - optional dependency in some environments
    Client = None  # type: ignore
    create_client = None  # type: ignore

REQUIRED_TABLES = ("users", "projects", "research_plans", "messages", "user_devices")

def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    sanitized = value.strip().strip('"').strip("'")
    return sanitized or None


@lru_cache(maxsize=1)
def get_supabase() -> "Client | None":
    """
    Return a cached Supabase client when env vars are configured.
    Leading/trailing quotes/newlines are stripped to avoid misconfiguration.
    """
    if not create_client:
        return None

    url = _clean(os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL"))
    key = _clean(os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY"))
    if not url or not key:
        return None

    try:
        return create_client(url, key)
    except Exception:
        return None


def check_supabase_health() -> dict:
    # Clear cache to avoid sticky None when envs are injected after a cold start.
    get_supabase.cache_clear()  # type: ignore[attr-defined]
    url = _clean(os.getenv("SUPABASE_URL") or os.getenv("NEXT_PUBLIC_SUPABASE_URL"))
    key = _clean(os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY") or os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY"))
    missing = [name for name, val in [("SUPABASE_URL", url), ("SUPABASE_SERVICE_ROLE_KEY/ANON_KEY", key)] if not val]

    client = get_supabase()
    if not client:
        return {
            "status": "not_configured",
            "missing": missing,
            "hasUrl": bool(url),
            "hasKey": bool(key),
        }

    table_counts = {}
    errors: list[str] = []

    for table in REQUIRED_TABLES:
        try:
            response = client.table(table).select("id").limit(1).execute()
            if getattr(response, "error", None):
                errors.append(f"{table}: {response.error}")
            elif hasattr(response, "data"):
                table_counts[table] = len(response.data or [])
            else:
                errors.append(f"{table}: missing data in response")
        except Exception as exc:  # pragma: no cover - runtime guard
            errors.append(f"{table}: {exc}")

    status = "ok" if not errors else "error"
    payload: dict = {"status": status, "tables": table_counts}
    if errors:
        payload["errors"] = errors
    return payload


def fetch_auth_metadata(auth_user_id: str) -> dict:
    """
    Best-effort fetch of auth user metadata using the service role client.
    """
    client = get_supabase()
    if not client or not auth_user_id:
        return {}
    try:
        admin = getattr(client.auth, "admin", None)
        if admin and hasattr(admin, "get_user_by_id"):
            res = admin.get_user_by_id(auth_user_id)
            user = getattr(res, "user", None) or {}
            metadata = getattr(user, "user_metadata", None)
            return metadata or {}
    except Exception:
        return {}
    return {}
