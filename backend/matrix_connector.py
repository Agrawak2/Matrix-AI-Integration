from __future__ import annotations

import json
from typing import Any, Protocol

from .matrix_config import connector_mode, load_active_profile, load_mql_templates
from .matrix_rest import MatrixRestClient
from .mock_matrix import MockMatrixConnector
from .storage import Storage


EXECUTE_MQL_PATH = "/resources/IGT/v1/MQLService/executeMQL"


class MatrixConnector(Protocol):
    def get_part(self, part_number: str) -> dict[str, Any] | None:
        ...

    def search_parts(self, query: str) -> list[dict[str, Any]]:
        ...

    def duplicate_parts(self, part_number: str, name: str, classification: str) -> list[dict[str, Any]]:
        ...

    def open_ecos_for_parts(self, part_numbers: list[str]) -> list[dict[str, Any]]:
        ...

    def where_used(self, part_numbers: list[str]) -> list[dict[str, Any]]:
        ...


class MatrixConnectorError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def create_matrix_connector(storage: Storage, mode: str | None = None) -> MatrixConnector:
    selected_mode = (mode or connector_mode()).strip().lower() or "mock"
    if selected_mode != "rest-read":
        return MockMatrixConnector(storage)

    try:
        profile = load_active_profile()
        templates = load_mql_templates()
    except Exception as exc:
        return UnavailableMatrixConnector("matrix_rest_config_missing", str(exc))

    return RestReadOnlyMatrixConnector(storage, MatrixRestClient(profile), templates)


class UnavailableMatrixConnector:
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message

    def get_part(self, part_number: str) -> dict[str, Any] | None:
        raise MatrixConnectorError(self.code, self.message)

    def search_parts(self, query: str) -> list[dict[str, Any]]:
        raise MatrixConnectorError(self.code, self.message)

    def duplicate_parts(self, part_number: str, name: str, classification: str) -> list[dict[str, Any]]:
        raise MatrixConnectorError(self.code, self.message)

    def open_ecos_for_parts(self, part_numbers: list[str]) -> list[dict[str, Any]]:
        raise MatrixConnectorError(self.code, self.message)

    def where_used(self, part_numbers: list[str]) -> list[dict[str, Any]]:
        raise MatrixConnectorError(self.code, self.message)


class RestReadOnlyMatrixConnector:
    def __init__(self, storage: Storage, rest_client: MatrixRestClient, templates: dict[str, str]):
        self.storage = storage
        self.rest_client = rest_client
        self.templates = templates

    def get_part(self, part_number: str) -> dict[str, Any] | None:
        raw = self._execute_template("get_part", part_number=part_number)
        records = _records(raw, _PART_MQL_COLUMNS)
        if not records:
            return None
        return _normalize_part(records[0])

    def search_parts(self, query: str) -> list[dict[str, Any]]:
        raw = self._execute_template("search_parts", query=query, query_pattern=_mql_pattern(query))
        return [_normalize_part(record) for record in _records(raw, _PART_MQL_COLUMNS)]

    def duplicate_parts(self, part_number: str, name: str, classification: str) -> list[dict[str, Any]]:
        template_name = "duplicate_parts" if "duplicate_parts" in self.templates else "search_parts"
        raw = self._execute_template(
            template_name,
            query=name or part_number,
            query_pattern=_mql_pattern(name or part_number),
            part_number=part_number,
            name=name,
            classification=classification,
        )
        return [_normalize_part(record) for record in _records(raw, _PART_MQL_COLUMNS)]

    def open_ecos_for_parts(self, part_numbers: list[str]) -> list[dict[str, Any]]:
        raw = self._execute_template("open_ecos_for_parts", part_numbers=",".join(part_numbers))
        return [_normalize_eco(record) for record in _records(raw, _ECO_MQL_COLUMNS)]

    def where_used(self, part_numbers: list[str]) -> list[dict[str, Any]]:
        raw = self._execute_template("where_used", part_numbers=",".join(part_numbers))
        records = _records(raw)
        return [record for record in records if isinstance(record, dict)]

    def _execute_template(self, template_name: str, **values: str) -> str:
        if not self.storage.is_matrix_api_endpoint_enabled("GET", EXECUTE_MQL_PATH):
            raise MatrixConnectorError(
                "matrix_api_disabled",
                "Matrix executeMQL is not marked enabled in the API catalog.",
            )
        template = self.templates.get(template_name)
        if not template:
            raise MatrixConnectorError(
                "matrix_mql_template_missing",
                f"Missing MQL template '{template_name}'.",
            )
        try:
            mql = template.format(**{key: _mql_value(value) for key, value in values.items()})
        except KeyError as exc:
            raise MatrixConnectorError(
                "matrix_mql_template_invalid",
                f"MQL template '{template_name}' references missing value {exc}.",
            ) from exc
        return self.rest_client.execute_mql(mql)


