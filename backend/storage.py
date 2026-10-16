from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from .database import json_dumps, json_loads, session_expiry, utc_now


MAX_AUDIT_JSON_CHARS = 20_000
AUDIT_PREVIEW_CHARS = 2_000


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


class Storage:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        return row_to_dict(
            self.conn.execute(
                "SELECT id, username, display_name, role FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        )

    def get_user_by_session(self, session_id: str | None) -> dict[str, Any] | None:
        if not session_id:
            return None
        return row_to_dict(
            self.conn.execute(
                """
                SELECT u.id, u.username, u.display_name, u.role
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.id = ?
                  AND s.revoked_at IS NULL
                  AND s.expires_at > ?
                """,
                (session_id, utc_now()),
            ).fetchone()
        )

    def create_session(self, user_id: int) -> str:
        session_id = uuid.uuid4().hex
        self.conn.execute(
            """
            INSERT INTO sessions (id, user_id, created_at, expires_at, revoked_at)
            VALUES (?, ?, ?, ?, NULL)
            """,
            (session_id, user_id, utc_now(), session_expiry()),
        )
        self.conn.commit()
        return session_id

    def revoke_session(self, session_id: str | None) -> None:
        if not session_id:
            return
        self.conn.execute(
            "UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (utc_now(), session_id),
        )
        self.conn.commit()

    def list_actions(self) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT key, label, category, risk_level, enabled, requires_approval,
                   allowed_roles_json, connector_method
            FROM actions
            ORDER BY category, risk_level, label
            """
        ).fetchall()
        return [self._format_action(row) for row in rows]

    def get_action(self, action_key: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT key, label, category, risk_level, enabled, requires_approval,
                   allowed_roles_json, connector_method
            FROM actions
            WHERE key = ?
            """,
            (action_key,),
        ).fetchone()
        return self._format_action(row) if row else None

    def update_action(self, action_key: str, changes: dict[str, Any]) -> dict[str, Any]:
        allowed = {"enabled", "requires_approval", "allowed_roles"}
        unknown = set(changes) - allowed
        if unknown:
            raise ValueError(f"Unsupported permission fields: {', '.join(sorted(unknown))}")

        action = self.get_action(action_key)
        if not action:
            raise ValueError(f"Unknown action '{action_key}'.")

        enabled = int(bool(changes.get("enabled", action["enabled"])))
        requires_approval = int(bool(changes.get("requires_approval", action["requires_approval"])))
        allowed_roles = changes.get("allowed_roles", action["allowed_roles"])
        if not isinstance(allowed_roles, list) or not all(isinstance(role, str) for role in allowed_roles):
            raise ValueError("allowed_roles must be a list of role names.")

        self.conn.execute(
            """
            UPDATE actions
            SET enabled = ?, requires_approval = ?, allowed_roles_json = ?
            WHERE key = ?
            """,
            (enabled, requires_approval, json_dumps(allowed_roles), action_key),
        )
        self.conn.commit()
        return self.get_action(action_key) or action

    def list_matrix_api_endpoints(self, matrix_enabled: bool | None = None) -> list[dict[str, Any]]:
        params: tuple[Any, ...] = ()
        where = ""
        if matrix_enabled is not None:
            where = "WHERE matrix_enabled = ?"
            params = (int(matrix_enabled),)

        rows = self.conn.execute(
            f"""
            SELECT *
            FROM matrix_api_endpoints
            {where}
            ORDER BY matrix_enabled DESC, service_group, path, method
            """,
            params,
        ).fetchall()
        return [self._format_matrix_api_endpoint(row) for row in rows]

    def get_matrix_api_endpoint(self, method: str, path: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT *
            FROM matrix_api_endpoints
            WHERE method = ? AND path = ?
            """,
            (method.upper(), path),
        ).fetchone()
        return self._format_matrix_api_endpoint(row) if row else None

    def is_matrix_api_endpoint_enabled(self, method: str, path: str) -> bool:
        endpoint = self.get_matrix_api_endpoint(method, path)
        return bool(endpoint and endpoint["matrix_enabled"])

    def sync_matrix_api_endpoints(self, endpoints: list[dict[str, Any]]) -> dict[str, int]:
        synced_at = utc_now()
        created = 0
        updated = 0
        for endpoint in endpoints:
            existing = self.get_matrix_api_endpoint(endpoint["method"], endpoint["path"])
            if existing:
                updated += 1
            else:
                created += 1

            self.conn.execute(
                """
                INSERT INTO matrix_api_endpoints (
                    method, path, summary, service_group, query_params_json,
                    header_params_json, auth_required, source, local_action_keys_json,
                    matrix_enabled, created_at, updated_at, last_synced_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                ON CONFLICT(method, path) DO UPDATE SET
                    summary = excluded.summary,
                    service_group = excluded.service_group,
                    query_params_json = excluded.query_params_json,
                    header_params_json = excluded.header_params_json,
                    auth_required = excluded.auth_required,
                    source = excluded.source,
                    local_action_keys_json = excluded.local_action_keys_json,
                    updated_at = excluded.updated_at,
                    last_synced_at = excluded.last_synced_at
                """,
                (
                    endpoint["method"].upper(),
                    endpoint["path"],
                    endpoint.get("summary") or "",
                    endpoint.get("service_group") or "Other",
                    json_dumps(endpoint.get("query_params", [])),
                    json_dumps(endpoint.get("header_params", [])),
                    int(bool(endpoint.get("auth_required"))),
                    endpoint.get("source") or "unknown",
                    json_dumps(endpoint.get("local_action_keys", [])),
                    synced_at,
                    synced_at,
                    synced_at,
                ),
            )

        self.conn.commit()
        return {"created": created, "updated": updated, "total": len(endpoints)}

    def update_matrix_api_endpoint_status(self, method: str, path: str, matrix_enabled: bool) -> dict[str, Any]:
        endpoint = self.get_matrix_api_endpoint(method, path)
        if not endpoint:
            raise ValueError(f"Matrix API endpoint {method.upper()} {path} was not found.")

        self.conn.execute(
            """
            UPDATE matrix_api_endpoints
            SET matrix_enabled = ?, updated_at = ?
            WHERE method = ? AND path = ?
            """,
            (int(matrix_enabled), utc_now(), method.upper(), path),
        )
        self.conn.commit()
        return self.get_matrix_api_endpoint(method, path) or endpoint

    def create_audit_event(
        self,
        actor_user_id: int | None,
        action_key: str,
        event_type: str,
        outcome: str,
        request: dict[str, Any],
        response: dict[str, Any],
    ) -> int:
        safe_request = _safe_audit_payload(request)
        safe_response = _safe_audit_payload(response)
        cursor = self.conn.execute(
            """
            INSERT INTO audit_events (
                timestamp, actor_user_id, action_key, event_type, outcome,
                request_json, response_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                utc_now(),
                actor_user_id,
                action_key,
                event_type,
                outcome,
                json_dumps(safe_request),
                json_dumps(safe_response),
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def create_workflow_run(
        self,
        workflow_type: str,
        title: str,
        created_by: int,
        input_payload: dict[str, Any],
        findings: list[dict[str, Any]],
        ai_summary: dict[str, Any],
    ) -> int:
        cursor = self.conn.execute(
            """
            INSERT INTO workflow_runs (
                workflow_type, title, status, created_by, created_at,
                input_json, findings_json, ai_summary_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workflow_type,
                title,
                "analyzed",
                created_by,
                utc_now(),
                json_dumps(input_payload),
                json_dumps(findings),
                json_dumps(ai_summary),
            ),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def create_proposed_action(
        self,
        workflow_run_id: int,
        action_key: str,
        status: str,
        payload_preview: str,
        payload: dict[str, Any],
        created_by: int,
        blocked_reason: str | None = None,
    ) -> dict[str, Any]:
        cursor = self.conn.execute(
            """
            INSERT INTO proposed_actions (
                workflow_run_id, action_key, status, payload_preview, payload_json,
                created_by, approved_by, executed_at, blocked_reason, decision_note, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, ?)
            """,
            (
                workflow_run_id,
                action_key,
                status,
                payload_preview,
                json_dumps(payload),
                created_by,
                blocked_reason,
                utc_now(),
            ),
        )
        self.conn.commit()
        return self.get_proposed_action(int(cursor.lastrowid)) or {}

    def get_proposed_action(self, proposed_action_id: int) -> dict[str, Any] | None:
        row = self.conn.execute(
            """
            SELECT pa.*, a.label, a.category, a.risk_level, a.enabled,
                   a.requires_approval, a.allowed_roles_json
            FROM proposed_actions pa
            JOIN actions a ON a.key = pa.action_key
            WHERE pa.id = ?
            """,
            (proposed_action_id,),
        ).fetchone()
        return self._format_proposed_action(row) if row else None

    def list_proposed_actions(self, workflow_run_id: int | None = None) -> list[dict[str, Any]]:
        params: tuple[Any, ...] = ()
        where = ""
        if workflow_run_id is not None:
            where = "WHERE pa.workflow_run_id = ?"
            params = (workflow_run_id,)

        rows = self.conn.execute(
            f"""
            SELECT pa.*, a.label, a.category, a.risk_level, a.enabled,
                   a.requires_approval, a.allowed_roles_json
            FROM proposed_actions pa
            JOIN actions a ON a.key = pa.action_key
            {where}
            ORDER BY pa.id
            """,
            params,
        ).fetchall()
        return [self._format_proposed_action(row) for row in rows]

    def update_proposed_action(
        self,
        proposed_action_id: int,
        status: str,
        approved_by: int | None = None,
        executed_at: str | None = None,
        blocked_reason: str | None = None,
        decision_note: str | None = None,
    ) -> dict[str, Any]:
        self.conn.execute(
            """
            UPDATE proposed_actions
            SET status = ?,
                approved_by = COALESCE(?, approved_by),
                executed_at = COALESCE(?, executed_at),
                blocked_reason = ?,
                decision_note = ?
            WHERE id = ?
            """,
            (status, approved_by, executed_at, blocked_reason, decision_note, proposed_action_id),
        )
        self.conn.commit()
        return self.get_proposed_action(proposed_action_id) or {}

    def list_workflow_runs(self, limit: int = 25) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT wr.*, u.username, u.display_name, u.role
            FROM workflow_runs wr
            JOIN users u ON u.id = wr.created_by
            ORDER BY wr.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        workflows = []
        for row in rows:
            workflow = dict(row)
            workflow["input"] = json_loads(workflow.pop("input_json"), {})
            workflow["findings"] = json_loads(workflow.pop("findings_json"), [])
            workflow["ai_summary"] = json_loads(workflow.pop("ai_summary_json"), {})
            workflow["created_by_user"] = {
                "id": workflow.pop("created_by"),
                "username": workflow.pop("username"),
                "display_name": workflow.pop("display_name"),
                "role": workflow.pop("role"),
            }
            workflow["proposed_actions"] = self.list_proposed_actions(workflow["id"])
            workflows.append(workflow)
        return workflows

    def list_audit_events(self, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT ae.id, ae.timestamp, ae.actor_user_id, ae.action_key,
                   ae.event_type, ae.outcome,
                   length(ae.request_json) AS request_size,
                   length(ae.response_json) AS response_size,
                   substr(ae.request_json, 1, ?) AS request_preview,
                   substr(ae.response_json, 1, ?) AS response_preview,
                   u.username, u.display_name, u.role
            FROM audit_events ae
            LEFT JOIN users u ON u.id = ae.actor_user_id
            ORDER BY ae.id DESC
            LIMIT ?
            """,
            (AUDIT_PREVIEW_CHARS, AUDIT_PREVIEW_CHARS, limit),
        ).fetchall()
        events = []
        for row in rows:
            event = dict(row)
            request_size = int(event.pop("request_size") or 0)
            response_size = int(event.pop("response_size") or 0)
            event["request"] = _preview_audit_json(event.pop("request_preview"), request_size)
            event["response"] = _preview_audit_json(event.pop("response_preview"), response_size)
            event["actor"] = None
            if event.get("username"):
                event["actor"] = {
                    "id": event["actor_user_id"],
                    "username": event.pop("username"),
                    "display_name": event.pop("display_name"),
                    "role": event.pop("role"),
                }
            else:
                event.pop("username", None)
                event.pop("display_name", None)
                event.pop("role", None)
            events.append(event)
        return events

    def get_part(self, part_number: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM mock_parts WHERE upper(part_number) = upper(?)",
            (part_number,),
        ).fetchone()
        return self._format_part(row) if row else None

    def search_parts(self, query: str) -> list[dict[str, Any]]:
        like = f"%{query.strip()}%"
        rows = self.conn.execute(
            """
            SELECT * FROM mock_parts
            WHERE upper(part_number) LIKE upper(?)
               OR upper(name) LIKE upper(?)
            ORDER BY part_number
            """,
            (like, like),
        ).fetchall()
        return [self._format_part(row) for row in rows]

    def find_part_duplicates(self, part_number: str, name: str, classification: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT * FROM mock_parts
            WHERE upper(part_number) = upper(?)
               OR (upper(name) = upper(?) AND upper(classification) = upper(?))
               OR upper(name) LIKE upper(?)
            ORDER BY
                CASE WHEN upper(part_number) = upper(?) THEN 0 ELSE 1 END,
                part_number
            """,
            (part_number, name, classification, f"%{name.strip()}%", part_number),
        ).fetchall()
        return [self._format_part(row) for row in rows]

    def open_ecos_for_parts(self, part_numbers: list[str]) -> list[dict[str, Any]]:
        if not part_numbers:
            return []
        rows = self.conn.execute(
            "SELECT * FROM mock_ecos WHERE status NOT IN ('Released', 'Cancelled')"
        ).fetchall()
        wanted = {part.upper() for part in part_numbers}
        matches = []
        for row in rows:
            eco = dict(row)
            affected = json_loads(eco.pop("affected_parts_json"), [])
            if wanted.intersection({part.upper() for part in affected}):
                eco["affected_parts"] = affected
                matches.append(eco)
        return matches

    def where_used(self, part_numbers: list[str]) -> list[dict[str, Any]]:
        if not part_numbers:
            return []
        placeholders = ",".join("?" for _ in part_numbers)
        rows = self.conn.execute(
            f"""
            SELECT mb.parent_part, mb.child_part, mb.quantity, mp.name AS parent_name,
                   mp.lifecycle_state AS parent_lifecycle_state
            FROM mock_bom mb
            JOIN mock_parts mp ON mp.part_number = mb.parent_part
            WHERE upper(mb.child_part) IN ({placeholders})
            ORDER BY mb.parent_part, mb.child_part
            """,
            tuple(part.upper() for part in part_numbers),
        ).fetchall()
        return [dict(row) for row in rows]

    def _format_action(self, row: sqlite3.Row) -> dict[str, Any]:
        action = dict(row)
        action["enabled"] = bool(action["enabled"])
        action["requires_approval"] = bool(action["requires_approval"])
        action["allowed_roles"] = json_loads(action.pop("allowed_roles_json"), [])
        return action

    def _format_proposed_action(self, row: sqlite3.Row) -> dict[str, Any]:
        action = dict(row)
        action["enabled"] = bool(action["enabled"])
        action["requires_approval"] = bool(action["requires_approval"])
        action["allowed_roles"] = json_loads(action.pop("allowed_roles_json"), [])
        action["payload"] = json_loads(action.pop("payload_json"), {})
        return action

    def _format_part(self, row: sqlite3.Row) -> dict[str, Any]:
        part = dict(row)
        part["attributes"] = json_loads(part.pop("attributes_json"), {})
        return part

    def _format_matrix_api_endpoint(self, row: sqlite3.Row) -> dict[str, Any]:
        endpoint = dict(row)
        endpoint["auth_required"] = bool(endpoint["auth_required"])
        endpoint["matrix_enabled"] = bool(endpoint["matrix_enabled"])
        endpoint["query_params"] = json_loads(endpoint.pop("query_params_json"), [])
        endpoint["header_params"] = json_loads(endpoint.pop("header_params_json"), [])
        endpoint["local_action_keys"] = json_loads(endpoint.pop("local_action_keys_json"), [])
        return endpoint


def _safe_audit_payload(value: Any) -> Any:
    raw = json_dumps(value)
    if len(raw) <= MAX_AUDIT_JSON_CHARS:
        return value
    return {
        "audit_truncated": True,
        "original_size": len(raw),
        "preview": raw[:AUDIT_PREVIEW_CHARS],
    }


def _preview_audit_json(preview: str | None, full_size: int) -> dict[str, Any]:
    text = preview or ""
    if full_size <= AUDIT_PREVIEW_CHARS:
        return json_loads(text, {})
    return {
        "audit_truncated": True,
        "original_size": full_size,
        "preview": text,
    }
