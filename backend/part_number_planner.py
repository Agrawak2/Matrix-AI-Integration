from __future__ import annotations

import re
from typing import Any

from .matrix_connector import MatrixConnector, MatrixConnectorError
from .part_number_families import PartNumberFamilyCatalog
from .permissions import PermissionService
from .sap_connector import SapConnectorError, SapMaterialConnector
from .storage import Storage


class PartNumberPlanner:
    def __init__(
        self,
        storage: Storage,
        permissions: PermissionService,
        matrix: MatrixConnector,
        sap: SapMaterialConnector,
        families: PartNumberFamilyCatalog,
    ):
        self.storage = storage
        self.permissions = permissions
        self.matrix = matrix
        self.sap = sap
        self.families = families

    def plan(self, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        prompt = _required_text(payload, "prompt")
        requested_prefix = _text(payload.get("family_prefix"))
        suffix = _text(payload.get("suffix")) or "00"
        if not re.fullmatch(r"\d{2}", suffix):
            raise ValueError("suffix must contain exactly two digits.")

        family, candidates = self.families.identify(prompt, requested_prefix)
        if not family:
            raise ValueError("No unique part-number family matched. Supply a verified three-digit family_prefix.")

        findings: list[dict[str, Any]] = []
        if not family.verified:
            findings.append(
                _finding(
                    "warning",
                    "family_reference_unverified",
                    f"Family {family.prefix} ({family.name}) is provisional until checked against REF0178.",
                    {"source": family.source},
                )
            )

        matrix_parts: list[dict[str, Any]] = []
        matrix_used: set[int] = set()
        search_block = self.permissions.require_matrix_read("matrix.part.search", user["role"])
        if search_block:
            findings.append(search_block)
        else:
            try:
                matrix_parts = self.matrix.search_parts(family.prefix)
                matrix_used = _matrix_used_sequences(matrix_parts, family.prefix)
            except MatrixConnectorError as exc:
                findings.append(_finding("error", exc.code, exc.message, {"source": "Matrix"}))

        sap_used: set[int] = set()
        try:
            sap_used = self.sap.used_sequences(family.prefix)
        except SapConnectorError as exc:
            findings.append(_finding("error", exc.code, exc.message, {"source": "SAP"}))

        first = int(f"{family.prefix}000")
        last = int(f"{family.prefix}999")
        used = matrix_used | sap_used
        available = [sequence for sequence in range(first, last + 1) if sequence not in used]
        if not available:
            findings.append(
                _finding("error", "part_number_family_exhausted", f"No unused sequence remains in family {family.prefix}.", {})
            )

        candidate_part_number = f"{available[0]:06d}{suffix}" if available else ""
        alternatives = [f"{sequence:06d}{suffix}" for sequence in available[1:6]]
        sap_status = self.sap.status()
        if not sap_status.get("live"):
            findings.append(
                _finding(
                    "warning",
                    "sap_revalidation_required",
                    "SAP availability is based on mock or cached data and must be revalidated live before creation.",
                    sap_status,
                )
            )

        description = (_text(payload.get("description")) or _description_from_prompt(prompt)).upper()
        bom_items = _bom_items(payload.get("bom_items"))
        creation_payload = {
            "part_number": candidate_part_number,
            "name": description,
            "description": description,
            "revision": _text(payload.get("revision")) or "EA",
            "part_type": _text(payload.get("part_type")) or "Unfinished Part",
            "policy": _text(payload.get("policy")) or "Development Part",
            "unit_of_measure": _text(payload.get("unit_of_measure")) or "EA",
            "autoname_checked": False,
            "family_prefix": family.prefix,
            "sequence": candidate_part_number[:6],
            "suffix": suffix,
        }

        blocking_reason = None
        if not candidate_part_number:
            blocking_reason = "Resolve blocking availability findings before creating the part."
        elif any(finding["severity"] == "error" for finding in findings):
            blocking_reason = "Resolve blocking source findings before creating the part."
        elif not sap_status.get("live"):
            blocking_reason = "A live SAP revalidation adapter is required before this candidate can be created."

        ai_summary = {
            "provider": "deterministic",
            "summary": (
                f"Matched {family.name} family {family.prefix}; proposed {candidate_part_number or 'no candidate'} "
                f"after checking {len(matrix_used)} Matrix and {len(sap_used)} SAP/legacy sequence(s)."
            ),
            "recommended_next_steps": [
                "Review the family, candidate, attributes, and BOM summary.",
                "Revalidate against live SAP and Matrix immediately before the create transaction.",
            ],
        }
        run_id = self.storage.create_workflow_run(
            "part_number",
            candidate_part_number or f"{family.name} part-number request",
            int(user["id"]),
            {**payload, "family": family.to_dict(), "candidate_part_number": candidate_part_number},
            findings,
            ai_summary,
        )

        proposed_actions = []
        if candidate_part_number:
            proposed_actions.append(
                self._propose(
                    run_id,
                    "matrix.part.create",
                    user,
                    f"Create part {candidate_part_number}: {description}",
                    creation_payload,
                    blocking_reason,
                )
            )
            for item in bom_items:
                proposed_actions.append(
                    self._propose(
                        run_id,
                        "matrix.bom.add_item",
                        user,
                        f"Add {item['child_part']} to BOM for {candidate_part_number}",
                        {"parent_part": candidate_part_number, **item},
                        blocking_reason,
                    )
                )

        return {
            "workflow_run": {
                "id": run_id,
                "workflow_type": "part_number",
                "title": candidate_part_number or f"{family.name} part-number request",
                "status": "planned",
            },
            "ai_summary": ai_summary,
            "findings": findings,
            "part_number_plan": {
                "prompt": prompt,
                "family": family.to_dict(),
                "family_candidates": candidates,
                "candidate_part_number": candidate_part_number,
                "alternative_part_numbers": alternatives,
                "sequence": candidate_part_number[:6] if candidate_part_number else "",
                "suffix": suffix,
                "matrix_sequence_count": len(matrix_used),
                "sap_sequence_count": len(sap_used),
                "combined_sequence_count": len(used),
                "sap_status": sap_status,
                "matrix_matches": matrix_parts[:25],
                "part_attributes": creation_payload,
                "bom_items": bom_items,
            },
            "proposed_actions": proposed_actions,
        }

    def _propose(
        self,
        workflow_run_id: int,
        action_key: str,
        user: dict[str, Any],
        preview: str,
        payload: dict[str, Any],
        workflow_blocked_reason: str | None,
    ) -> dict[str, Any]:
        status, blocked_reason = self.permissions.proposal_state(action_key, user["role"], workflow_blocked_reason)
        return self.storage.create_proposed_action(
            workflow_run_id,
            action_key,
            status,
            preview,
            payload,
            int(user["id"]),
            blocked_reason,
        )


def _matrix_used_sequences(parts: list[dict[str, Any]], family_prefix: str) -> set[int]:
    used = set()
    for part in parts:
        number = str(part.get("part_number", ""))
        if re.fullmatch(r"\d{8}[A-Z0-9]?", number) and number.startswith(family_prefix):
            used.add(int(number[:6]))
    return used


def _bom_items(value: Any) -> list[dict[str, Any]]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError("bom_items must be a list.")
    result = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"BOM item {index} must be an object.")
        child_part = _text(item.get("child_part")).upper()
        if not child_part:
            raise ValueError(f"BOM item {index} requires child_part.")
        quantity = float(item.get("quantity", 1))
        if quantity <= 0:
            raise ValueError(f"BOM item {index} quantity must be positive.")
        result.append(
            {
                "child_part": child_part,
                "quantity": quantity,
                "find_number": _text(item.get("find_number")) or str(index * 10),
            }
        )
    return result


def _description_from_prompt(prompt: str) -> str:
    cleaned = re.sub(r"(?i)^.*?new\s+", "", prompt).strip(" .")
    return cleaned or "NEW PART"


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = _text(payload.get(key))
    if not value:
        raise ValueError(f"{key} is required.")
    return value


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _finding(severity: str, code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"severity": severity, "code": code, "message": message, "details": details}
