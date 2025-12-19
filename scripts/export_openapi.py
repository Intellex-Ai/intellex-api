import json
import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.main import app


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    spec_path = repo_root / "intellex-shared" / "schemas" / "openapi" / "intellex-api.openapi.json"
    spec_path.parent.mkdir(parents=True, exist_ok=True)

    spec = app.openapi()
    with spec_path.open("w", encoding="utf-8") as handle:
        json.dump(spec, handle, indent=2, sort_keys=True)
        handle.write("\n")


if __name__ == "__main__":
    main()
