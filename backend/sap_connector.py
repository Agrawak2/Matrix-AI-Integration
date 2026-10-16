from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path
from typing import Any, Protocol
from xml.etree import ElementTree


class SapConnectorError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class SapMaterialConnector(Protocol):
    mode: str

    def search_materials(self, query: str) -> list[dict[str, Any]]:
        ...

    def used_sequences(self, family_prefix: str) -> set[int]:
        ...

    def status(self) -> dict[str, Any]:
        ...


class MockSapMaterialConnector:
    mode = "mock"

    def __init__(self):
        self.materials = [
            {"material_number": "62900000", "description": "BRKT-MINI SPECT RH", "source": "SAP ECC"},
            {"material_number": "62900100", "description": "BRACKET-BOX LOWER", "source": "SAP ECC"},
            {"material_number": "62997900", "description": "BRACKET-RETAINER LIFT CARRIAGE", "source": "SAP ECC"},
        ]

    def search_materials(self, query: str) -> list[dict[str, Any]]:
        normalized = query.strip().casefold()
        return [
            dict(material)
            for material in self.materials
            if normalized in material["material_number"].casefold()
            or normalized in material["description"].casefold()
        ]

    def used_sequences(self, family_prefix: str) -> set[int]:
        if family_prefix == "629":
            return set(range(629000, 629980))
        return set()

    def status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "live": False,
            "record_count": len(self.materials),
            "message": "Deterministic mock SAP data; do not use it to authorize a production part number.",
        }


class WorkbookSapSnapshotConnector:
    mode = "workbook-snapshot"

    def __init__(self, path: Path):
        self.path = path
        self.materials, self.metadata = _read_workbook_materials(path)

    def search_materials(self, query: str) -> list[dict[str, Any]]:
        normalized = query.strip().casefold()
        return [
            dict(material)
            for material in self.materials
            if material["source"] != "Matrix"
            and (normalized in material["material_number"].casefold()
            or normalized in material["description"].casefold()
            )
        ][:500]

    def used_sequences(self, family_prefix: str) -> set[int]:
        return _used_sequences(self.materials, family_prefix)

    def status(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "live": False,
            "record_count": len(self.materials),
            "path": str(self.path),
            **self.metadata,
            "message": "Cached SAP/Mapics results from a workbook snapshot; revalidate before creation.",
        }


class UnavailableSapMaterialConnector:
    mode = "unavailable"

    def __init__(self, message: str):
        self.message = message

    def search_materials(self, query: str) -> list[dict[str, Any]]:
        raise SapConnectorError("sap_source_unavailable", self.message)

    def used_sequences(self, family_prefix: str) -> set[int]:
        raise SapConnectorError("sap_source_unavailable", self.message)

    def status(self) -> dict[str, Any]:
        return {"mode": self.mode, "live": False, "record_count": 0, "message": self.message}


def create_sap_connector() -> SapMaterialConnector:
    configured = os.environ.get("SAP_PART_SEARCH_WORKBOOK", "").strip()
    if not configured:
        return MockSapMaterialConnector()
    path = Path(configured)
    if not path.exists():
        return UnavailableSapMaterialConnector(f"SAP_PART_SEARCH_WORKBOOK does not exist: {path}")
    try:
        return WorkbookSapSnapshotConnector(path)
    except Exception as exc:
        return UnavailableSapMaterialConnector(f"Could not read SAP workbook snapshot: {exc}")


def _read_workbook_materials(path: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    namespaces = {
        "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
        "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        "pkg": "http://schemas.openxmlformats.org/package/2006/relationships",
    }
    with zipfile.ZipFile(path) as archive:
        shared = _shared_strings(archive.read("xl/sharedStrings.xml"))
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        relationships = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            item.attrib["Id"]: item.attrib["Target"]
            for item in relationships.findall("pkg:Relationship", namespaces)
        }
        sheet = next(
            item for item in workbook.findall("main:sheets/main:sheet", namespaces)
            if item.attrib.get("name") == "Sheet1"
        )
        relationship_id = sheet.attrib[f"{{{namespaces['rel']}}}id"]
        target = targets[relationship_id].lstrip("/")
        sheet_path = target if target.startswith("xl/") else f"xl/{target}"
        worksheet = ElementTree.fromstring(archive.read(sheet_path))
        metadata_text = archive.read("xl/customProperty3.bin").decode("utf-16le", errors="replace")

    materials = []
    for row in worksheet.findall("main:sheetData/main:row", namespaces):
        values: dict[str, str] = {}
        for cell in row.findall("main:c", namespaces):
            column = re.match(r"[A-Z]+", cell.attrib.get("r", ""))
            value = cell.find("main:v", namespaces)
            if not column or value is None or value.text is None:
                continue
            text = value.text
            if cell.attrib.get("t") == "s":
                text = shared[int(text)]
            values[column.group()] = text
        source = values.get("B", "").strip()
        material_number = values.get("A", "").strip()
        if source not in {"SAP ECC", "Mapics", "Matrix"} or not material_number:
            continue
        materials.append(
            {
                "material_number": material_number,
                "description": values.get("C", "").strip(),
                "source": source,
            }
        )
    metadata = {
        "query_id": _xml_text(metadata_text, "Id"),
        "last_refreshed": _xml_text(metadata_text, "LastRefreshed"),
        "system_id": _xml_text(metadata_text, "SystemId"),
    }
    return materials, metadata


def _shared_strings(data: bytes) -> list[str]:
    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    root = ElementTree.fromstring(data)
    return ["".join(node.text or "" for node in item.findall(".//main:t", namespace)) for item in root]


def _used_sequences(materials: list[dict[str, Any]], family_prefix: str) -> set[int]:
    used = set()
    for material in materials:
        number = str(material.get("material_number", ""))
        if re.fullmatch(r"\d{8}[A-Z0-9]?", number) and number.startswith(family_prefix):
            used.add(int(number[:6]))
    return used


def _xml_text(value: str, tag: str) -> str:
    match = re.search(rf"<{tag}>(.*?)</{tag}>", value)
    return match.group(1).strip() if match else ""
