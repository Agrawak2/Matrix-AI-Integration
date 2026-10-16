from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.matrix_config import connection_status
from backend.matrix_connector import EXECUTE_MQL_PATH
from backend.service import handle
from backend.storage import Storage
from backend.database import initialize


def main() -> int:
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

    conn = initialize()
    try:
        status = connection_status(Storage(conn))
    finally:
        conn.close()

    print("Matrix REST read preparation:")
    print(f"  executeMQL endpoint enabled: {status['execute_mql_matrix_enabled']}")
    print(f"  profile configured: {status['profile_configured']}")
    print(f"  templates configured: {status['templates_configured']}")
    print(f"  live reads ready: {status['ready_for_rest_read']}")
    if status.get("profile_name"):
        print(f"  profile: {status['profile_name']}")
    if status.get("template_names"):
        print(f"  templates: {', '.join(status['template_names'])}")
    if status.get("profile_error"):
        print(f"  profile error: {status['profile_error']}")
    if status.get("template_error"):
        print(f"  template error: {status['template_error']}")
    return 0 if status["ready_for_rest_read"] else 1


def _fail(label: str, response: dict[str, object]) -> int:
    print(label)
    print(json.dumps(response, indent=2))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
