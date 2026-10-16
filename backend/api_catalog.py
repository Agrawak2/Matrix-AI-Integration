from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .database import ROOT
from .storage import Storage


DEFAULT_SPEC_PATH = ROOT / "REST API Info" / "IGT_WebServicesR2025x_postman_specification.json"

ENDPOINT_ACTION_MAP = {
    ("GET", "/resources/IGT/v1/MQLService/executeMQL"): [
        "matrix.part.search",
        "matrix.part.read",
        "matrix.bom.where_used",
        "matrix.eco.search",
    ],
}


class MatrixApiCatalogService:
    def __init__(self, storage: Storage):
        self.storage = storage

    def list_endpoints(self, enabled_filter: bool | None = None) -> list[dict[str, Any]]:
        return self.storage.list_matrix_api_endpoints(enabled_filter)

    def sync_from_default_spec(self) -> dict[str, Any]:
        endpoints = load_openapi_endpoints(DEFAULT_SPEC_PATH)
        result = self.storage.sync_matrix_api_endpoints(endpoints)
        return {
            **result,
            "source": str(DEFAULT_SPEC_PATH),
            "endpoints": self.storage.list_matrix_api_endpoints(),
        }

    def update_status(self, method: str, path: str, matrix_enabled: bool) -> dict[str, Any]:
        return self.storage.update_matrix_api_endpoint_status(method, path, matrix_enabled)


def load_openapi_endpoints(spec_path: str | Path = DEFAULT_SPEC_PATH) -> list[dict[str, Any]]:
    path = Path(spec_path)
    with path.open("r", encoding="utf-8") as handle:
        spec = json.load(handle)

    endpoints: list[dict[str, Any]] = []
    paths = spec.get("paths", {})
    if not isinstance(paths, dict):
        return endpoints

    for api_path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, operation in methods.items():
            method_upper = method.upper()
            if method_upper not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            if not isinstance(operation, dict):
                continue

            query_params = _parameters(operation, "query")
            header_params = _parameters(operation, "header")
            endpoints.append(
                {
                    "method": method_upper,
                    "path": api_path,
                    "summary": operation.get("summary") or "",
                    "service_group": _service_group(api_path),
                    "query_params": query_params,
                    "header_params": header_params,
                    "auth_required": _auth_required(api_path, query_params, header_params),
                    "source": path.name,
                    "local_action_keys": ENDPOINT_ACTION_MAP.get((method_upper, api_path), []),
                }
            )

    return endpoints


def _parameters(operation: dict[str, Any], location: str) -> list[dict[str, Any]]:
    params = operation.get("parameters", [])
    if not isinstance(params, list):
        return []

    normalized = []
    for param in params:
        if not isinstance(param, dict) or param.get("in") != location:
            continue
        normalized.append(
            {
                "name": param.get("name") or "",
                "required": bool(param.get("required")),
            }
        )
    return normalized


def _service_group(api_path: str) -> str:
    parts = [part for part in api_path.split("/") if part]
    if parts[:3] == ["resources", "IGT", "v1"] and len(parts) >= 4:
        return parts[3]
    if parts and parts[0] == "api":
        return "3DPassport"
    return "Other"


def _auth_required(
    api_path: str,
    query_params: list[dict[str, Any]],
    header_params: list[dict[str, Any]],
) -> bool:
    names = {str(param.get("name", "")).lower() for param in query_params + header_params}
    return api_path.startswith("/resources/") or "ticket" in names or "ds-service-secret" in names
