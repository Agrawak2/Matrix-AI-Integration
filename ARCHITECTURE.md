# Matrix AI Integration Architecture

This project uses a Python-first architecture so the workflow logic, web layer, tests, and Matrix integration can live in one language.

## Current Shape

The application has four main layers:

1. Browser UI in `gateway/templates/gateway/index.html` and `gateway/static/gateway/`.
2. Django routes/views in `gateway/urls.py` and `gateway/views.py`.
3. A thin service adapter in `gateway/services.py`.
4. Workflow, permission, approval, audit, mock Matrix, and Matrix REST logic in `backend/`.

The important request flow is:

```text
Browser -> Django URL -> gateway view -> gateway service adapter -> backend service -> storage/workflows -> JSON response
```

## What Django Owns

Django is responsible for normal web application concerns:

- Routing.
- Rendering the main page.
- CSRF protection for browser POST requests.
- Cookie-backed browser session handling.
- Future real user authentication, admin screens, and authorization middleware.

The Django API delegates business decisions to `backend.service.handle()`. That keeps web concerns in Django and domain behavior in plain Python services.

## What The Backend Owns

The `backend/` package owns domain behavior:

- Action envelope validation and dispatch.
- Mock user/session lookup for the current prototype.
- Role checks.
- Matrix action permission policy.
- ECO and part readiness workflows.
- Approval execution.
- Audit event creation.
- SQLite persistence for Matrix AI data.
- Read-only Matrix REST connector support.

When you are trying to understand a workflow bug, start in `backend/app.py`, then follow the action into `backend/workflows.py`, `backend/approvals.py`, or `backend/permissions.py`.

## Python Learning Guardrails

This codebase should be readable for someone learning Python. New code should follow these rules:

- Use type hints everywhere practical, especially function arguments and return values.
- Keep views/controllers thin. They should parse the request, call a service, and return a response.
- Keep business rules in plain Python services, not templates or framework hooks.
- Prefer explicit helper functions over clever one-liners.
- Use names that explain the domain: `workflow_run`, `proposed_action`, `action_key`.
- Add tests before or alongside behavior changes.
- Treat tests as executable examples of how a feature works.
- Add short comments only where the code is not obvious from names and structure.
- Avoid framework magic until the simpler Python version becomes painful.

## Near-Term Plan

1. Keep Django as the only web shell and JSON gateway.
2. Replace mock login/session handling with Django auth.
3. Move action policies, audit history, and workflow runs into Django admin views or typed Django models.
4. Continue keeping business rules in plain, typed Python services.

## Debugging Map

- Page does not load: check `matrix_ai_site/urls.py`, `gateway/urls.py`, and `gateway/views.py`.
- API call fails before reaching business logic: check `gateway/views.py`.
- API call reaches Python but returns a domain error: check `backend/app.py`.
- ECO or part analysis is wrong: check `backend/workflows.py`.
- Permissions are wrong: check `backend/permissions.py` and seeded actions in `backend/database.py`.
- Stored data looks wrong: check `backend/storage.py`.
