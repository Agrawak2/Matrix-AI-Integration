from __future__ import annotations

import json
from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from .services import call_matrix_service


JsonObject = dict[str, Any]


@require_GET
def index(request: HttpRequest) -> HttpResponse:
    return render(request, 'gateway/index.html')


@require_GET
def health(request: HttpRequest) -> JsonResponse:
    return JsonResponse({'ok': True, 'service': 'django-gateway'})


@require_POST
def api(request: HttpRequest) -> JsonResponse:
    try:
        envelope = _normalize_envelope(request, _read_json_object(request))
    except ValueError as exc:
        return JsonResponse(
            {'ok': False, 'data': None, 'errors': [str(exc)], 'audit_id': None},
            status=400,
        )

    response = call_matrix_service(envelope)
    _sync_django_session(request, envelope, response)
    return JsonResponse(response, status=200 if response.get('ok') else 400)


def _read_json_object(request: HttpRequest) -> JsonObject:
    raw_body = request.body.decode('utf-8').strip()
    if not raw_body:
        return {key: value for key, value in request.POST.items()}

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise ValueError(f'Invalid JSON: {exc}') from exc

    if not isinstance(payload, dict):
        raise ValueError('Request body must be a JSON object.')
    return payload


def _normalize_envelope(request: HttpRequest, envelope: JsonObject) -> JsonObject:
    normalized = dict(envelope)
    payload = normalized.get('payload')
    if not isinstance(payload, dict):
        normalized['payload'] = {}

    if not normalized.get('session_id'):
        session_id = request.session.get('matrix_ai_session_id')
        if isinstance(session_id, str) and session_id:
            normalized['session_id'] = session_id

    return normalized


def _sync_django_session(request: HttpRequest, envelope: JsonObject, response: JsonObject) -> None:
    action = envelope.get('action')
    if action == 'auth.login' and response.get('ok'):
        session_id = response.get('data', {}).get('session_id')
        if isinstance(session_id, str) and session_id:
            request.session['matrix_ai_session_id'] = session_id

    if action == 'auth.logout':
        request.session.pop('matrix_ai_session_id', None)
