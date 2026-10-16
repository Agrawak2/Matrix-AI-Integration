# Matrix AI Integration Local Dev Environment

This workspace is set up to build and test a Python-backed ENOVIA / Matrix AI gateway with a Django web front end without requiring local admin privileges.

## What Is Installed Locally

- Python virtual environment: `.venv`
- Django web shell: `matrix_ai_site`, `gateway`, `manage.py`
- Python backend logic, workflows, permissions, mock Matrix connector, and SQLite repositories: `backend`
- Tests and smoke checks: `tests`, `scripts/test.ps1`

## Run Tests

```powershell
.\scripts\test.cmd
```

The test script runs Python unit tests, Django checks, and Django gateway tests.

## Start The Web App

```powershell
.\scripts\dev.cmd
```

Then open:

```text
http://127.0.0.1:8000
```

If you started the server in the foreground, press `Ctrl+C` to stop it. If it is running in the background, stop it with:

```powershell
.\scripts\stop-dev.cmd
```

## Quick Django API Test

With the Django server running, run a part-number search against the `/api/` envelope endpoint:

```powershell
.\scripts\test-django-part-search.cmd PCB
```

The script logs in as the mock `engineer` user, calls `matrix.part.search`, and prints the returned matches. You can pass a different part-number fragment as the first argument.
Add `-UseMatrixServer` to call the configured Matrix REST read connector instead of mock data.

## Matrix REST Read Setup

Create ignored local Matrix REST config files from the REST ticket notes:

```powershell
.\scripts\setup-matrix-rest-config.cmd
```

Then run a read-only Matrix part search through the same backend action used by the web GUI:

```powershell
.\scripts\test-matrix-rest-config.cmd PCB
```

In the Django UI, use the Part Search tab and check `Matrix server` to exercise the live Matrix path.

## Runtime Commands

Check local runtime versions:

```powershell
.\scripts\env.cmd
```

Install future Python packages into the local virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install package-name
```

No global PATH changes or administrator installs are required.

The `.cmd` wrappers run the PowerShell helpers with a per-command execution policy bypass. They do not change the system-wide PowerShell policy.

## Mock Users

- `engineer` / Engineer: runs ECO and part readiness workflows
- `approver` / Approver: approves or rejects proposed Matrix actions
- `admin` / Admin: toggles Matrix action permissions

## Architecture Notes

AI does not call ENOVIA / Matrix directly. The Django gateway sends action envelopes to the Python backend, and Python enforces action registry permissions before using either mock Matrix data or the configured Matrix REST read connector. V1 uses SQLite under `data/`; the repository layer keeps the persistence boundary narrow for a later MySQL or MariaDB move.

The Django architecture is documented in `ARCHITECTURE.md`. The web shell and backend are now Python-first so the project can be easier to understand, test, and extend while learning Python.

Deployment notes for the RHEL 9 server `RNOAPPHEN01D` are documented in `DEPLOYMENT.md`.

## API Envelope

Browser and helper-script calls use the same envelope:

```json
{
  "action": "workflow.eco.analyze",
  "session_id": "mock-session-id",
  "payload": {}
}
```

The Python backend responds with:

```json
{
  "ok": true,
  "data": {},
  "errors": [],
  "audit_id": 1
}
```

Core actions include `auth.login`, `permissions.list`, `permissions.update`, `workflow.eco.analyze`, `workflow.part.analyze`, `approval.action.approve`, `approval.action.reject`, `approval.actions.approve_all_eligible`, and `audit.workflow.history`.

## New Part Number Planner

The **New Part Number** tab turns a request such as “Let's pull a P/N for a new Bracket...” into a staged creation summary. The backend action `workflow.part_number.plan` selects a configured family, combines occupied six-digit sequences from Matrix and SAP/legacy sources, proposes the next candidate, and stages Matrix part/BOM actions for review.

SAP material search is available through `sap.material.search`. It uses mock data by default or a cached SAP AO workbook when `SAP_PART_SEARCH_WORKBOOK` is set. Snapshot results are not treated as production-safe; a live SAP adapter and final transactional recheck are still required. The reverse engineering and production handoff are documented in `docs/PART_NUMBER_INTEGRATION.md`.
