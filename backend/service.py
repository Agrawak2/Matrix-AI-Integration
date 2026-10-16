from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app import MatrixAIApplication


def handle(envelope: dict[str, Any], db_path: str | Path | None = None) -> dict[str, Any]:
    app = MatrixAIApplication(db_path=db_path)
    try:
        return app.handle(envelope)
    finally:
        app.close()


def main() -> int:
    raw_input = sys.stdin.read()
    try:
        envelope = json.loads(raw_input or "{}")
    except json.JSONDecodeError as exc:
        envelope = {"action": "unknown", "payload": {"error": f"Invalid JSON: {exc}"}}

    response = handle(envelope)
    print(json.dumps(response, ensure_ascii=False))
    return 0 if response.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
