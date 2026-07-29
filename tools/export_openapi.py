"""Write the OpenAPI document to a file.

Generated from the application on every run, never hand maintained. The contract
layer validates against the same document this exports, so the published spec
cannot drift from the service without a test noticing.

Usage: python tools/export_openapi.py reports/openapi.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, ".")

from app.main import app  # noqa: E402


def main(destination: str) -> None:
    """Export the spec, creating the directory if it is not there."""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "reports/openapi.json")
