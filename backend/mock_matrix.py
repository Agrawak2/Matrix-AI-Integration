from __future__ import annotations

from typing import Any

from .storage import Storage


class MockMatrixConnector:
    def __init__(self, storage: Storage):
        self.storage = storage

    def get_part(self, part_number: str) -> dict[str, Any] | None:
        return self.storage.get_part(part_number)

    def search_parts(self, query: str) -> list[dict[str, Any]]:
        return self.storage.search_parts(query)

    def duplicate_parts(self, part_number: str, name: str, classification: str) -> list[dict[str, Any]]:
        return self.storage.find_part_duplicates(part_number, name, classification)

    def open_ecos_for_parts(self, part_numbers: list[str]) -> list[dict[str, Any]]:
        return self.storage.open_ecos_for_parts(part_numbers)

    def where_used(self, part_numbers: list[str]) -> list[dict[str, Any]]:
        return self.storage.where_used(part_numbers)

