import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.database import initialize
from backend.matrix_config import MatrixProfile
from backend.matrix_connector import EXECUTE_MQL_PATH, MatrixConnectorError, RestReadOnlyMatrixConnector
from backend.matrix_rest import MatrixRestClient
from backend.service import handle
from backend.storage import Storage


class MatrixAIServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "matrix_ai.sqlite3"

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def request(self, action: str, payload: dict | None = None, session_id: str | None = None) -> dict:
        envelope = {
            "action": action,
            "payload": payload or {},
        }
        if session_id:
            envelope["session_id"] = session_id
        return handle(envelope, self.db_path)

    def login(self, username: str) -> tuple[str, dict]:
        response = self.request("auth.login", {"username": username})
        self.assertTrue(response["ok"], response)
        return response["data"]["session_id"], response["data"]["user"]

    def test_login_and_me_use_mock_users(self) -> None:
        session_id, user = self.login("engineer")

        self.assertEqual(user["role"], "Engineer")
        me = self.request("auth.me", session_id=session_id)

        self.assertTrue(me["ok"], me)
        self.assertEqual(me["data"]["user"]["username"], "engineer")
        self.assertIsInstance(me["audit_id"], int)

    def test_permission_update_requires_admin(self) -> None:
        engineer_session, _user = self.login("engineer")
        response = self.request(
            "permissions.update",
            {"action_key": "matrix.eco.create", "enabled": True},
            engineer_session,
        )

        self.assertFalse(response["ok"])
        self.assertIn("Admin", response["errors"][0])

    def test_eco_workflow_generates_findings_and_blocked_write_actions(self) -> None:
        engineer_session, _user = self.login("engineer")
        response = self.request(
            "workflow.eco.analyze",
            {
                "title": "Cooling update",
                "reason": "Thermal issue",
                "requested_change": "Change PCB layout",
                "affected_parts": ["PCB-2045", "ASM-1000"],
            },
            engineer_session,
        )

        self.assertTrue(response["ok"], response)
        data = response["data"]
        self.assertEqual(data["workflow_run"]["workflow_type"], "eco")
        self.assertTrue(any(finding["code"] == "open_eco_overlap" for finding in data["findings"]))
        self.assertTrue(any(finding["code"] == "where_used_impact" for finding in data["findings"]))
        self.assertGreaterEqual(len(data["proposed_actions"]), 3)
        self.assertTrue(all(action["status"] == "blocked" for action in data["proposed_actions"]))
        self.assertTrue(all("disabled by policy" in action["blocked_reason"] for action in data["proposed_actions"]))

    def test_part_workflow_detects_exact_duplicate(self) -> None:
        engineer_session, _user = self.login("engineer")
        response = self.request(
            "workflow.part.analyze",
            {
                "part_number": "PCB-2045",
                "name": "Power Distribution Board",
                "revision": "A",
                "classification": "Electrical",
                "material": "FR4",
                "supplier": "Acme Circuits",
            },
            engineer_session,
        )

        self.assertTrue(response["ok"], response)
        self.assertTrue(any(finding["code"] == "exact_part_exists" for finding in response["data"]["findings"]))
        self.assertEqual(response["data"]["proposed_actions"][0]["action_key"], "matrix.part.update_attributes")

    def test_part_search_returns_matching_parts(self) -> None:
        engineer_session, _user = self.login("engineer")
        response = self.request(
            "matrix.part.search",
            {"part_number": "PCB"},
            engineer_session,
        )

        self.assertTrue(response["ok"], response)
        self.assertEqual(response["data"]["query"], "PCB")
        self.assertEqual(response["data"]["source"], "mock")
        self.assertGreaterEqual(response["data"]["count"], 2)
        part_numbers = {part["part_number"] for part in response["data"]["matches"]}
        self.assertIn("PCB-2045", part_numbers)
        self.assertIn("PCB-2046", part_numbers)

    def test_sap_material_search_uses_configured_connector(self) -> None:
        engineer_session, _user = self.login("engineer")

        response = self.request("sap.material.search", {"query": "BRACKET"}, engineer_session)

        self.assertTrue(response["ok"], response)
        self.assertEqual(response["data"]["source"], "sap")
        self.assertEqual(response["data"]["source_status"]["mode"], "mock")
        self.assertGreaterEqual(response["data"]["count"], 2)

    def test_part_number_plan_identifies_bracket_family_and_stages_part_and_bom(self) -> None:
        engineer_session, _user = self.login("engineer")

        response = self.request(
            "workflow.part_number.plan",
            {
                "prompt": "Let's pull a P/N for a new Bracket...",
                "description": "BRACKET, TEST",
                "suffix": "00",
                "bom_items": [
                    {"child_part": "MEC-3301", "quantity": 2, "find_number": "10"},
                    {"child_part": "CAB-4100", "quantity": 1, "find_number": "20"},
                ],
            },
            engineer_session,
        )

        self.assertTrue(response["ok"], response)
        data = response["data"]
        self.assertEqual(data["workflow_run"]["workflow_type"], "part_number")
        self.assertEqual(data["part_number_plan"]["family"]["prefix"], "629")
        self.assertEqual(data["part_number_plan"]["candidate_part_number"], "62998000")
        self.assertNotIn("63000000", data["part_number_plan"]["alternative_part_numbers"])
        self.assertEqual(
            [action["action_key"] for action in data["proposed_actions"]],
            ["matrix.part.create", "matrix.bom.add_item", "matrix.bom.add_item"],
        )
        self.assertTrue(all(action["status"] == "blocked" for action in data["proposed_actions"]))
        finding_codes = {finding["code"] for finding in data["findings"]}
        self.assertIn("family_reference_unverified", finding_codes)
        self.assertIn("sap_revalidation_required", finding_codes)

    def test_part_search_can_force_matrix_server_read_mode(self) -> None:
        admin_session, _admin = self.login("admin")
        self.assertTrue(self.request("matrix.api.catalog.sync", session_id=admin_session)["ok"])
        self.assertTrue(
            self.request(
                "matrix.api.catalog.update_status",
                {"method": "GET", "path": EXECUTE_MQL_PATH, "matrix_enabled": True},
                admin_session,
            )["ok"]
        )

        profiles_path = Path(self.tempdir.name) / "matrix_profiles.local.json"
        templates_path = Path(self.tempdir.name) / "matrix_mql_templates.local.json"
        profiles_path.write_text(
            json.dumps(
                {
                    "active_profile": "live-test",
                    "profiles": [
                        {
                            "name": "live-test",
                            "passport_url": "https://matrix.example/3dpassport",
                            "space_url": "https://matrix.example/3dspace",
                            "identifier": "svc",
                            "service_name": "SERVICE",
                            "service_secret": "SECRET",
                            "security_context": "ctx",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        templates_path.write_text(
            json.dumps({"templates": {"search_parts": "temp query bus Part {query} *"}}),
            encoding="utf-8",
        )

        engineer_session, _engineer = self.login("engineer")
        with patch.dict(os.environ, {"MATRIX_PROFILE_NAME": ""}), patch(
            "backend.matrix_config.PROFILES_PATH",
            profiles_path,
        ), patch("backend.matrix_config.MQL_TEMPLATES_PATH", templates_path), patch(
            "backend.matrix_connector.MatrixRestClient.execute_mql",
            return_value=json.dumps(
                {
                    "records": [
                        {
                            "part_number": "LIVE-1000",
                            "description": "Live part",
                            "rev": "A",
                            "state": "Released",
                            "type": "Electrical",
                            "owner": "matrix",
                        }
                    ]
                }
            ),
        ) as execute_mql:
            response = self.request(
                "matrix.part.search",
                {"query": "LIVE", "use_matrix_server": True},
                engineer_session,
            )

        self.assertTrue(response["ok"], response)
        self.assertEqual(response["data"]["source"], "matrix")
        self.assertEqual(response["data"]["count"], 1)
        self.assertEqual(response["data"]["matches"][0]["part_number"], "LIVE-1000")
        execute_mql.assert_called_once()

    def test_admin_can_enable_actions_and_approver_can_approve_all_eligible(self) -> None:
        admin_session, _admin = self.login("admin")
        for action_key in ["matrix.eco.create", "matrix.eco.add_affected_item"]:
            response = self.request(
                "permissions.update",
                {"action_key": action_key, "enabled": True},
                admin_session,
            )
            self.assertTrue(response["ok"], response)

        engineer_session, _engineer = self.login("engineer")
        workflow = self.request(
            "workflow.eco.analyze",
            {
                "title": "Documentation correction",
                "reason": "Manufacturing instruction mismatch",
                "requested_change": "Update affected assembly package",
                "affected_parts": ["MEC-3301"],
                "eco_category": "Product",
                "eco_release_code": "Standard",
                "responsible_design_engineer": "engineer",
                "coordinator": "coordinator",
                "hps": "hps",
                "lead": "lead",
                "manager": "manager",
                "sap_project_wbs": "WBS-100",
                "sap_project_network": "NET-100",
                "due_date": "2026-06-30",
            },
            engineer_session,
        )
        self.assertTrue(workflow["ok"], workflow)
        statuses = {action["action_key"]: action["status"] for action in workflow["data"]["proposed_actions"]}
        self.assertEqual(statuses["matrix.eco.create"], "approval_required")
        self.assertEqual(statuses["matrix.eco.add_affected_item"], "approval_required")
        self.assertEqual(statuses["matrix.eco.submit"], "blocked")

        approver_session, _approver = self.login("approver")
        approval = self.request(
            "approval.actions.approve_all_eligible",
            {"workflow_run_id": workflow["data"]["workflow_run"]["id"]},
            approver_session,
        )

        self.assertTrue(approval["ok"], approval)
        self.assertEqual(len(approval["data"]["approved"]), 2)
        self.assertEqual(len(approval["data"]["skipped"]), 1)
        self.assertTrue(all(action["status"] == "executed" for action in approval["data"]["approved"]))

    def test_audit_history_returns_workflows_and_events(self) -> None:
        engineer_session, _user = self.login("engineer")
        self.request(
            "workflow.part.analyze",
            {
                "part_number": "CAB-9999",
                "name": "Harness service jumper",
                "revision": "A",
                "classification": "Cable",
                "material": "Copper",
                "supplier": "WireTech",
            },
            engineer_session,
        )

        history = self.request("audit.workflow.history", {"limit": 10}, engineer_session)

        self.assertTrue(history["ok"], history)
        self.assertGreaterEqual(len(history["data"]["workflows"]), 1)
        self.assertGreaterEqual(len(history["data"]["audit_events"]), 2)

    def test_audit_history_does_not_recursively_expand_audit_responses(self) -> None:
        engineer_session, _user = self.login("engineer")

        first = self.request("audit.workflow.history", {"limit": 10}, engineer_session)
        second = self.request("audit.workflow.history", {"limit": 10}, engineer_session)

        self.assertTrue(first["ok"], first)
        self.assertTrue(second["ok"], second)
        self.assertLess(len(str(second["data"]["audit_events"])), 100_000)

    def test_sqlite_initialization_is_repeatable(self) -> None:
        first = initialize(self.db_path)
        first.close()
        second = initialize(self.db_path)
        users = second.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        actions = second.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
        second.close()

        self.assertEqual(users, 3)
        self.assertGreaterEqual(actions, 9)

    def test_api_catalog_sync_imports_postman_spec_and_preserves_matrix_status(self) -> None:
        admin_session, _admin = self.login("admin")
        sync = self.request("matrix.api.catalog.sync", session_id=admin_session)

        self.assertTrue(sync["ok"], sync)
        self.assertEqual(sync["data"]["total"], 14)
        self.assertEqual(len(sync["data"]["endpoints"]), 14)
        batch = next(endpoint for endpoint in sync["data"]["endpoints"] if endpoint["path"] == "/api/v2/batch/ticket")
        self.assertNotIn("example", batch["header_params"][0])

        update = self.request(
            "matrix.api.catalog.update_status",
            {"method": "GET", "path": EXECUTE_MQL_PATH, "matrix_enabled": True},
            admin_session,
        )
        self.assertTrue(update["ok"], update)
        self.assertTrue(update["data"]["endpoint"]["matrix_enabled"])

        resync = self.request("matrix.api.catalog.sync", session_id=admin_session)
        self.assertTrue(resync["ok"], resync)
        mql = next(endpoint for endpoint in resync["data"]["endpoints"] if endpoint["path"] == EXECUTE_MQL_PATH)
        self.assertTrue(mql["matrix_enabled"])

    def test_api_catalog_mutation_requires_admin_and_is_independent_from_local_permissions(self) -> None:
        engineer_session, _engineer = self.login("engineer")
        denied = self.request("matrix.api.catalog.sync", session_id=engineer_session)
        self.assertFalse(denied["ok"])
        self.assertIn("Admin", denied["errors"][0])

        admin_session, _admin = self.login("admin")
        self.assertTrue(self.request("matrix.api.catalog.sync", session_id=admin_session)["ok"])
        self.assertTrue(
            self.request(
                "matrix.api.catalog.update_status",
                {"method": "GET", "path": EXECUTE_MQL_PATH, "matrix_enabled": True},
                admin_session,
            )["ok"]
        )
        self.assertTrue(
            self.request(
                "permissions.update",
                {"action_key": "matrix.part.read", "enabled": False},
                admin_session,
            )["ok"]
        )

        catalog = self.request("matrix.api.catalog.list", {"matrix_enabled": True}, admin_session)
        self.assertTrue(catalog["ok"], catalog)
        self.assertTrue(any(endpoint["path"] == EXECUTE_MQL_PATH for endpoint in catalog["data"]["endpoints"]))

        permissions = self.request("permissions.list", session_id=admin_session)
        part_read = next(action for action in permissions["data"]["actions"] if action["key"] == "matrix.part.read")
        self.assertFalse(part_read["enabled"])

    def test_matrix_rest_client_uses_transient_token_cas_and_execute_mql(self) -> None:
        calls = []

        def fake_transport(url: str, headers: dict[str, str]) -> str:
            calls.append((url, headers))
            if "/api/v2/batch/ticket" in url:
                return '{"access_token": "TGT-1"}'
            if "/api/login/cas/transient" in url:
                return '{"access_token": "ST-1"}'
            return '{"part": {"part_number": "PCB-2045"}}'

        profile = MatrixProfile(
            name="qa",
            passport_url="https://matrix.example/3dpassport",
            space_url="https://matrix.example/3dspace",
            identifier="svc",
            service_name="SERVICE",
            service_secret="SECRET",
            security_context="ctx",
        )
        client = MatrixRestClient(profile, transport=fake_transport)

        self.assertEqual(client.execute_mql("print person svc"), '{"part": {"part_number": "PCB-2045"}}')
        self.assertIn("DS-SERVICE-SECRET", calls[0][1])
        self.assertIn("SecurityContext", calls[2][1])

    def test_rest_connector_reports_disabled_endpoint_and_missing_template(self) -> None:
        conn = initialize(self.db_path)
        storage = Storage(conn)

        class FakeRestClient:
            def execute_mql(self, mql: str) -> str:
                return '{"part": {"part_number": "PCB-2045"}}'

        connector = RestReadOnlyMatrixConnector(
            storage,
            FakeRestClient(),  # type: ignore[arg-type]
            {"get_part": "print bus Part {part_number} *"},
        )
        with self.assertRaises(MatrixConnectorError) as disabled:
            connector.get_part("PCB-2045")
        self.assertEqual(disabled.exception.code, "matrix_api_disabled")

        storage.sync_matrix_api_endpoints(
            [
                {
                    "method": "GET",
                    "path": EXECUTE_MQL_PATH,
                    "summary": "MQL",
                    "service_group": "MQLService",
                    "query_params": [],
                    "header_params": [],
                    "auth_required": True,
                    "source": "test",
                    "local_action_keys": [],
                }
            ]
        )
        storage.update_matrix_api_endpoint_status("GET", EXECUTE_MQL_PATH, True)
        missing_template = RestReadOnlyMatrixConnector(storage, FakeRestClient(), {})  # type: ignore[arg-type]
        with self.assertRaises(MatrixConnectorError) as missing:
            missing_template.get_part("PCB-2045")
        self.assertEqual(missing.exception.code, "matrix_mql_template_missing")
        conn.close()

    def test_rest_connector_parses_plain_mql_dump_part_search(self) -> None:
        conn = initialize(self.db_path)
        storage = Storage(conn)
        storage.sync_matrix_api_endpoints(
            [
                {
                    "method": "GET",
                    "path": EXECUTE_MQL_PATH,
                    "summary": "MQL",
                    "service_group": "MQLService",
                    "query_params": [],
                    "header_params": [],
                    "auth_required": True,
                    "source": "test",
                    "local_action_keys": [],
                }
            ]
        )
        storage.update_matrix_api_endpoint_status("GET", EXECUTE_MQL_PATH, True)

        class FakeRestClient:
            def __init__(self) -> None:
                self.mql = ""

            def execute_mql(self, mql: str) -> str:
                self.mql = mql
                return "\n".join(
                    [
                        "Part|PCB-2045|A|Released|jnguyen|Power Distribution Board",
                        "Part|PCB-2046|A|In Work|jnguyen|Power Distribution Board Alternate",
                    ]
                )

        rest_client = FakeRestClient()
        connector = RestReadOnlyMatrixConnector(
            storage,
            rest_client,  # type: ignore[arg-type]
            {"search_parts": 'temp query bus Part "{query_pattern}" * select current owner description dump |'},
        )

        matches = connector.search_parts("PCB")

        self.assertEqual([part["part_number"] for part in matches], ["PCB-2045", "PCB-2046"])
        self.assertEqual(matches[0]["name"], "Power Distribution Board")
        self.assertEqual(matches[1]["lifecycle_state"], "In Work")
        self.assertIn('"*PCB*"', rest_client.mql)
        conn.close()

    def test_rest_read_mode_without_config_adds_non_invented_workflow_finding(self) -> None:
        engineer_session, _user = self.login("engineer")
        missing_profile = Path(self.tempdir.name) / "missing_profiles.json"
        missing_templates = Path(self.tempdir.name) / "missing_templates.json"
        with patch.dict(os.environ, {"MATRIX_CONNECTOR_MODE": "rest-read"}), patch(
            "backend.matrix_config.PROFILES_PATH",
            missing_profile,
        ), patch("backend.matrix_config.MQL_TEMPLATES_PATH", missing_templates):
            response = self.request(
                "workflow.part.analyze",
                {
                    "part_number": "12345678",
                    "name": "BRACKET, TEST",
                    "revision": "A",
                    "classification": "Mechanical",
                    "material": "Aluminum",
                    "supplier": "ForgeWorks",
                },
                engineer_session,
            )

        self.assertTrue(response["ok"], response)
        self.assertTrue(any(finding["code"] == "matrix_rest_config_missing" for finding in response["data"]["findings"]))

    def test_guideline_validators_add_rule_ids_to_eco_and_part_reviews(self) -> None:
        engineer_session, _user = self.login("engineer")
        eco = self.request(
            "workflow.eco.analyze",
            {
                "title": "NPI validation",
                "reason": "Test",
                "requested_change": "Test",
                "affected_parts": ["MEC-3301"],
                "eco_category": "Product",
                "eco_release_code": "NPI",
                "responsible_design_engineer": "engineer",
                "coordinator": "coordinator",
                "hps": "hps",
                "lead": "lead",
                "manager": "manager",
                "sap_project_wbs": "WBS-100",
                "sap_project_network": "NET-100",
                "due_date": "2026-06-30",
                "relations": {"related_ecrs": ["ECR-1"], "revised_parts": ["MEC-3301"]},
            },
            engineer_session,
        )
        self.assertTrue(eco["ok"], eco)
        eco_rule_ids = {finding.get("rule_id") for finding in eco["data"]["findings"]}
        self.assertIn("ECO-NPI-001", eco_rule_ids)
        self.assertIn("ECO-NPI-002", eco_rule_ids)

        part = self.request(
            "workflow.part.analyze",
            {
                "part_number": "12345678",
                "name": "BRACKET FOR (TEST)",
                "revision": "A",
                "classification": "Mechanical",
                "material": "Aluminum",
                "supplier": "ForgeWorks",
            },
            engineer_session,
        )
        self.assertTrue(part["ok"], part)
        part_rule_ids = {finding.get("rule_id") for finding in part["data"]["findings"]}
        self.assertIn("TITLE-002", part_rule_ids)
        self.assertIn("TITLE-003", part_rule_ids)


if __name__ == "__main__":
    unittest.main()
