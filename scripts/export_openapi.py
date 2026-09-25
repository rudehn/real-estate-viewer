"""Write the API's OpenAPI document (for frontend type generation).

Usage: uv run python scripts/export_openapi.py [OUT]   (default: frontend/openapi.json)
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from main import app  # noqa: E402


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "frontend/openapi.json")
    out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
