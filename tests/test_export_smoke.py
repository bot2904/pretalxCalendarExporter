from __future__ import annotations

from pathlib import Path

import requests
from icalendar import Calendar

import pretalx_star_exporter.exporter as exporter
from pretalx_star_exporter.exporter import ExportConfig


def _slot(
    *,
    start: str,
    end: str,
    code: str,
    title: str,
    room: str,
) -> dict[str, object]:
    return {
        "start": start,
        "end": end,
        "room": {"name": room},
        "submission": {
            "code": code,
            "title": title,
            "abstract": "Talk abstract",
            "state": "confirmed",
            "is_public": True,
            "speakers": [{"name": "Ada Lovelace"}],
        },
    }


def test_export_smoke_flow(tmp_path: Path, monkeypatch) -> None:
    output_path = tmp_path / "favourites.ics"

    config = ExportConfig(
        base_url="https://pretalx.example.org",
        event_slug="demo26",
        output_path=output_path,
        username="user@example.org",
        password="secret",
    )

    monkeypatch.setattr(
        exporter,
        "authenticate_session",
        lambda session, config, warnings: "credentials",
    )
    monkeypatch.setattr(exporter, "fetch_event_timezone", lambda session, config: "Europe/Vienna")
    monkeypatch.setattr(exporter, "fetch_current_schedule_id", lambda session, config: 42)
    monkeypatch.setattr(exporter, "fetch_favourites", lambda session, config: ["A1", "B2"])

    captured_schedule_ids: list[int | None] = []

    slots = {
        "A1": [
            _slot(
                start="2026-04-15T08:30:00+00:00",
                end="2026-04-15T09:00:00+00:00",
                code="A1",
                title="Opening Keynote",
                room="Main Hall",
            ),
            _slot(
                start="2026-04-16T08:30:00+00:00",
                end="2026-04-16T09:00:00+00:00",
                code="A1",
                title="Opening Keynote",
                room="Main Hall",
            ),
        ],
        "B2": [
            _slot(
                start="2026-04-15T10:00:00+00:00",
                end="2026-04-15T10:45:00+00:00",
                code="B2",
                title="Packaging with uv",
                room="Room 2",
            )
        ],
    }

    monkeypatch.setattr(
        exporter,
        "fetch_slots_for_submission",
        lambda session, config, submission_code, schedule_id=None: (
            captured_schedule_ids.append(schedule_id),
            slots[submission_code],
        )[1],
    )

    report = exporter.export_starred_sessions(config, session=requests.Session())

    assert report.output_path == output_path
    assert report.auth_method == "credentials"
    assert report.exported_submissions == 2
    assert report.exported_slots == 3
    assert report.warnings == []
    assert captured_schedule_ids == [42, 42]

    payload = output_path.read_bytes()
    parsed = Calendar.from_ical(payload)
    vevents = [component for component in parsed.walk() if component.name == "VEVENT"]
    assert len(vevents) == 3
