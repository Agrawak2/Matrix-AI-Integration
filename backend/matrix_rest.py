from __future__ import annotations

import json
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .matrix_config import MatrixProfile


class MatrixRestError(RuntimeError):
    pass


Transport = Callable[[str, dict[str, str]], str]


class MatrixRestClient:
    def __init__(
        self,
        profile: MatrixProfile,
        transport: Transport | None = None,
        timeout_seconds: int = 30,
    ):
        self.profile = profile
        self.transport = transport
        self.timeout_seconds = timeout_seconds

    def execute_mql(self, mql: str) -> str:
        transient_token = self.get_transient_token()
        service_ticket = self.authenticate_with_cas(transient_token)
        return self.execute_mql_with_ticket(mql, service_ticket)

    def get_transient_token(self) -> str:
        query = urlencode({"service": self.profile.space_url, "identifier": self.profile.identifier})
        body = self._get(
            f"{self.profile.passport_url}/api/v2/batch/ticket?{query}",
            {
                "DS-SERVICE-NAME": self.profile.service_name,
                "DS-SERVICE-SECRET": self.profile.service_secret,
                "Accept": "application/json",
            },
        )
        payload = _json_object(body, "transient token response")
        token = str(payload.get("access_token") or "").strip()
        if not token:
            raise MatrixRestError("Transient token response did not include access_token.")
        return token

    def authenticate_with_cas(self, transient_token: str) -> str:
        query = urlencode({"tgt": transient_token, "service": self.profile.space_url})
        body = self._get(
            f"{self.profile.passport_url}/api/login/cas/transient?{query}",
            {"Accept": "application/json"},
        )
        payload = _json_object(body, "CAS response")
        ticket = str(payload.get("access_token") or "").strip()
        if not ticket:
            raise MatrixRestError("CAS response did not include access_token.")
        return ticket

    def execute_mql_with_ticket(self, mql: str, ticket: str) -> str:
        query = urlencode({"query": mql, "ticket": ticket})
        headers = {"Accept": "application/json"}
        if self.profile.security_context:
            headers["SecurityContext"] = self.profile.security_context
        return self._get(
            f"{self.profile.space_url}/resources/IGT/v1/MQLService/executeMQL?{query}",
            headers,
        )

    def _get(self, url: str, headers: dict[str, str]) -> str:
        if self.transport:
            return self.transport(url, headers)

        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return response.read().decode("utf-8")
        except Exception as exc:
            raise MatrixRestError(f"Matrix REST request failed: {exc}") from exc


def _json_object(raw: str, label: str) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MatrixRestError(f"Matrix {label} was not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise MatrixRestError(f"Matrix {label} was not a JSON object.")
    return payload
