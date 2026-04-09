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


def test_build_calendar_uses_speaker_names_and_includes_description() -> None:
    slots_by_code = {
        "DEF456": [
            {
                "start": "2026-04-22T12:00:00+00:00",
                "end": "2026-04-22T13:00:00+00:00",
                "room": {"name": "Green Room"},
                "submission": {
                    "title": "Shipping Python Tools",
                    "abstract": "A short abstract.",
                    "description": "A longer talk description.",
                    "state": "confirmed",
                    "is_public": True,
                    "speakers": ["S1", "S2"],
                    "speaker_names": "Ada Lovelace, Grace Hopper",
                    "url": "https://pretalx.example.org/demo26/talk/def456/",
                },
            }
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
    assert len(vevents) == 1

    description = str(vevents[0].get("DESCRIPTION"))
    assert "Speakers: Ada Lovelace, Grace Hopper" in description
    assert "S1" not in description
    assert "S2" not in description
    assert "A short abstract." in description
    assert "A longer talk description." in description
    assert "Link: https://pretalx.example.org/demo26/talk/def456/" in description
    assert str(vevents[0].get("URL")) == "https://pretalx.example.org/demo26/talk/def456/"
