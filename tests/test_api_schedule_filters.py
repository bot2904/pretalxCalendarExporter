from __future__ import annotations

from pathlib import Path
from typing import Any

from pretalx_star_exporter.exporter import (
    ExportConfig,
    fetch_current_schedule_id,
    fetch_slots_for_submission,
)


class _FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        return self._payload


class _FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    def get(self, url: str, params: dict[str, Any] | None = None, timeout: int = 30) -> _FakeResponse:  # noqa: ARG002
        self.calls.append((url, params))

        if url.endswith("/schedules/"):
            return _FakeResponse(
                {
                    "count": 3,
                    "next": None,
                    "previous": None,
                    "results": [
                        {"id": 153, "version": "0.1"},
                        {"id": 170, "version": "0.2"},
                        {"id": 161, "version": "0.15"},
                    ],
                }
            )

        if url.endswith("/slots/"):
            return _FakeResponse(
                {
                    "count": 1,
                    "next": None,
                    "previous": None,
                    "results": [
                        {
                            "id": 1,
                            "schedule": 170,
                            "start": "2026-04-11T09:00:00+02:00",
                            "end": "2026-04-11T09:45:00+02:00",
                            "submission": {"title": "Talk"},
                        }
                    ],
                }
            )

        return _FakeResponse({}, status_code=404)


def _config() -> ExportConfig:
    return ExportConfig(
        base_url="https://pretalx.example.org",
        event_slug="demo26",
        output_path=Path("/tmp/favs.ics"),
    )


def test_fetch_current_schedule_id_uses_latest_id() -> None:
    session = _FakeSession()

    schedule_id = fetch_current_schedule_id(session, _config())

    assert schedule_id == 170


def test_fetch_slots_for_submission_includes_schedule_filter() -> None:
    session = _FakeSession()

    slots = fetch_slots_for_submission(
        session,
        _config(),
        "ABC123",
        schedule_id=170,
    )

    assert len(slots) == 1
    _, params = session.calls[-1]
    assert params is not None
    assert params["submission"] == "ABC123"
    assert params["schedule"] == 170
    assert params["expand"] == "submission,submission.speakers,room"
