from __future__ import annotations

from pathlib import Path
from typing import Any

from .api_catalog import MatrixApiCatalogService
from .ai import MockAIAdapter
from .approvals import ApprovalService
from .database import initialize
from .matrix_config import connection_status
from .matrix_connector import MatrixConnectorError, create_matrix_connector
from .permissions import PermissionService
from .part_number_families import PartNumberFamilyCatalog
from .part_number_planner import PartNumberPlanner
from .sap_connector import SapConnectorError, create_sap_connector
from .storage import Storage
from .workflows import WorkflowService


class AppError(Exception):
    pass


class ValidationError(AppError):
    pass


class AuthorizationError(AppError):
    pass


class MatrixAIApplication:
    def __init__(self, db_path: str | Path | None = None):
        self.conn = initialize(db_path)
        self.storage = Storage(self.conn)
        self.permissions = PermissionService(self.storage)
        self.api_catalog = MatrixApiCatalogService(self.storage)
        self.matrix = create_matrix_connector(self.storage)
        self.sap = create_sap_connector()
        self.ai = MockAIAdapter()
        self.workflows = WorkflowService(self.storage, self.permissions, self.matrix, self.ai)
        self.part_number_planner = PartNumberPlanner(
            self.storage,
            self.permissions,
            self.matrix,
            self.sap,
            PartNumberFamilyCatalog(),
        )
        self.approvals = ApprovalService(self.storage, self.permissions)

    def close(self) -> None:
        self.conn.close()

    def handle(self, envelope: dict[str, Any]) -> dict[str, Any]:
        action_key = "unknown"
        user: dict[str, Any] | None = None
        response: dict[str, Any]
        try:
            if not isinstance(envelope, dict):
                raise ValidationError("Request must be a JSON object.")
            action_key = _required_string(envelope, "action")
            payload = envelope.get("payload") or {}
            if not isinstance(payload, dict):
                raise ValidationError("payload must be a JSON object.")

            session_id = envelope.get("session_id")
            if isinstance(session_id, str):
                user = self.storage.get_user_by_session(session_id)

            data = self._dispatch(action_key, payload, user, session_id if isinstance(session_id, str) else None)
            response = {"ok": True, "data": data, "errors": []}
        except (ValidationError, AuthorizationError, ValueError, PermissionError) as exc:
            response = {"ok": False, "data": None, "errors": [str(exc)]}
        except Exception as exc:
            response = {"ok": False, "data": None, "errors": [f"Unexpected error: {exc}"]}

        audit_id = self.storage.create_audit_event(
            int(user["id"]) if user else None,
            action_key,
            "api_request",
            "ok" if response["ok"] else "error",
            envelope if isinstance(envelope, dict) else {"invalid_request": repr(envelope)},
            response,
        )
        response["audit_id"] = audit_id
        return response

    def _dispatch(
        self,
        action_key: str,
        payload: dict[str, Any],
        user: dict[str, Any] | None,
        session_id: str | None,
    ) -> dict[str, Any]:
        if action_key == "auth.login":
            username = _required_string(payload, "username").lower()
            login_user = self.storage.get_user_by_username(username)
            if not login_user:
                raise AuthorizationError("Unknown mock user.")
            new_session_id = self.storage.create_session(int(login_user["id"]))
            return {"session_id": new_session_id, "user": login_user}

        if action_key == "auth.logout":
            self.storage.revoke_session(session_id)
            return {"logged_out": True}

        if action_key == "auth.me":
            return {"user": self._require_user(user)}

        user = self._require_user(user)

        if action_key == "permissions.list":
            return {"actions": self.storage.list_actions()}

        if action_key == "permissions.update":
            self._require_role(user, {"Admin"})
            updated = self.storage.update_action(
                _required_string(payload, "action_key"),
                _dict_subset(payload, {"enabled", "requires_approval", "allowed_roles"}),
            )
            return {"action": updated}

        if action_key == "matrix.api.catalog.list":
            self._require_role(user, {"Admin"})
            enabled_filter = payload.get("matrix_enabled")
            if enabled_filter is not None and not isinstance(enabled_filter, bool):
                raise ValidationError("matrix_enabled must be true, false, or omitted.")
            return {"endpoints": self.api_catalog.list_endpoints(enabled_filter)}

        if action_key == "matrix.api.catalog.sync":
            self._require_role(user, {"Admin"})
            return self.api_catalog.sync_from_default_spec()

        if action_key == "matrix.api.catalog.update_status":
            self._require_role(user, {"Admin"})
            endpoint = self.api_catalog.update_status(
                _required_string(payload, "method"),
                _required_string(payload, "path"),
                _required_bool(payload, "matrix_enabled"),
            )
            return {"endpoint": endpoint}

        if action_key == "matrix.connection.status":
            self._require_role(user, {"Admin"})
            return connection_status(self.storage)

        if action_key == "matrix.part.search":
            return self._search_parts(payload, user)

        if action_key == "sap.material.search":
            return self._search_sap_materials(payload, user)

        if action_key == "workflow.part_number.plan":
            self._require_role(user, {"Engineer", "Admin"})
            return self.part_number_planner.plan(payload, user)

        if action_key == "workflow.eco.analyze":
            self._require_role(user, {"Engineer", "Admin"})
            return self.workflows.analyze_eco(payload, user)

        if action_key == "workflow.part.analyze":
            self._require_role(user, {"Engineer", "Admin"})
            return self.workflows.analyze_part(payload, user)

        if action_key == "approval.action.approve":
            self._require_role(user, {"Approver", "Admin"})
            approved = self.approvals.approve(int(payload.get("proposed_action_id")), user, payload.get("note"))
            return {"proposed_action": approved}

        if action_key == "approval.action.reject":
            self._require_role(user, {"Approver", "Admin"})
            rejected = self.approvals.reject(int(payload.get("proposed_action_id")), user, payload.get("note"))
            return {"proposed_action": rejected}

        if action_key == "approval.actions.approve_all_eligible":
            self._require_role(user, {"Approver", "Admin"})
            return self.approvals.approve_all_eligible(
                int(payload.get("workflow_run_id")),
                user,
                payload.get("note"),
            )

        if action_key == "audit.workflow.history":
            self._require_role(user, {"Engineer", "Admin", "Approver"})
            limit = int(payload.get("limit", 25))
            return {
                "workflows": self.storage.list_workflow_runs(limit=limit),
                "audit_events": self.storage.list_audit_events(limit=min(limit * 2, 100)),
            }

        raise ValidationError(f"Unknown action '{action_key}'.")

    def _search_parts(self, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        allowed, reason, _action = self.permissions.can_use_action("matrix.part.search", user["role"])
        if not allowed:
            raise AuthorizationError(reason or "Search parts is disabled by policy.")

        query = _part_search_query(payload)
        use_matrix_server = _optional_bool(payload, "use_matrix_server")
        matrix = create_matrix_connector(self.storage, mode="rest-read") if use_matrix_server else self.matrix
        try:
            matches = matrix.search_parts(query)
        except MatrixConnectorError as exc:
            raise ValidationError(f"{exc.code}: {exc.message}") from exc
        return {
            "query": query,
            "source": "matrix" if use_matrix_server else "mock",
            "count": len(matches),
            "matches": matches,
        }

    def _search_sap_materials(self, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        allowed, reason, _action = self.permissions.can_use_action("sap.material.search", user["role"])
        if not allowed:
            raise AuthorizationError(reason or "Search SAP materials is disabled by policy.")
        query = _part_search_query(payload)
        try:
            matches = self.sap.search_materials(query)
        except SapConnectorError as exc:
            raise ValidationError(f"{exc.code}: {exc.message}") from exc
        return {
            "query": query,
            "source": "sap",
            "source_status": self.sap.status(),
            "count": len(matches),
            "matches": matches,
        }

    def _require_user(self, user: dict[str, Any] | None) -> dict[str, Any]:
        if not user:
            raise AuthorizationError("A valid session_id is required.")
        return user

    def _require_role(self, user: dict[str, Any], allowed_roles: set[str]) -> None:
        if user["role"] not in allowed_roles:
            raise AuthorizationError(
                f"Role {user['role']} cannot perform this action. Required: {', '.join(sorted(allowed_roles))}."
            )


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{key} is required.")
    return value.strip()


def _required_bool(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValidationError(f"{key} must be a boolean.")
    return value


def _part_search_query(payload: dict[str, Any]) -> str:
    value = payload.get("query")
    if value is None:
        value = payload.get("part_number")
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("query or part_number is required.")
    return value.strip()


def _optional_bool(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key, False)
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    raise ValidationError(f"{key} must be a boolean.")


def _dict_subset(payload: dict[str, Any], keys: set[str]) -> dict[str, Any]:
    return {key: payload[key] for key in keys if key in payload}