_PART_MQL_COLUMNS = ["type", "name", "revision", "current", "owner", "description"]
_ECO_MQL_COLUMNS = ["type", "name", "revision", "current", "owner", "description"]


def _records(raw: str, dump_columns: list[str] | None = None) -> list[dict[str, Any]]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return _mql_dump_records(raw, dump_columns, exc)

    if isinstance(payload, list):
        return [record for record in payload if isinstance(record, dict)]
    if isinstance(payload, dict):
        for key in ("records", "rows", "data", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [record for record in value if isinstance(record, dict)]
        for key in ("part", "eco", "result"):
            value = payload.get(key)
            if isinstance(value, dict):
                return [value]
        return [payload]
    return []


def _mql_dump_records(
    raw: str,
    columns: list[str] | None,
    json_error: json.JSONDecodeError,
) -> list[dict[str, Any]]:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        return []

    preview = lines[0][:240]
    preview_lower = preview.lower()
    if preview_lower.startswith(("error", "exception", "failed")) or "mql error" in preview_lower:
        raise MatrixConnectorError("matrix_mql_failed", preview)

    if not columns:
        raise MatrixConnectorError(
            "matrix_mql_parse_failed",
            "Matrix MQL response was not JSON and no dump column map was available.",
        ) from json_error

    records = []
    for line in lines:
        values = line.split("|")
        record = {
            column: values[index].strip() if index < len(values) else ""
            for index, column in enumerate(columns)
        }
        if len(values) > len(columns):
            record["extra"] = [value.strip() for value in values[len(columns) :]]
        records.append(record)
    return records


def _normalize_part(record: dict[str, Any]) -> dict[str, Any]:
    part_number = record.get("part_number") or record.get("name") or record.get("partName") or record.get("part")
    revision = record.get("revision") or record.get("rev") or record.get("majorrevision") or ""
    lifecycle_state = record.get("lifecycle_state") or record.get("state") or record.get("current") or ""
    classification = record.get("classification") or record.get("type") or record.get("part_type") or ""
    description = record.get("description") or record.get("title") or record.get("name") or ""
    normalized = dict(record)
    normalized.update(
        {
            "part_number": str(part_number or ""),
            "name": str(description or part_number or ""),
            "revision": str(revision),
            "lifecycle_state": str(lifecycle_state),
            "classification": str(classification),
            "owner": str(record.get("owner") or ""),
            "material": record.get("material") or record.get("basic_material"),
            "supplier": record.get("supplier"),
            "attributes": record.get("attributes") if isinstance(record.get("attributes"), dict) else {},
        }
    )
    return normalized


def _normalize_eco(record: dict[str, Any]) -> dict[str, Any]:
    affected = record.get("affected_parts")
    if isinstance(affected, str):
        affected = [part.strip() for part in affected.split(",") if part.strip()]
    elif not isinstance(affected, list):
        affected = []

    normalized = dict(record)
    normalized.update(
        {
            "eco_number": str(record.get("eco_number") or record.get("name") or record.get("eco") or ""),
            "title": str(record.get("title") or record.get("description") or ""),
            "status": str(record.get("status") or record.get("state") or record.get("current") or ""),
            "owner": str(record.get("owner") or ""),
            "affected_parts": affected,
        }
    )
    return normalized


def _mql_value(value: str) -> str:
    return str(value).replace('"', '\\"').strip()


def _mql_pattern(value: str) -> str:
    text = str(value).strip()
    if "*" in text or "?" in text:
        return text
    return f"*{text}*"
