from __future__ import annotations

from typing import Any

from .database import utc_now
from .permissions import PermissionService
from .storage import Storage


class ApprovalService:
    def __init__(self, storage: Storage, permissions: PermissionService):
        self.storage = storage
        self.permissions = permissions

    def approve(self, proposed_action_id: int, user: dict[str, Any], note: str | None = None) -> dict[str, Any]:
        proposed = self.storage.get_proposed_action(proposed_action_id)
        if not proposed:
            raise ValueError(f"Proposed action {proposed_action_id} was not found.")

        if proposed["status"] not in {"approval_required", "ready"}:
            raise ValueError(f"Proposed action {proposed_action_id} is {proposed['status']} and cannot be approved.")

        allowed, reason, _action = self.permissions.can_use_action(proposed["action_key"], user["role"])
        if not allowed:
            raise PermissionError(reason or "Action is not allowed.")

        return self.storage.update_proposed_action(
            proposed_action_id,
            "executed",
            approved_by=int(user["id"]),
            executed_at=utc_now(),
            blocked_reason=None,
            decision_note=note or "Approved and mock-executed.",
        )

    def reject(self, proposed_action_id: int, user: dict[str, Any], note: str | None = None) -> dict[str, Any]:
        proposed = self.storage.get_proposed_action(proposed_action_id)
        if not proposed:
            raise ValueError(f"Proposed action {proposed_action_id} was not found.")
        if proposed["status"] in {"executed", "rejected"}:
            raise ValueError(f"Proposed action {proposed_action_id} is already {proposed['status']}.")
        return self.storage.update_proposed_action(
            proposed_action_id,
            "rejected",
            approved_by=int(user["id"]),
            executed_at=None,
            blocked_reason=proposed.get("blocked_reason"),
            decision_note=note or "Rejected by approver.",
        )

    def approve_all_eligible(
        self,
        workflow_run_id: int,
        user: dict[str, Any],
        note: str | None = None,
    ) -> dict[str, Any]:
        approved: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for proposed in self.storage.list_proposed_actions(workflow_run_id):
            if proposed["status"] not in {"approval_required", "ready"}:
                skipped.append({"id": proposed["id"], "reason": f"status is {proposed['status']}"})
                continue

            allowed, reason, _action = self.permissions.can_use_action(proposed["action_key"], user["role"])
            if not allowed:
                skipped.append({"id": proposed["id"], "reason": reason or "not allowed"})
                continue

            approved.append(
                self.storage.update_proposed_action(
                    int(proposed["id"]),
                    "executed",
                    approved_by=int(user["id"]),
                    executed_at=utc_now(),
                    blocked_reason=None,
                    decision_note=note or "Approved by approve-all and mock-executed.",
                )
            )

        return {"approved": approved, "skipped": skipped}

