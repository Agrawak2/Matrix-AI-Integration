from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from django.test import Client, TestCase, override_settings


class GatewayViewTests(TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.backend_db_path = Path(self.tempdir.name) / 'matrix_ai.sqlite3'
        self.settings_override = override_settings(MATRIX_AI_BACKEND_DB_PATH=self.backend_db_path)
        self.settings_override.enable()
        self.client = Client()

    def tearDown(self) -> None:
        self.settings_override.disable()
        self.tempdir.cleanup()

    def post_api(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.client.post(
            '/api/',
            data=json.dumps({'action': action, 'payload': payload or {}}),
            content_type='application/json',
        )
        return response.json()

    def test_home_page_renders_django_shell(self) -> None:
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Matrix AI Integration')
        self.assertContains(response, 'Part Search')
        self.assertContains(response, 'New Part Number')
        self.assertContains(response, 'Prepare Creation Summary')
        self.assertContains(response, 'Matrix server')
        self.assertContains(response, 'Admin/API')

    def test_login_stores_backend_session_in_django_session(self) -> None:
        response = self.post_api('auth.login', {'username': 'engineer'})

        self.assertTrue(response['ok'], response)
        self.assertEqual(response['data']['user']['role'], 'Engineer')
        self.assertIn('matrix_ai_session_id', self.client.session)

    def test_api_uses_django_session_when_session_id_is_omitted(self) -> None:
        login = self.post_api('auth.login', {'username': 'engineer'})
        self.assertTrue(login['ok'], login)

        workflow = self.post_api(
            'workflow.part.analyze',
            {
                'part_number': 'PCB-7777',
                'name': 'Power Distribution Board Low Heat Variant',
                'revision': 'A',
                'classification': 'Electrical',
                'material': 'FR4',
                'supplier': 'Acme Circuits',
            },
        )

        self.assertTrue(workflow['ok'], workflow)
        self.assertEqual(workflow['data']['workflow_run']['workflow_type'], 'part')

    def test_part_search_returns_matches_through_gateway_api(self) -> None:
        login = self.post_api('auth.login', {'username': 'engineer'})
        self.assertTrue(login['ok'], login)

        search = self.post_api('matrix.part.search', {'part_number': 'PCB'})

        self.assertTrue(search['ok'], search)
        self.assertEqual(search['data']['query'], 'PCB')
        self.assertEqual(search['data']['source'], 'mock')
        self.assertGreaterEqual(search['data']['count'], 2)
        part_numbers = {part['part_number'] for part in search['data']['matches']}
        self.assertIn('PCB-2045', part_numbers)
        self.assertIn('PCB-2046', part_numbers)

    def test_part_number_plan_returns_creation_summary_through_gateway_api(self) -> None:
        login = self.post_api('auth.login', {'username': 'engineer'})
        self.assertTrue(login['ok'], login)

        plan = self.post_api(
            'workflow.part_number.plan',
            {
                'prompt': "Let's pull a P/N for a new Bracket...",
                'description': 'BRACKET, TEST',
                'suffix': '00',
                'bom_items': [],
            },
        )

        self.assertTrue(plan['ok'], plan)
        self.assertEqual(plan['data']['part_number_plan']['candidate_part_number'], '62998000')

    def test_admin_catalog_actions_work_through_gateway_api(self) -> None:
        login = self.post_api('auth.login', {'username': 'admin'})
        self.assertTrue(login['ok'], login)

        sync = self.post_api('matrix.api.catalog.sync')
        self.assertTrue(sync['ok'], sync)
        self.assertEqual(sync['data']['total'], 14)

        update = self.post_api(
            'matrix.api.catalog.update_status',
            {
                'method': 'GET',
                'path': '/resources/IGT/v1/MQLService/executeMQL',
                'matrix_enabled': True,
            },
        )
        self.assertTrue(update['ok'], update)
        self.assertTrue(update['data']['endpoint']['matrix_enabled'])

    def test_non_admin_cannot_mutate_api_catalog_through_gateway_api(self) -> None:
        login = self.post_api('auth.login', {'username': 'engineer'})
        self.assertTrue(login['ok'], login)

        sync = self.post_api('matrix.api.catalog.sync')
        self.assertFalse(sync['ok'])
        self.assertIn('Admin', sync['errors'][0])
