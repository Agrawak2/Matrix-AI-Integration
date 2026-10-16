from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .database import ROOT


RULE_CATALOG_PATH = ROOT / "guidelines" / "RULE_CATALOG.yaml"

ECO_REQUIRED_FIELDS = [
    "eco_category",
    "eco_release_code",
    "responsible_design_engineer",
    "coordinator",
    "hps",
    "lead",
    "manager",
    "sap_project_wbs",
    "sap_project_network",
    "due_date",
]

ECO_RELEASE_CODES = {"ECO-MNB", "EDU-CP", "EDU-GEN", "NPI", "Standard", "Systems"}
DISALLOWED_TEXT = re.compile(r"[<>\\[\\]{}]")


def validate_eco(payload: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    data = _eco_data(payload)

    missing = [field for field in ECO_REQUIRED_FIELDS if not _text(data.get(field))]
    if missing:
        findings.append(
            _finding(
                "ECO-CRT-001",
                f"Mandatory ECO fields are missing before promote: {', '.join(missing)}.",
                {"missing_fields": missing},
            )
        )

    release_code = _text(data.get("eco_release_code"))
    if release_code and release_code not in ECO_RELEASE_CODES:
        findings.append(
            _finding(
                "ECO-CODE-001",
                f"ECO Release Code '{release_code}' is not supported.",
                {"eco_release_code": release_code, "allowed_values": sorted(ECO_RELEASE_CODES)},
            )
        )

    if release_code == "Systems":
        findings.append(
            _finding(
                "ECO-CODE-001",
                "Systems release code requires owner confirmation because the procedure is undefined.",
                {"eco_release_code": release_code},
                severity_override="WARN",
            )
        )

    related_ecrs = _list(data.get("related_ecrs"))
    if release_code == "NPI" and related_ecrs:
        findings.append(
            _finding(
                "ECO-NPI-001",
                "NPI ECOs cannot be attached to an ECR.",
                {"related_ecrs": related_ecrs},
            )
        )

    revised_parts = _list(data.get("revised_parts"))
    revised_specs = _list(data.get("revised_specs"))
    ob_in_parts = _list(data.get("ob_in_parts"))
    if release_code == "NPI" and (revised_parts or revised_specs or ob_in_parts):
        findings.append(
            _finding(
                "ECO-NPI-002",
                "NPI ECOs can only release new products; revised or OB/IN content is not permitted.",
                {
                    "revised_parts": revised_parts,
                    "revised_specs": revised_specs,
                    "ob_in_parts": ob_in_parts,
                },
            )
        )

    gate = _text(payload.get("gate") or payload.get("review_gate"))
    if gate in {"ECO.PromoteToReview", "PromoteToReview", "Review"}:
        if _text(data.get("vc_notes_required")) not in {"Yes", "No"}:
            findings.append(
                _finding(
                    "ECO-NOTES-001",
                    "VC Notes Required must be set to Yes or No before promotion to Review.",
                    {"vc_notes_required": data.get("vc_notes_required")},
                )
            )
        if not _text(data.get("coordinator_instructions")):
            findings.append(
                _finding(
                    "ECO-NOTES-002",
                    "Coordinator Instructions must be set before promotion to Review.",
                    {},
                )
            )

    description = _text(data.get("description"))
    if description and DISALLOWED_TEXT.search(description):
        findings.append(
            _finding(
                "ECO-CRT-001",
                "ECO description contains disallowed characters that may block promotion.",
                {"description": description},
            )
        )

    workflow_flags = payload.get("workflow_flags") if isinstance(payload.get("workflow_flags"), dict) else {}
    if _truthy(payload.get("release_to_sap_requested")) or gate in {"ECO.ReleaseToSAP", "ReleaseToSAP"}:
        if workflow_flags.get("sap_transfer_status") != "complete_black":
            findings.append(
                _finding(
                    "ECO-SAP-001",
                    "SAP transfer must complete without red errors before Release-to-SAP.",
                    {"sap_transfer_status": workflow_flags.get("sap_transfer_status")},
                )
            )

    return findings


def validate_part(payload: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    part_number = _text(payload.get("part_number")).upper()
    part_type = _text(payload.get("part_type") or payload.get("classification"))
    policy = _text(payload.get("policy"))
    description = _text(payload.get("description") or payload.get("name"))
    unit_of_measure = _text(payload.get("unit_of_measure") or payload.get("uom"))

    if part_number and not re.match(r"^\d{8}[A-Z0-9]?$", part_number):
        findings.append(
            _finding(
                "PART-NUM-001",
                "Part number does not match standard IGT format AAABBBCCD plus optional extension.",
                {"part_number": part_number},
            )
        )

    if part_number and (len(part_number) > 18 or part_number != part_number.upper() or DISALLOWED_TEXT.search(part_number)):
        findings.append(
            _finding(
                "PART-NAME-001",
                "Part Name must be uppercase, 18 characters or fewer, and contain no disallowed characters.",
                {"part_number": part_number},
            )
        )

    if _truthy(payload.get("autoname_checked")):
        findings.append(
            _finding(
                "PART-AUTONAME-001",
                "Autoname must be unchecked and Autoname Series must not be selected.",
                {"autoname_checked": payload.get("autoname_checked")},
            )
        )

    findings.extend(validate_title(description, rule_prefix="PART"))

    if description and (len(description) > 40 or description != description.upper() or DISALLOWED_TEXT.search(description)):
        findings.append(
            _finding(
                "PART-DESC-001",
                "Description must be uppercase, 40 characters or fewer, and contain no disallowed characters.",
                {"description": description},
            )
        )

    if not part_type:
        findings.append(_finding("PART-TYPE-001", "Part Type must be selected using the HE042 decision tree.", {}))

    if part_type == "Material_IGT" and unit_of_measure and unit_of_measure != "G":
        findings.append(
            _finding(
                "PART-MATERIALIGT-001",
                "Material_IGT parts should use Gram UOM.",
                {"unit_of_measure": unit_of_measure},
            )
        )

    if part_type == "Tool":
        tool_fields = payload.get("tool_fields") if isinstance(payload.get("tool_fields"), dict) else {}
        missing_tool = []
        if _text(payload.get("environmental_compliance_required")) != "NO":
            missing_tool.append("environmental_compliance_required=NO")
        if not _text(tool_fields.get("tool_vendor") or payload.get("tool_vendor")):
            missing_tool.append("tool_vendor")
        if not _has_number(tool_fields.get("tool_cost") or payload.get("tool_cost")):
            missing_tool.append("tool_cost")
        if missing_tool:
            findings.append(
                _finding(
                    "TOOL-CRT-001",
                    f"Tool part required fields are incomplete: {', '.join(missing_tool)}.",
                    {"missing_fields": missing_tool},
                )
            )

    if _truthy(payload.get("push_to_sap_requested")):
        missing = []
        for key, value in {
            "part_type": part_type,
            "policy": policy,
            "unit_of_measure": unit_of_measure,
            "basic_material": _text(payload.get("basic_material") or payload.get("material")),
            "eco_to_release_or_attached_eco": _text(payload.get("eco_to_release") or payload.get("attached_eco")),
        }.items():
            if not value:
                missing.append(key)
        if missing:
            findings.append(
                _finding(
                    "PART-SAP-001",
                    f"Part is not ready for SAP push; missing {', '.join(missing)}.",
                    {"missing_fields": missing},
                )
            )

    if _truthy(payload.get("delete_requested")) and _truthy(payload.get("exists_in_sap")):
        findings.append(
            _finding(
                "PART-DEL-001",
                "Parts that exist in SAP cannot be deleted and must follow the OB/IN path.",
                {"exists_in_sap": True},
            )
        )

    return findings


def validate_title(title: str, rule_prefix: str = "TITLE") -> list[dict[str, Any]]:
    title = _text(title)
    if not title:
        return []

    findings = []
    if title != title.upper():
        findings.append(_finding("TITLE-001", "Title must be uppercase.", {"title": title}))
    if re.search(r"\b(FOR|OR)\b", title, flags=re.IGNORECASE):
        findings.append(_finding("TITLE-002", "Title must not use FOR or OR.", {"title": title}))
    if "(" in title or ")" in title:
        findings.append(_finding("TITLE-003", "Title must not include parenthetical words or phrases.", {"title": title}))

    if rule_prefix != "TITLE":
        for finding in findings:
            finding["details"]["applied_to"] = rule_prefix
    return findings


def _eco_data(payload: dict[str, Any]) -> dict[str, Any]:
    basic = payload.get("basic_attributes") if isinstance(payload.get("basic_attributes"), dict) else {}
    relations = payload.get("relations") if isinstance(payload.get("relations"), dict) else {}
    data = {**basic, **relations, **payload}
    data.setdefault("type", payload.get("type") or "ECO")
    data.setdefault("policy", payload.get("policy") or "ECO")
    data.setdefault("description", payload.get("description") or payload.get("title"))
    data.setdefault("design_responsibility", payload.get("design_responsibility") or "IGT")
    return data


def _finding(
    rule_id: str,
    message: str,
    evidence: dict[str, Any],
    severity_override: str | None = None,
) -> dict[str, Any]:
    rule = rule_catalog().get(rule_id, {})
    guideline_severity = severity_override or str(rule.get("severity") or "WARN")
    return {
        "severity": _ui_severity(guideline_severity),
        "code": rule_id,
        "message": message,
        "details": evidence,
        "rule_id": rule_id,
        "guideline_severity": guideline_severity,
        "gate": rule.get("gate", ""),
        "suggested_fix": rule.get("fix", ""),
        "refs": rule.get("refs", []),
    }


@lru_cache(maxsize=1)
def rule_catalog() -> dict[str, dict[str, Any]]:
    if not RULE_CATALOG_PATH.exists():
        return {}

    rules: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    in_refs = False
    for raw_line in RULE_CATALOG_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("- id: "):
            rule_id = _unquote(line.removeprefix("- id: ").strip())
            current = {"id": rule_id, "refs": []}
            rules[rule_id] = current
            in_refs = False
            continue
        if current is None:
            continue
        if line.startswith("refs:"):
            current["refs"] = _inline_list(line.removeprefix("refs:").strip())
            in_refs = not current["refs"]
            continue
        if in_refs and line.startswith("- "):
            current.setdefault("refs", []).append(_unquote(line.removeprefix("- ").strip()))
            continue
        in_refs = False
        for key in ("domain", "severity", "gate", "description", "fix"):
            prefix = f"{key}:"
            if line.startswith(prefix):
                current[key] = _unquote(line.removeprefix(prefix).strip())
                break
    return rules


def _inline_list(value: str) -> list[str]:
    if not value.startswith("[") or not value.endswith("]"):
        return []
    inner = value[1:-1].strip()
    if not inner:
        return []
    return [_unquote(item.strip()) for item in inner.split(",")]


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _ui_severity(guideline_severity: str) -> str:
    if guideline_severity in {"BLOCKER", "ERROR"}:
        return "error"
    if guideline_severity == "WARN":
        return "warning"
    return "info"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return [item for item in value if _text(item)]
    if not _text(value):
        return []
    return [item.strip() for item in re.split(r"[\s,;]+", _text(value)) if item.strip()]


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _has_number(value: Any) -> bool:
    if isinstance(value, (int, float)):
        return True
    text = _text(value)
    return bool(text and re.match(r"^\d+(\.\d+)?$", text))
