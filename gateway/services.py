from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from django.conf import settings

from backend.service import handle


JsonObject = dict[str, Any]


def call_matrix_service(envelope: Mapping[str, Any]) -> JsonObject:
    db_path = _backend_db_path()
    return handle(dict(envelope), db_path=db_path)


def _backend_db_path() -> Path | str | None:
    value = getattr(settings, 'MATRIX_AI_BACKEND_DB_PATH', None)
    if isinstance(value, Path):
        return value
    if isinstance(value, str) and value:
        return value
    return None
