"""Local result archive.

FortyGuard results are deterministic for a given request, and identical
requests are charged again if resubmitted. Archiving completed results keyed by
(endpoint, request body) means a repeat request is served from disk for free.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def request_key(endpoint: str, body: dict) -> str:
    canonical = json.dumps(
        {"endpoint": endpoint, "body": body}, sort_keys=True, default=str
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ResultArchive:
    def __init__(self, data_dir: Path):
        self.results_dir = data_dir / "results"
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, endpoint: str, body: dict) -> Path:
        return self.results_dir / f"{request_key(endpoint, body)}.json"

    def get(self, endpoint: str, body: dict) -> dict | None:
        path = self._path(endpoint, body)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def put(self, endpoint: str, body: dict, result: dict) -> dict:
        record = {"endpoint": endpoint, "request": body, "result": result}
        self._path(endpoint, body).write_text(
            json.dumps(record, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        return record
