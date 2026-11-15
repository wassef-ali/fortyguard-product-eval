"""Thin HTTP client for the FortyGuard Temperature API.

Covers the submit-then-poll async pattern and the account-usage endpoint.
The API key travels only as an `api-key` header (plus, for the usage endpoint,
in the request body, which is that endpoint's documented requirement).
"""

from __future__ import annotations

import time
from typing import Any

import requests

from .config import (
    ENV_PARAMS_PATH,
    FORTYGUARD_BASE_URL,
    HEATMAP_PATH,
    STATUS_PATH,
    USAGE_PATH,
)


class FortyGuardError(RuntimeError):
    """A non-2xx / non-JSON / error-flagged response from the API."""


class FortyGuardClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = FORTYGUARD_BASE_URL,
        timeout: float = 60.0,
    ):
        if not api_key or not api_key.strip():
            raise ValueError("FORTYGUARD_API_KEY is missing. Add it to your .env file.")
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )

    # -- primitives --------------------------------------------------------- #

    def _request(self, method: str, path: str, json_body: Any = None) -> dict:
        url = f"{self.base_url}{path}"
        response = self.session.request(method, url, json=json_body, timeout=self.timeout)
        try:
            body = response.json()
        except ValueError as exc:
            raise FortyGuardError(
                f"Non-JSON HTTP {response.status_code}: {response.text[:300]}"
            ) from exc
        if not isinstance(body, dict):
            raise FortyGuardError(f"Unexpected response type: {type(body).__name__}")
        if response.status_code >= 400 or body.get("error") is True:
            raise FortyGuardError(f"API error (HTTP {response.status_code}): {body}")
        return body

    @staticmethod
    def _activity_id(body: dict) -> str:
        data = body.get("data") or {}
        activity_id = data.get("activity_id")
        if not activity_id:
            raise FortyGuardError(f"Submit returned no data.activity_id: {body}")
        return str(activity_id)

    # -- endpoints ---------------------------------------------------------- #

    def usage(self) -> dict:
        """Account plan, credits and per-endpoint breakdown.

        This endpoint needs the key in the BODY as `api_key` as well as the
        header every other endpoint accepts alone.
        """
        return self._request("POST", USAGE_PATH, {"api_key": self.api_key})

    def submit_heatmap(
        self,
        polygon_aoi: dict,
        start_date: str,
        granularity: int = 80,
        filter_type: int = 3,
        start_time: str | None = None,
        end_date: str | None = None,
        analytic_type: str | None = None,
    ) -> str:
        """Submit a heatmap and return its activity_id (does not wait)."""
        date_time: dict[str, Any] = {"start_date": start_date, "filter_type": filter_type}
        if start_time:
            date_time["start_time"] = start_time
        if end_date:
            date_time["end_date"] = end_date
        payload: dict[str, Any] = {
            "polygon_aoi": polygon_aoi,
            "date_time": date_time,
            "granularity": granularity,
        }
        if analytic_type:
            payload["analytic_type"] = analytic_type
        return self._activity_id(self._request("POST", HEATMAP_PATH, payload))

    def submit_env_params(
        self,
        latitude: float,
        longitude: float,
        temperature: float,
        date_time: dict,
        analysis: list[str] | None = None,
    ) -> str:
        """Submit an env_params request and return its activity_id."""
        payload: dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "temperature": temperature,
            "date_time": date_time,
        }
        if analysis:
            payload["analysis"] = analysis
        return self._activity_id(self._request("POST", ENV_PARAMS_PATH, payload))

    def status(self, activity_id: str) -> dict:
        return self._request("GET", STATUS_PATH.format(activity_id=activity_id))

    def wait_for_result(
        self,
        activity_id: str,
        timeout: float = 600.0,
        poll_interval: float = 5.0,
        backoff: float = 1.5,
    ) -> dict:
        """Poll until the activity completes, then return the full status body.

        Completion is detected structurally (data.result is present), not by
        string-matching a status. An unrecognised status keeps polling until
        the timeout; a failed status raises.
        """
        deadline = time.monotonic() + timeout
        delay = poll_interval
        last_status = "unknown"
        while time.monotonic() < deadline:
            time.sleep(delay)
            delay = min(delay * backoff, 15.0)
            body = self.status(activity_id)
            data = body.get("data") or {}
            status = data.get("status") or body.get("status") or "unknown"
            last_status = str(status)
            if isinstance(data.get("result"), dict):
                return body
            if last_status.lower() in ("failed", "error", "cancelled"):
                raise FortyGuardError(
                    f"Activity {activity_id} ended as {last_status}: {body}"
                )
        raise TimeoutError(
            f"Timed out waiting for activity {activity_id}; last status={last_status}"
        )
