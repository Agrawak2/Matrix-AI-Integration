from __future__ import annotations

from typing import Any

from .storage import Storage


class PermissionService:
    def __init__(self, storage: Storage):
        self.storage = storage

    def can_use_action(self, action_key: str, role: str) -> tuple[bool, str | None, dict[str, Any] | None]:
        action = self.storage.get_action(action_key)
        if not action:
            return False, f"Action '{action_key}' is not registered.", None
        if not action["enabled"]:
            return False, f"{action['label']} is disabled by policy.", action
        if role not in action["allowed_roles"]:
            return False, f"Role {role} is not allowed to use {action['label']}.", action
        return True, None, action

    def proposal_state(
        self,
        action_key: str,
        role: str,
        workflow_blocked_reason: str | None = None,
    ) -> tuple[str, str | None]:
        allowed, reason, action = self.can_use_action(action_key, role)
        if not allowed:
            return "blocked", reason
        if workflow_blocked_reason:
            return "blocked", workflow_blocked_reason
        if action and action["requires_approval"]:
            return "approval_required", None
        return "ready", None

    def require_matrix_read(self, action_key: str, role: str) -> dict[str, Any] | None:
        allowed, reason, action = self.can_use_action(action_key, role)
        if allowed:
            return None
        return {
            "severity": "warning",
            "code": "permission_blocked",
            "message": reason or "Matrix action is blocked.",
            "details": {"action_key": action_key, "action": action},
        }

