from __future__ import annotations

from typing import Any


class MockAIAdapter:
    """Deterministic stand-in for a future approved AI provider."""

    def summarize_eco(
        self,
        payload: dict[str, Any],
        findings: list[dict[str, Any]],
        impacted_parts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        title = payload.get("title") or "Untitled ECO"
        errors = _count(findings, "error")
        warnings = _count(findings, "warning")
        impacted = len(impacted_parts)
        return {
            "provider": "mock",
            "summary": (
                f"ECO draft '{title}' has {errors} blocking finding(s), "
                f"{warnings} warning(s), and {impacted} where-used impact record(s)."
            ),
            "recommended_next_steps": _next_steps(errors, warnings),
        }

    def summarize_part(
        self,
        payload: dict[str, Any],
        findings: list[dict[str, Any]],
        duplicates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        part_number = payload.get("part_number") or "new part"
        errors = _count(findings, "error")
        warnings = _count(findings, "warning")
        return {
            "provider": "mock",
            "summary": (
                f"Part readiness check for {part_number} found {len(duplicates)} candidate duplicate(s), "
                f"{errors} blocking finding(s), and {warnings} warning(s)."
            ),
            "recommended_next_steps": _next_steps(errors, warnings),
        }


def _count(findings: list[dict[str, Any]], severity: str) -> int:
    return sum(1 for finding in findings if finding.get("severity") == severity)


def _next_steps(errors: int, warnings: int) -> list[str]:
    if errors:
        return ["Resolve blocking findings before requesting approval."]
    if warnings:
        return ["Review warnings, then request approval for eligible actions."]
    return ["Review proposed actions and request approval when ready."]

