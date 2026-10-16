from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT / "data" / "matrix_ai.sqlite3"


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def json_loads(value: str | None, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    return json.loads(value)


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize(db_path: str | Path | None = None) -> sqlite3.Connection:
    conn = connect(db_path)
    _apply_schema(conn)
    _seed(conn)
    return conn


def _apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT
        );

        CREATE TABLE IF NOT EXISTS actions (
            key TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            category TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            enabled INTEGER NOT NULL,
            requires_approval INTEGER NOT NULL,
            allowed_roles_json TEXT NOT NULL,
            connector_method TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            actor_user_id INTEGER REFERENCES users(id),
            action_key TEXT NOT NULL,
            event_type TEXT NOT NULL,
            outcome TEXT NOT NULL,
            request_json TEXT NOT NULL,
            response_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS workflow_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_type TEXT NOT NULL,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            created_by INTEGER NOT NULL REFERENCES users(id),
            created_at TEXT NOT NULL,
            input_json TEXT NOT NULL,
            findings_json TEXT NOT NULL,
            ai_summary_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS proposed_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_run_id INTEGER NOT NULL REFERENCES workflow_runs(id),
            action_key TEXT NOT NULL REFERENCES actions(key),
            status TEXT NOT NULL,
            payload_preview TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_by INTEGER NOT NULL REFERENCES users(id),
            approved_by INTEGER REFERENCES users(id),
            executed_at TEXT,
            blocked_reason TEXT,
            decision_note TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS mock_parts (
            part_number TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            revision TEXT NOT NULL,
            lifecycle_state TEXT NOT NULL,
            classification TEXT NOT NULL,
            owner TEXT NOT NULL,
            material TEXT,
            supplier TEXT,
            attributes_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS mock_ecos (
            eco_number TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            owner TEXT NOT NULL,
            affected_parts_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS mock_bom (
            parent_part TEXT NOT NULL,
            child_part TEXT NOT NULL,
            quantity REAL NOT NULL,
            PRIMARY KEY (parent_part, child_part)
        );

        CREATE TABLE IF NOT EXISTS matrix_api_endpoints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            method TEXT NOT NULL,
            path TEXT NOT NULL,
            summary TEXT NOT NULL,
            service_group TEXT NOT NULL,
            query_params_json TEXT NOT NULL,
            header_params_json TEXT NOT NULL,
            auth_required INTEGER NOT NULL,
            source TEXT NOT NULL,
            local_action_keys_json TEXT NOT NULL,
            matrix_enabled INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_synced_at TEXT NOT NULL,
            UNIQUE(method, path)
        );
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations (id, applied_at) VALUES (?, ?)",
        (1, utc_now()),
    )
    conn.commit()


def _seed(conn: sqlite3.Connection) -> None:
    now = utc_now()
    users = [
        ("engineer", "Erin Engineer", "Engineer"),
        ("admin", "Avery Admin", "Admin"),
        ("approver", "Priya Approver", "Approver"),
    ]
    conn.executemany(
        """
        INSERT INTO users (username, display_name, role, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            display_name = excluded.display_name,
            role = excluded.role
        """,
        [(username, display_name, role, now) for username, display_name, role in users],
    )

    actions = [
        ("matrix.part.search", "Search parts", "Part", "low", 1, 0, ["Engineer", "Admin", "Approver"], "search_parts"),
        ("matrix.part.read", "Read part details", "Part", "low", 1, 0, ["Engineer", "Admin", "Approver"], "get_part"),
        ("matrix.bom.where_used", "Where-used impact", "BOM", "medium", 1, 0, ["Engineer", "Admin", "Approver"], "where_used"),
        ("matrix.eco.search", "Search ECOs", "ECO", "low", 1, 0, ["Engineer", "Admin", "Approver"], "search_ecos"),
        ("matrix.eco.create", "Create ECO", "ECO", "high", 0, 1, ["Engineer", "Admin", "Approver"], "create_eco"),
        ("matrix.eco.add_affected_item", "Add affected item", "ECO", "high", 0, 1, ["Engineer", "Admin", "Approver"], "add_affected_item"),
        ("matrix.eco.submit", "Submit ECO", "ECO", "high", 0, 1, ["Engineer", "Admin", "Approver"], "submit_eco"),
        ("matrix.part.create", "Create part", "Part", "high", 0, 1, ["Engineer", "Admin", "Approver"], "create_part"),
        ("matrix.part.update_attributes", "Update part attributes", "Part", "medium", 0, 1, ["Engineer", "Admin", "Approver"], "update_part_attributes"),
        ("matrix.bom.add_item", "Add BOM item", "BOM", "high", 0, 1, ["Engineer", "Admin", "Approver"], "add_bom_item"),
        ("sap.material.search", "Search SAP materials", "Part", "low", 1, 0, ["Engineer", "Admin", "Approver"], "search_sap_materials"),
        ("matrix.api.catalog.list", "List Matrix API catalog", "Admin", "low", 1, 0, ["Admin"], "list_matrix_api_catalog"),
        ("matrix.api.catalog.sync", "Sync Matrix API catalog", "Admin", "low", 1, 0, ["Admin"], "sync_matrix_api_catalog"),
        ("matrix.api.catalog.update_status", "Update Matrix API status", "Admin", "low", 1, 0, ["Admin"], "update_matrix_api_status"),
        ("matrix.connection.status", "Matrix connection status", "Admin", "low", 1, 0, ["Admin"], "matrix_connection_status"),
    ]
    conn.executemany(
        """
        INSERT INTO actions (
            key, label, category, risk_level, enabled, requires_approval,
            allowed_roles_json, connector_method
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            label = excluded.label,
            category = excluded.category,
            risk_level = excluded.risk_level,
            allowed_roles_json = excluded.allowed_roles_json,
            connector_method = excluded.connector_method
        """,
        [
            (key, label, category, risk_level, enabled, requires_approval, json_dumps(roles), method)
            for key, label, category, risk_level, enabled, requires_approval, roles, method in actions
        ],
    )

    parts = [
        ("ASM-1000", "Main Control Assembly", "B", "Released", "Assembly", "mrosen", "Mixed", "Internal", {"criticality": "high"}),
        ("PCB-2045", "Power Distribution Board", "A", "Released", "Electrical", "jnguyen", "FR4", "Acme Circuits", {"voltage": "24V"}),
        ("PCB-2046", "Power Distribution Board Alternate", "A", "In Work", "Electrical", "jnguyen", "FR4", "Acme Circuits", {"voltage": "24V"}),
        ("MEC-3301", "Bracket Mounting Plate", "C", "Released", "Mechanical", "ssingh", "Aluminum", "ForgeWorks", {"finish": "anodized"}),
        ("CAB-4100", "Harness Front Panel", "A", "Released", "Cable", "rpatel", "Copper", "WireTech", {"length_mm": 420}),
        ("DOC-9001", "Installation Procedure", "D", "Released", "Document", "klee", None, None, {"document_type": "procedure"}),
        ("LEG-7780", "Legacy Sensor Module", "E", "Obsolete", "Electrical", "mrosen", "Mixed", "LegacyCo", {"criticality": "medium"}),
    ]
    conn.executemany(
        """
        INSERT INTO mock_parts (
            part_number, name, revision, lifecycle_state, classification,
            owner, material, supplier, attributes_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(part_number) DO UPDATE SET
            name = excluded.name,
            revision = excluded.revision,
            lifecycle_state = excluded.lifecycle_state,
            classification = excluded.classification,
            owner = excluded.owner,
            material = excluded.material,
            supplier = excluded.supplier,
            attributes_json = excluded.attributes_json
        """,
        [
            (part, name, rev, state, classification, owner, material, supplier, json_dumps(attrs))
            for part, name, rev, state, classification, owner, material, supplier, attrs in parts
        ],
    )

    ecos = [
        ("ECO-240017", "Power board thermal relief update", "In Work", "jnguyen", ["PCB-2045", "ASM-1000"]),
        ("ECO-240023", "Cable routing manufacturability cleanup", "Review", "rpatel", ["CAB-4100", "ASM-1000"]),
        ("ECO-230411", "Legacy sensor retirement", "Released", "mrosen", ["LEG-7780"]),
    ]
    conn.executemany(
        """
        INSERT INTO mock_ecos (eco_number, title, status, owner, affected_parts_json)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(eco_number) DO UPDATE SET
            title = excluded.title,
            status = excluded.status,
            owner = excluded.owner,
            affected_parts_json = excluded.affected_parts_json
        """,
        [(eco, title, status, owner, json_dumps(parts)) for eco, title, status, owner, parts in ecos],
    )

    bom_rows = [
        ("ASM-1000", "PCB-2045", 1),
        ("ASM-1000", "MEC-3301", 2),
        ("ASM-1000", "CAB-4100", 1),
        ("ASM-1000", "DOC-9001", 1),
        ("PCB-2045", "LEG-7780", 1),
    ]
    conn.executemany(
        """
        INSERT INTO mock_bom (parent_part, child_part, quantity)
        VALUES (?, ?, ?)
        ON CONFLICT(parent_part, child_part) DO UPDATE SET
            quantity = excluded.quantity
        """,
        bom_rows,
    )

    conn.commit()


def session_expiry() -> str:
    return (datetime.now(UTC) + timedelta(hours=12)).isoformat(timespec="seconds")
