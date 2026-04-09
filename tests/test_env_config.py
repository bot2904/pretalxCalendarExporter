from __future__ import annotations

from pretalx_star_exporter.__main__ import load_env_overrides
from pretalx_star_exporter.exporter import merged_config


def test_load_env_overrides_maps_supported_variables() -> None:
    env = {
        "PRETALX_STARRED_EXPORT_BASE_URL": "https://pretalx.example.org",
        "PRETALX_STARRED_EXPORT_EVENT_SLUG": "demo26",
        "PRETALX_STARRED_EXPORT_OUTPUT_PATH": "/tmp/favourites.ics",
        "PRETALX_STARRED_EXPORT_USERNAME": "attendee@example.org",
        "PRETALX_STARRED_EXPORT_PASSWORD": "secret",
        "PRETALX_STARRED_EXPORT_FIREFOX_PROFILE": "/profiles/default",
        "PRETALX_STARRED_EXPORT_COOKIE_NAME": "pretalx_session",
    }

    assert load_env_overrides(env) == {
        "base_url": "https://pretalx.example.org",
        "event_slug": "demo26",
        "output_path": "/tmp/favourites.ics",
        "username": "attendee@example.org",
        "password": "secret",
        "firefox_profile": "/profiles/default",
        "cookie_name": "pretalx_session",
    }


def test_load_env_overrides_ignores_empty_values() -> None:
    env = {
        "PRETALX_STARRED_EXPORT_BASE_URL": "",
        "PRETALX_STARRED_EXPORT_EVENT_SLUG": "demo26",
    }

    assert load_env_overrides(env) == {
        "event_slug": "demo26",
    }


def test_env_values_override_file_and_cli_overrides_env() -> None:
    file_config = {
        "base_url": "https://from-file.example.org",
        "event_slug": "file-event",
        "output_path": "/tmp/from-file.ics",
        "username": "file-user",
    }
    env_overrides = load_env_overrides(
        {
            "PRETALX_STARRED_EXPORT_BASE_URL": "https://from-env.example.org",
            "PRETALX_STARRED_EXPORT_PASSWORD": "from-env-secret",
        }
    )
    cli_overrides = {
        "base_url": "https://from-cli.example.org",
        "event_slug": None,
        "output_path": None,
        "username": None,
        "password": None,
        "firefox_profile": None,
        "cookie_name": None,
    }

    merged = merged_config(merged_config(file_config, env_overrides), cli_overrides)

    assert merged["base_url"] == "https://from-cli.example.org"
    assert merged["password"] == "from-env-secret"
    assert merged["username"] == "file-user"
    assert merged["event_slug"] == "file-event"
