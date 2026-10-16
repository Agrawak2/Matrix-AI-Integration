from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .database import ROOT


CONFIG_DIR = ROOT / "config"
PROFILES_PATH = CONFIG_DIR / "matrix_profiles.local.json"
MQL_TEMPLATES_PATH = CONFIG_DIR / "matrix_mql_templates.local.json"


@dataclass(frozen=True)
class MatrixProfile:
    name: str
    passport_url: str
    space_url: str
    identifier: str
    service_name: str
    service_secret: str
    security_context: str = ""


def connector_mode() -> str:
    return os.environ.get("MATRIX_CONNECTOR_MODE", "mock").strip().lower() or "mock"


def active_profile_name() -> str:
    return os.environ.get("MATRIX_PROFILE_NAME", "").strip()


def load_active_profile(path: str | Path | None = None) -> MatrixProfile:
    profiles_path = Path(path) if path is not None else PROFILES_PATH
    raw = _read_json_object(profiles_path)
    profiles = raw.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        raise ValueError(f"{profiles_path} must contain a non-empty profiles list.")

    selected_name = active_profile_name() or str(raw.get("active_profile") or "").strip()
    if not selected_name:
        selected_name = str(profiles[0].get("name") or "").strip()

    for profile in profiles:
        if isinstance(profile, dict) and profile.get("name") == selected_name:
            return _profile_from_dict(profile, profiles_path)

    raise ValueError(f"Matrix profile '{selected_name}' was not found in {profiles_path}.")


def load_mql_templates(path: str | Path | None = None) -> dict[str, str]:
    templates_path = Path(path) if path is not None else MQL_TEMPLATES_PATH
    raw = _read_json_object(templates_path)
    templates = raw.get("templates")
    if not isinstance(templates, dict):
        raise ValueError(f"{templates_path} must contain a templates object.")
    return {str(key): str(value) for key, value in templates.items()}


def connection_status(storage: Any | None = None) -> dict[str, Any]:
    mode = connector_mode()
    profile_status = _safe_profile_status()
    template_status = _safe_template_status()
    endpoint_enabled = None
    if storage is not None:
        endpoint_enabled = storage.is_matrix_api_endpoint_enabled(
            "GET",
            "/resources/IGT/v1/MQLService/executeMQL",
        )

    return {
        "mode": mode,
        "profile_configured": profile_status["configured"],
        "profile_name": profile_status["name"],
        "profile_error": profile_status["error"],
        "templates_configured": template_status["configured"],
        "template_names": template_status["names"],
        "template_error": template_status["error"],
        "execute_mql_matrix_enabled": endpoint_enabled,
        "rest_read_default_enabled": mode == "rest-read",
        "ready_for_rest_read": bool(
            profile_status["configured"]
            and template_status["configured"]
            and endpoint_enabled
        ),
    }


def _safe_profile_status() -> dict[str, Any]:
    try:
        profile = load_active_profile()
    except Exception as exc:
        return {"configured": False, "name": None, "error": str(exc)}
    return {"configured": True, "name": profile.name, "error": None}


def _safe_template_status() -> dict[str, Any]:
    try:
        templates = load_mql_templates()
    except Exception as exc:
        return {"configured": False, "names": [], "error": str(exc)}
    return {"configured": True, "names": sorted(templates), "error": None}


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"{path} does not exist.")
    with path.open("r", encoding="utf-8-sig") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return raw


def _profile_from_dict(raw: dict[str, Any], source_path: Path) -> MatrixProfile:
    required = {
        "name": "name",
        "passport_url": "passport_url",
        "space_url": "space_url",
        "identifier": "identifier",
        "service_name": "service_name",
        "service_secret": "service_secret",
    }
    values = {field: str(raw.get(key) or "").strip() for field, key in required.items()}
    missing = [field for field, value in values.items() if not value]
    if missing:
        raise ValueError(f"{source_path} profile is missing: {', '.join(missing)}.")

    return MatrixProfile(
        name=values["name"],
        passport_url=values["passport_url"].rstrip("/"),
        space_url=values["space_url"].rstrip("/"),
        identifier=values["identifier"],
        service_name=values["service_name"],
        service_secret=values["service_secret"],
        security_context=str(raw.get("security_context") or "").strip(),
    )
