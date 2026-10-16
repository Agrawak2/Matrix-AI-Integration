from __future__ import annotations

import re
from typing import Any

from .ai import MockAIAdapter
from .guideline_validators import validate_eco, validate_part
from .matrix_connector import MatrixConnector, MatrixConnectorError
from .permissions import PermissionService
from .storage import Storage


ALLOWED_CLASSIFICATIONS = {"Assembly", "Electrical", "Mechanical", "Cable", "Document", "Firmware"}


class WorkflowService:
    def __init__(
        self,
        storage: Storage,
        permissions: PermissionService,
        matrix: MatrixConnector,
        ai: MockAIAdapter,
    ):
        self.storage = storage
        self.permissions = permissions
        self.matrix = matrix
        self.ai = ai

    def analyze_eco(self, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        title = _clean(payload.get("title"))
        reason = _clean(payload.get("reason"))
        requested_change = _clean(payload.get("requested_change"))
        affected_parts = _parse_parts(payload.get("affected_parts"))
        findings: list[dict[str, Any]] = []

        for field, value in {
            "title": title,
            "reason": reason,
            "requested_change": requested_change,
        }.items():
            if not value:
                findings.append(_finding("error", "required_field_missing", f"ECO {field} is required.", {"field": field}))

        if not affected_parts:
            findings.append(
                _finding("error", "affected_parts_missing", "At least one affected part is required.", {})
            )
        findings.extend(validate_eco(payload))

        part_read_block = self.permissions.require_matrix_read("matrix.part.read", user["role"])
        eco_search_block = self.permissions.require_matrix_read("matrix.eco.search", user["role"])
        where_used_block = self.permissions.require_matrix_read("matrix.bom.where_used", user["role"])
        findings.extend(block for block in [part_read_block, eco_search_block, where_used_block] if block)

        valid_parts = []
        missing_parts = []
        if not part_read_block:
            try:
                for part_number in affected_parts:
                    part = self.matrix.get_part(part_number)
                    if part:
                        valid_parts.append(part)
                        if part["lifecycle_state"] == "Obsolete":
                            findings.append(
                                _finding(
                                    "error",
                                    "obsolete_affected_part",
                                    f"{part_number} is obsolete and should not be used as an active affected item.",
                                    {"part_number": part_number},
                                )
                            )
                    else:
                        missing_parts.append(part_number)
                        findings.append(
                            _finding(
                                "error",
                                "part_not_found",
                                f"{part_number} was not found in Matrix data.",
                                {"part_number": part_number},
                            )
                        )
            except MatrixConnectorError as exc:
                findings.append(_matrix_finding(exc, "matrix.part.read"))

        open_ecos = []
        if not eco_search_block:
            try:
                open_ecos = self.matrix.open_ecos_for_parts(affected_parts)
            except MatrixConnectorError as exc:
                findings.append(_matrix_finding(exc, "matrix.eco.search"))
        for eco in open_ecos:
            findings.append(
                _finding(
                    "warning",
                    "open_eco_overlap",
                    f"{eco['eco_number']} is already open for one or more affected parts.",
                    {"eco": eco},
                )
            )

        impact = []
        if not where_used_block:
            try:
                impact = self.matrix.where_used(affected_parts)
            except MatrixConnectorError as exc:
                findings.append(_matrix_finding(exc, "matrix.bom.where_used"))
        if impact:
            findings.append(
                _finding(
                    "info",
                    "where_used_impact",
                    f"{len(impact)} where-used relationship(s) may be impacted.",
                    {"relationships": impact},
                )
            )

        if len(valid_parts) != len(affected_parts):
            findings.append(
                _finding(
                    "error",
                    "affected_item_completeness",
                    "Affected item list has missing or invalid part records.",
                    {"missing_parts": missing_parts},
                )
            )

        ai_summary = self.ai.summarize_eco(payload, findings, impact)
        run_id = self.storage.create_workflow_run(
            "eco",
            title or "Untitled ECO",
            int(user["id"]),
            {**payload, "affected_parts": affected_parts},
            findings,
            ai_summary,
        )

        blocking_errors = _has_errors(findings)
        proposed = [
            self._propose(
                run_id,
                "matrix.eco.create",
                user,
                f"Create ECO: {title or 'Untitled ECO'}",
                {
                    "title": title,
                    "reason": reason,
                    "requested_change": requested_change,
                    "affected_parts": affected_parts,
                },
                "Resolve blocking ECO findings before creating the ECO." if blocking_errors else None,
            )
        ]
        for part in valid_parts:
            proposed.append(
                self._propose(
                    run_id,
                    "matrix.eco.add_affected_item",
                    user,
                    f"Add affected item: {part['part_number']}",
                    {"part_number": part["part_number"], "revision": part["revision"], "eco_title": title},
                    None,
                )
            )
        proposed.append(
            self._propose(
                run_id,
                "matrix.eco.submit",
                user,
                f"Submit ECO package: {title or 'Untitled ECO'}",
                {"title": title, "affected_parts": affected_parts},
                "Resolve blocking ECO findings before submit." if blocking_errors else None,
            )
        )

        return {
            "workflow_run": {
                "id": run_id,
                "workflow_type": "eco",
                "title": title or "Untitled ECO",
                "status": "analyzed",
            },
            "findings": findings,
            "ai_summary": ai_summary,
            "impact": impact,
            "open_ecos": open_ecos,
            "proposed_actions": proposed,
        }

    def analyze_part(self, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        part_number = _clean(payload.get("part_number")).upper()
        name = _clean(payload.get("name"))
        revision = _clean(payload.get("revision")) or "A"
        classification = _clean(payload.get("classification"))
        material = _clean(payload.get("material"))
        supplier = _clean(payload.get("supplier"))
        findings: list[dict[str, Any]] = []

        for field, value in {
            "part_number": part_number,
            "name": name,
            "classification": classification,
            "material": material,
        }.items():
            if not value:
                findings.append(_finding("error", "required_field_missing", f"Part {field} is required.", {"field": field}))

        if classification and classification not in ALLOWED_CLASSIFICATIONS:
            findings.append(
                _finding(
                    "warning",
                    "classification_unknown",
                    f"{classification} is not one of the seeded classifications.",
                    {"allowed_classifications": sorted(ALLOWED_CLASSIFICATIONS)},
                )
            )

        if part_number and not re.match(r"^[A-Z]{2,4}-\d{4,6}$", part_number):
            findings.append(
                _finding(
                    "warning",
                    "numbering_pattern",
                    "Part number does not match the seeded business pattern AAA-1234.",
                    {"part_number": part_number},
                )
            )
        findings.extend(validate_part(payload))

        search_block = self.permissions.require_matrix_read("matrix.part.search", user["role"])
        read_block = self.permissions.require_matrix_read("matrix.part.read", user["role"])
        findings.extend(block for block in [search_block, read_block] if block)

        duplicates = []
        if not search_block:
            try:
                duplicates = self.matrix.duplicate_parts(part_number, name, classification)
            except MatrixConnectorError as exc:
                findings.append(_matrix_finding(exc, "matrix.part.search"))
        exact_duplicate = next((part for part in duplicates if part["part_number"].upper() == part_number), None)
        if exact_duplicate:
            findings.append(
                _finding(
                    "error",
                    "exact_part_exists",
                    f"{part_number} already exists in mock Matrix data.",
                    {"part": exact_duplicate},
                )
            )
        elif duplicates:
            findings.append(
                _finding(
                    "warning",
                    "duplicate_candidates",
                    f"{len(duplicates)} possible duplicate or alternate part(s) were found.",
                    {"candidates": duplicates},
                )
            )

        if exact_duplicate and exact_duplicate["lifecycle_state"] == "Obsolete":
            findings.append(
                _finding(
                    "warning",
                    "obsolete_duplicate",
                    "The exact duplicate is obsolete; review whether a replacement part should be created.",
                    {"part_number": part_number},
                )
            )

        ai_summary = self.ai.summarize_part(payload, findings, duplicates)
        run_id = self.storage.create_workflow_run(
            "part",
            part_number or name or "Untitled Part",
            int(user["id"]),
            {
                **payload,
                "part_number": part_number,
                "revision": revision,
                "classification": classification,
                "material": material,
                "supplier": supplier,
            },
            findings,
            ai_summary,
        )

        blocking_errors = _has_errors(findings)
        proposed = []
        if not exact_duplicate:
            proposed.append(
                self._propose(
                    run_id,
                    "matrix.part.create",
                    user,
                    f"Create part: {part_number or name or 'Untitled Part'}",
                    {
                        "part_number": part_number,
                        "name": name,
                        "revision": revision,
                        "classification": classification,
                        "material": material,
                        "supplier": supplier,
                    },
                    "Resolve blocking part findings before creating the part." if blocking_errors else None,
                )
            )
        else:
            proposed.append(
                self._propose(
                    run_id,
                    "matrix.part.update_attributes",
                    user,
                    f"Review attribute update: {part_number}",
                    {
                        "part_number": part_number,
                        "requested_attributes": {
                            "name": name,
                            "revision": revision,
                            "classification": classification,
                            "material": material,
                            "supplier": supplier,
                        },
                        "current_part": exact_duplicate,
                    },
                    None,
                )
            )

        return {
            "workflow_run": {
                "id": run_id,
                "workflow_type": "part",
                "title": part_number or name or "Untitled Part",
                "status": "analyzed",
            },
            "findings": findings,
            "ai_summary": ai_summary,
            "duplicates": duplicates,
            "proposed_actions": proposed,
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
        status, blocked_reason = self.permissions.proposal_state(
            action_key,
            user["role"],
            workflow_blocked_reason,
        )
        return self.storage.create_proposed_action(
            workflow_run_id,
            action_key,
            status,
            preview,
            payload,
            int(user["id"]),
            blocked_reason,
        )


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _parse_parts(value: Any) -> list[str]:
    if isinstance(value, list):
        parts = value
    else:
        parts = re.split(r"[\s,;]+", str(value or ""))
    return [str(part).strip().upper() for part in parts if str(part).strip()]


def _finding(severity: str, code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "details": details,
    }


def _matrix_finding(exc: MatrixConnectorError, action_key: str) -> dict[str, Any]:
    return {
        "severity": "warning",
        "code": exc.code,
        "message": exc.message,
        "details": {"action_key": action_key},
    }


def _has_errors(findings: list[dict[str, Any]]) -> bool:
    return any(finding.get("severity") == "error" for finding in findings)
