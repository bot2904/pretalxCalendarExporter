from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping
from pathlib import Path

from .exporter import (
    ConfigurationError,
    build_export_config,
    export_starred_sessions,
    load_yaml_config,
    merged_config,
)


DEFAULT_CONFIG_PATH = Path("/workspace/.config.yml")


ENV_VAR_MAP = {
    "base_url": "PRETALX_STARRED_EXPORT_BASE_URL",
    "event_slug": "PRETALX_STARRED_EXPORT_EVENT_SLUG",
    "output_path": "PRETALX_STARRED_EXPORT_OUTPUT_PATH",
    "username": "PRETALX_STARRED_EXPORT_USERNAME",
    "password": "PRETALX_STARRED_EXPORT_PASSWORD",
    "firefox_profile": "PRETALX_STARRED_EXPORT_FIREFOX_PROFILE",
    "cookie_name": "PRETALX_STARRED_EXPORT_COOKIE_NAME",
}


def load_env_overrides(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    source = os.environ if environ is None else environ
    overrides: dict[str, str] = {}

    for config_key, env_var in ENV_VAR_MAP.items():
        value = source.get(env_var)
        if value is None or value == "":
            continue
        overrides[config_key] = value

    return overrides


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export pretalx starred sessions to an ICS file",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to YAML config file (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--base-url",
        help=(
            "Pretalx base URL, e.g. https://pretalx.example.org "
            "(env: PRETALX_STARRED_EXPORT_BASE_URL)"
        ),
    )
    parser.add_argument(
        "--event-slug",
        help="Event slug, e.g. glt26 (env: PRETALX_STARRED_EXPORT_EVENT_SLUG)",
    )
    parser.add_argument(
        "--output-path",
        help=(
            "Where to write the generated ICS file "
            "(env: PRETALX_STARRED_EXPORT_OUTPUT_PATH)"
        ),
    )
    parser.add_argument(
        "--username",
        help=(
            "Pretalx username/email for web login "
            "(env: PRETALX_STARRED_EXPORT_USERNAME)"
        ),
    )
    parser.add_argument(
        "--password",
        help="Pretalx password for web login (env: PRETALX_STARRED_EXPORT_PASSWORD)",
    )
    parser.add_argument(
        "--firefox-profile",
        help=(
            "Firefox profile path containing cookies.sqlite (optional fallback) "
            "(env: PRETALX_STARRED_EXPORT_FIREFOX_PROFILE)"
        ),
    )
    parser.add_argument(
        "--cookie-name",
        default=None,
        help=(
            "Session cookie name (default: pretalx_session) "
            "(env: PRETALX_STARRED_EXPORT_COOKIE_NAME)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        file_config = load_yaml_config(args.config)
        env_overrides = load_env_overrides()
        cli_overrides = {
            "base_url": args.base_url,
            "event_slug": args.event_slug,
            "output_path": args.output_path,
            "username": args.username,
            "password": args.password,
            "firefox_profile": args.firefox_profile,
            "cookie_name": args.cookie_name,
        }
        config = build_export_config(
            merged_config(
                merged_config(file_config, env_overrides),
                cli_overrides,
            )
        )
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    try:
        report = export_starred_sessions(config)
    except Exception as exc:  # noqa: BLE001
        print(f"Export failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"Export complete: {report.exported_submissions} submissions, "
        f"{report.exported_slots} slots -> {report.output_path}"
    )
    print(f"Authentication: {report.auth_method}")

    for warning in report.warnings:
        print(f"Warning: {warning}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
