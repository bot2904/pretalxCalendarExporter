from __future__ import annotations

from icalendar import Calendar

from pretalx_star_exporter.exporter import build_calendar


def test_build_calendar_multi_slot_series_and_cancelled_prefix() -> None:
    slots_by_code = {
        "ABC123": [
            {
                "start": "2026-04-20T09:00:00+00:00",
                "end": "2026-04-20T10:00:00+00:00",
                "room": {"name": "Blue Room"},
                "submission": {
                    "title": "Kernel Deep Dive",
                    "abstract": "All about internals.",
                    "state": "canceled",
                    "is_public": False,
                    "speakers": [{"name": "Lin"}],
                },
            },
            {
                "start": "2026-04-21T09:00:00+00:00",
                "end": "2026-04-21T10:00:00+00:00",
                "room": {"name": "Blue Room"},
                "submission": {
                    "title": "Kernel Deep Dive",
                    "abstract": "All about internals.",
                    "state": "canceled",
                    "is_public": False,
                    "speakers": [{"name": "Lin"}],
                },
            },
        ]
    }

    calendar = build_calendar(
        base_url="https://pretalx.example.org",
        event_slug="demo26",
        timezone_name="Europe/Vienna",
        slots_by_code=slots_by_code,
    )

    parsed = Calendar.from_ical(calendar.to_ical())
    vevents = [component for component in parsed.walk() if component.name == "VEVENT"]
    assert len(vevents) == 2

    uids = {str(event.get("UID")) for event in vevents}
    assert len(uids) == 1

    master = next(event for event in vevents if event.get("RECURRENCE-ID") is None)
    override = next(event for event in vevents if event.get("RECURRENCE-ID") is not None)

    assert master.get("RDATE") is not None
    assert override.get("RECURRENCE-ID") is not None
    assert str(master.get("SUMMARY")).startswith("CANCELLED: ")
    assert str(master.get("STATUS")) == "CANCELLED"
