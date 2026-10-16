from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.matrix_connector import EXECUTE_MQL_PATH
from backend.service import handle


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a read-only Matrix REST part search.")
    parser.add_argument("--query", default="PCB", help="Part-number fragment or Matrix wildcard pattern.")
    parser.add_argument("--username", default="engineer", help="Mock app user used for authorization.")
    args = parser.parse_args()

    prepare_result = _prepare_catalog()
    if prepare_result:
        return prepare_result

    login = handle({"action": "auth.login", "payload": {"username": args.username}})
    if not login.get("ok"):
        return _fail("Login failed", login)

    search = handle(
        {
            "action": "matrix.part.search",
            "session_id": login["data"]["session_id"],
            "payload": {
                "query": args.query,
                "use_matrix_server": True,
            },
        }
    )
    if not search.get("ok"):
        return _fail("Matrix part search failed", search)

    data = search["data"]
    matches = data.get("matches", [])
    print(f"Matrix part search returned {data.get('count')} match(es) for {data.get('query')!r}.")
    for part in matches:
        print(
            "  {part_number:<18} {revision:<5} {lifecycle_state:<14} {name}".format(
                part_number=str(part.get("part_number", "")),
                revision=str(part.get("revision", "")),
                lifecycle_state=str(part.get("lifecycle_state", "")),
                name=str(part.get("name", "")),
            )
        )
    print("Matches JSON:")
    print(json.dumps(matches, indent=2))
    return 0


def _prepare_catalog() -> int:
    admin_login = handle({"action": "auth.login", "payload": {"username": "admin"}})
    if not admin_login.get("ok"):
        return _fail("Admin login failed", admin_login)

    admin_session = admin_login["data"]["session_id"]
    sync = handle({"action": "matrix.api.catalog.sync", "session_id": admin_session, "payload": {}})
    if not sync.get("ok"):
        return _fail("API catalog sync failed", sync)

    enable = handle(
        {
            "action": "matrix.api.catalog.update_status",
            "session_id": admin_session,
            "payload": {
                "method": "GET",
                "path": EXECUTE_MQL_PATH,
                "matrix_enabled": True,
            },
        }
    )
    if not enable.get("ok"):
        return _fail("executeMQL enable failed", enable)
    return 0


def _fail(label: str, response: dict[str, object]) -> int:
    print(label)
    errors = response.get("errors")
    if errors:
        print("; ".join(str(error) for error in errors))
    else:
        print(json.dumps(response, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
