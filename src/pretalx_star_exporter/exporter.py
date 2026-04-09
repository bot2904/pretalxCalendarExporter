from __future__ import annotations

import configparser
import html.parser
import re
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

import requests
import yaml
from icalendar import Calendar, Event
from zoneinfo import ZoneInfo


class ExporterError(RuntimeError):
    """Base class for exporter errors."""


class AuthenticationError(ExporterError):
    """Raised when the exporter cannot authenticate."""


class ConfigurationError(ExporterError):
    """Raised when configuration is incomplete or invalid."""


@dataclass(slots=True)
class ExportConfig:
    base_url: str
    event_slug: str
    output_path: Path
    username: str | None = None
    password: str | None = None
    firefox_profile: Path | None = None
    cookie_name: str = "pretalx_session"


@dataclass(slots=True)
class ExportReport:
    output_path: Path
    exported_submissions: int
    exported_slots: int
    auth_method: str
    warnings: list[str] = field(default_factory=list)


def load_yaml_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    if content is None:
        return {}
    if not isinstance(content, dict):
        raise ConfigurationError(f"Config file must contain a mapping: {path}")
    return content


def merged_config(file_config: dict[str, Any], cli_overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(file_config)
    for key, value in cli_overrides.items():
        if value is not None:
            merged[key] = value
    return merged


def build_export_config(raw: dict[str, Any]) -> ExportConfig:
    missing = [
        key
        for key in ("base_url", "event_slug", "output_path")
        if not raw.get(key)
    ]
    if missing:
        missing_str = ", ".join(missing)
        raise ConfigurationError(f"Missing required configuration value(s): {missing_str}")

    base_url = str(raw["base_url"]).rstrip("/")
    event_slug = str(raw["event_slug"]).strip("/")
    output_path = Path(str(raw["output_path"])).expanduser()

    firefox_profile_value = raw.get("firefox_profile")
    firefox_profile = (
        Path(str(firefox_profile_value)).expanduser()
        if firefox_profile_value
        else None
    )

    return ExportConfig(
        base_url=base_url,
        event_slug=event_slug,
        output_path=output_path,
        username=raw.get("username"),
        password=raw.get("password"),
        firefox_profile=firefox_profile,
        cookie_name=str(raw.get("cookie_name") or "pretalx_session"),
    )


def export_starred_sessions(
    config: ExportConfig,
    session: requests.Session | None = None,
) -> ExportReport:
    warnings: list[str] = []
    client = session or requests.Session()

    auth_method = authenticate_session(client, config, warnings)

    timezone_name = "UTC"
    try:
        timezone_name = fetch_event_timezone(client, config)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Could not fetch event timezone, falling back to UTC: {exc}")

    current_schedule_id: int | None = None
    try:
        current_schedule_id = fetch_current_schedule_id(client, config)
    except Exception as exc:  # noqa: BLE001
        warnings.append(
            "Could not fetch current schedule version; "
            f"slot results may include historical revisions: {exc}"
        )

    favourites = fetch_favourites(client, config)
    slots_by_code: dict[str, list[dict[str, Any]]] = {}

    for code in favourites:
        try:
            slots = fetch_slots_for_submission(
                client,
                config,
                code,
                schedule_id=current_schedule_id,
            )
            if slots:
                slots_by_code[code] = slots
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Could not fetch slots for {code}: {exc}")

    calendar = build_calendar(
        base_url=config.base_url,
        event_slug=config.event_slug,
        timezone_name=timezone_name,
        slots_by_code=slots_by_code,
    )

    write_validated_calendar(calendar, config.output_path)

    return ExportReport(
        output_path=config.output_path,
        exported_submissions=len(slots_by_code),
        exported_slots=sum(len(slots) for slots in slots_by_code.values()),
        auth_method=auth_method,
        warnings=warnings,
    )


def authenticate_session(
    session: requests.Session,
    config: ExportConfig,
    warnings: list[str],
) -> str:
    if config.username and config.password:
        try:
            login_with_credentials(
                session=session,
                base_url=config.base_url,
                event_slug=config.event_slug,
                username=config.username,
                password=config.password,
                cookie_name=config.cookie_name,
            )
            return "credentials"
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Credential login failed, trying Firefox cookies: {exc}")

    try:
        profile = config.firefox_profile or auto_detect_firefox_profile()
        apply_firefox_cookie_auth(
            session=session,
            base_url=config.base_url,
            profile_path=profile,
            cookie_name=config.cookie_name,
        )
        return "firefox"
    except Exception as exc:  # noqa: BLE001
        raise AuthenticationError(
            "Failed to authenticate using credentials and Firefox cookie fallback."
        ) from exc


def login_with_credentials(
    session: requests.Session,
    base_url: str,
    event_slug: str,
    username: str,
    password: str,
    cookie_name: str,
) -> None:
    errors: list[str] = []

    for login_url in _login_url_candidates(base_url, event_slug):
        try:
            _login_with_credentials_at_url(
                session=session,
                login_url=login_url,
                username=username,
                password=password,
                cookie_name=cookie_name,
            )
            return
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{login_url}: {exc}")

    details = "; ".join(errors)
    raise AuthenticationError(f"Credential login failed: {details}")


def _login_url_candidates(base_url: str, event_slug: str) -> list[str]:
    candidates: list[str] = []
    normalized_slug = event_slug.strip("/")

    if normalized_slug:
        event_login_url = urljoin(f"{base_url}/", f"{normalized_slug}/login/")
        next_target = f"/{normalized_slug}/schedule/"
        candidates.append(f"{event_login_url}?{urlencode({'next': next_target})}")
        candidates.append(event_login_url)

    candidates.append(urljoin(f"{base_url}/", "orga/login/"))

    # Keep insertion order but avoid duplicate URLs.
    return list(dict.fromkeys(candidates))


def _login_with_credentials_at_url(
    session: requests.Session,
    login_url: str,
    username: str,
    password: str,
    cookie_name: str,
) -> None:
    response = session.get(login_url, timeout=30)
    response.raise_for_status()

    csrf_token = _find_csrf_cookie(session.cookies) or extract_csrf_token(response.text)
    if not csrf_token:
        raise AuthenticationError("Could not extract CSRF token from login page")

    response = session.post(
        login_url,
        data={
            # Different pretalx versions/form variants use different field names.
            "login_email": username,
            "login_password": password,
            "login": username,
            "password": password,
            "csrfmiddlewaretoken": csrf_token,
        },
        headers={"Referer": login_url},
        timeout=30,
        allow_redirects=True,
    )
    response.raise_for_status()

    if not session.cookies.get(cookie_name):
        raise AuthenticationError("Login did not create a pretalx session cookie")


def _find_csrf_cookie(cookie_jar: requests.cookies.RequestsCookieJar) -> str | None:
    for cookie_name in ("pretalx_csrftoken", "csrftoken"):
        token = cookie_jar.get(cookie_name)
        if token:
            return str(token)

    for cookie in cookie_jar:
        if cookie.name.lower().endswith("csrftoken") and cookie.value:
            return str(cookie.value)

    return None


def extract_csrf_token(html: str) -> str | None:
    parser = _InputValueParser(input_name="csrfmiddlewaretoken")
    parser.feed(html)
    parser.close()

    if parser.found_value:
        return parser.found_value

    # Fallback regex for malformed/minified markup.
    match = re.search(
        r"\bname=(?:[\"'])?csrfmiddlewaretoken(?:[\"'])?[^>]*\bvalue=(?:[\"'])?([^\"'\s>]+)",
        html,
    )
    if match:
        return match.group(1)

    match = re.search(
        r"\bvalue=(?:[\"'])?([^\"'\s>]+)(?:[\"'])?[^>]*\bname=(?:[\"'])?csrfmiddlewaretoken(?:[\"'])?",
        html,
    )
    return match.group(1) if match else None


class _InputValueParser(html.parser.HTMLParser):
    def __init__(self, input_name: str):
        super().__init__()
        self._input_name = input_name
        self.found_value: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.found_value or tag.lower() != "input":
            return

        attr_map = {name: value for name, value in attrs if name}
        if attr_map.get("name") != self._input_name:
            return

        value = attr_map.get("value")
        if value:
            self.found_value = value


def auto_detect_firefox_profile() -> Path:
    profiles_ini = Path.home() / ".mozilla" / "firefox" / "profiles.ini"
    if not profiles_ini.exists():
        raise AuthenticationError("Firefox profiles.ini not found")

    parser = configparser.ConfigParser()
    parser.read(profiles_ini, encoding="utf-8")

    candidates: list[Path] = []
    for section in parser.sections():
        if not section.startswith("Profile"):
            continue
        path = parser.get(section, "Path", fallback="")
        if not path:
            continue
        is_relative = parser.getboolean(section, "IsRelative", fallback=True)
        profile_path = profiles_ini.parent / path if is_relative else Path(path)
        if parser.getboolean(section, "Default", fallback=False):
            return profile_path
        candidates.append(profile_path)

    if candidates:
        return candidates[0]

    raise AuthenticationError("No Firefox profile found")


def apply_firefox_cookie_auth(
    session: requests.Session,
    base_url: str,
    profile_path: Path,
    cookie_name: str,
) -> None:
    cookie_value, cookie_domain, cookie_path, secure = read_firefox_cookie(
        base_url=base_url,
        profile_path=profile_path,
        cookie_name=cookie_name,
    )

    session.cookies.set(
        cookie_name,
        cookie_value,
        domain=cookie_domain,
        path=cookie_path,
        secure=secure,
    )


def read_firefox_cookie(
    base_url: str,
    profile_path: Path,
    cookie_name: str,
) -> tuple[str, str, str, bool]:
    db_path = profile_path / "cookies.sqlite"
    if not db_path.exists():
        raise AuthenticationError(f"Firefox cookies database not found: {db_path}")

    hostname = (urlparse(base_url).hostname or "").lower()
    if not hostname:
        raise AuthenticationError("Could not derive host from base_url")

    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=True) as temp_db:
        temp_db.write(db_path.read_bytes())
        temp_db.flush()

        connection = sqlite3.connect(temp_db.name)
        try:
            cursor = connection.cursor()
            cursor.execute(
                """
                SELECT host, path, value, isSecure, expiry
                FROM moz_cookies
                WHERE name = ?
                ORDER BY expiry DESC
                """,
                (cookie_name,),
            )
            rows = cursor.fetchall()
        finally:
            connection.close()

    for host, path, value, is_secure, _expiry in rows:
        normalized_host = host.lstrip(".").lower()
        if hostname == normalized_host or hostname.endswith(f".{normalized_host}"):
            return value, host, path or "/", bool(is_secure)

    raise AuthenticationError(
        f"Cookie '{cookie_name}' for host '{hostname}' not found in Firefox profile"
    )


def fetch_event_timezone(session: requests.Session, config: ExportConfig) -> str:
    endpoint = urljoin(
        f"{config.base_url}/", f"api/events/{config.event_slug}/"
    )
    response = session.get(endpoint, timeout=30)
    response.raise_for_status()
    payload = response.json()

    if isinstance(payload, dict) and payload.get("timezone"):
        return str(payload["timezone"])

    return "UTC"


def fetch_current_schedule_id(
    session: requests.Session,
    config: ExportConfig,
) -> int | None:
    endpoint = urljoin(
        f"{config.base_url}/",
        f"api/events/{config.event_slug}/schedules/",
    )

    schedule_ids: list[int] = []
    for item in iter_paginated(session, endpoint):
        if not isinstance(item, dict):
            continue
        schedule_id = item.get("id")
        if isinstance(schedule_id, int):
            schedule_ids.append(schedule_id)

    if not schedule_ids:
        return None

    return max(schedule_ids)


def fetch_favourites(session: requests.Session, config: ExportConfig) -> list[str]:
    endpoint = urljoin(
        f"{config.base_url}/",
        f"api/events/{config.event_slug}/submissions/favourites/",
    )

    favourites: list[str] = []
    for item in iter_paginated(session, endpoint):
        if isinstance(item, str):
            favourites.append(item)
            continue
        if isinstance(item, dict):
            code = item.get("code")
            if code:
                favourites.append(str(code))

    seen: set[str] = set()
    deduplicated: list[str] = []
    for code in favourites:
        if code in seen:
            continue
        seen.add(code)
        deduplicated.append(code)

    return deduplicated


def fetch_slots_for_submission(
    session: requests.Session,
    config: ExportConfig,
    submission_code: str,
    schedule_id: int | None = None,
) -> list[dict[str, Any]]:
    endpoint = urljoin(f"{config.base_url}/", f"api/events/{config.event_slug}/slots/")
    params = {
        "submission": submission_code,
        "expand": "submission,submission.speakers,room",
    }
    if schedule_id is not None:
        params["schedule"] = schedule_id

    slots: list[dict[str, Any]] = []
    for item in iter_paginated(session, endpoint, params=params):
        if isinstance(item, dict):
            slots.append(item)

    return slots


def iter_paginated(
    session: requests.Session,
    endpoint: str,
    params: dict[str, Any] | None = None,
):
    next_url: str | None = endpoint
    next_params = params

    while next_url:
        response = session.get(next_url, params=next_params, timeout=30)
        response.raise_for_status()
        payload = response.json()

        if isinstance(payload, list):
            for item in payload:
                yield item
            return

        if isinstance(payload, dict) and "results" in payload:
            results = payload.get("results") or []
            if not isinstance(results, list):
                raise ExporterError(f"Expected list in paginated response: {next_url}")

            for item in results:
                yield item

            next_link = payload.get("next")
            next_url = urljoin(next_url, next_link) if next_link else None
            next_params = None
            continue

        raise ExporterError(f"Unexpected response shape for {next_url}")


def build_calendar(
    base_url: str,
    event_slug: str,
    timezone_name: str,
    slots_by_code: dict[str, list[dict[str, Any]]],
) -> Calendar:
    try:
        timezone = ZoneInfo(timezone_name)
    except Exception:  # noqa: BLE001
        timezone = ZoneInfo("UTC")
        timezone_name = "UTC"

    calendar = Calendar()
    calendar.add("prodid", "-//pretalx-starred-exporter//EN")
    calendar.add("version", "2.0")
    calendar.add("calscale", "GREGORIAN")
    calendar.add("x-wr-calname", f"pretalx favourites ({event_slug})")
    calendar.add("x-wr-timezone", timezone_name)

    host = urlparse(base_url).hostname or "pretalx.local"
    now = datetime.now(tz=UTC)

    for code in sorted(slots_by_code.keys()):
        normalized_slots = _normalized_slots(slots_by_code[code], timezone)
        if not normalized_slots:
            continue

        uid = f"{code}@{host}"
        first_slot, first_start, first_end = normalized_slots[0]

        master = Event()
        master.add("uid", uid)
        master.add("dtstamp", now)
        master.add("dtstart", first_start)
        master.add("dtend", first_end)
        _apply_slot_metadata(master, code, first_slot)

        if len(normalized_slots) > 1:
            for _slot, start, _end in normalized_slots[1:]:
                master.add("rdate", start)

        calendar.add_component(master)

        for slot, start, end in normalized_slots[1:]:
            override = Event()
            override.add("uid", uid)
            override.add("dtstamp", now)
            override.add("recurrence-id", start)
            override.add("dtstart", start)
            override.add("dtend", end)
            _apply_slot_metadata(override, code, slot)
            calendar.add_component(override)

    return calendar


def _normalized_slots(
    slots: list[dict[str, Any]], timezone: ZoneInfo
) -> list[tuple[dict[str, Any], datetime, datetime]]:
    normalized: list[tuple[dict[str, Any], datetime, datetime]] = []

    for slot in slots:
        start_raw = slot.get("start")
        end_raw = slot.get("end")
        if not start_raw or not end_raw:
            continue

        start = _parse_datetime(start_raw, timezone)
        end = _parse_datetime(end_raw, timezone)
        normalized.append((slot, start, end))

    normalized.sort(key=lambda item: item[1])
    return normalized


def _apply_slot_metadata(event: Event, code: str, slot: dict[str, Any]) -> None:
    submission = slot.get("submission") if isinstance(slot.get("submission"), dict) else {}

    title = _text_value(submission.get("title")) or f"Submission {code}"
    if _is_cancelled_or_hidden(submission, slot):
        title = f"CANCELLED: {title}"
        event.add("status", "CANCELLED")

    speakers = _speaker_list(submission)
    abstract = _text_value(submission.get("abstract"))
    talk_description = _text_value(submission.get("description"))

    description_parts = []
    if speakers:
        description_parts.append(f"Speakers: {speakers}")
    if abstract:
        description_parts.append(abstract)
    if talk_description and talk_description != abstract:
        description_parts.append(talk_description)

    public_url = _public_submission_url(submission)
    if public_url:
        description_parts.append(f"Link: {public_url}")

    event.add("summary", title)
    event.add("description", "\n\n".join(description_parts) or f"Submission code: {code}")

    room_name = _room_name(slot.get("room"))
    if room_name:
        event.add("location", room_name)

    if public_url:
        event.add("url", public_url)


def _parse_datetime(raw_value: str, timezone: ZoneInfo) -> datetime:
    value = raw_value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone)


def _text_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        if "en" in value and value["en"]:
            return str(value["en"]).strip()
        for val in value.values():
            text = str(val).strip()
            if text:
                return text
        return ""
    return str(value).strip()


def _speaker_list(submission: dict[str, Any]) -> str:
    names: list[str] = []

    speaker_names = submission.get("speaker_names")
    if isinstance(speaker_names, str):
        names.extend([name.strip() for name in speaker_names.split(",") if name.strip()])
    elif isinstance(speaker_names, list):
        for speaker_name in speaker_names:
            text = _text_value(speaker_name)
            if text:
                names.append(text)

    speakers = submission.get("speakers")
    if isinstance(speakers, list):
        for speaker in speakers:
            if not isinstance(speaker, dict):
                continue
            name = _text_value(speaker.get("name"))
            if name:
                names.append(name)

    deduplicated: list[str] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        deduplicated.append(name)

    return ", ".join(deduplicated)


def _room_name(room: Any) -> str:
    if isinstance(room, str):
        return room.strip()
    if isinstance(room, dict):
        return _text_value(room.get("name") or room.get("en") or room)
    return ""


def _public_submission_url(submission: dict[str, Any]) -> str:
    url = submission.get("url")
    if isinstance(url, str) and url.strip():
        return url.strip()

    urls = submission.get("urls")
    if isinstance(urls, dict):
        public_url = urls.get("public") or urls.get("detail")
        if isinstance(public_url, str):
            return public_url.strip()

    return ""


def _is_cancelled_or_hidden(submission: dict[str, Any], slot: dict[str, Any]) -> bool:
    state = _text_value(submission.get("state")).lower()
    cancelled_state = state in {"canceled", "cancelled", "withdrawn"}

    hidden_flags = [
        submission.get("is_public"),
        slot.get("is_public"),
        slot.get("is_visible"),
    ]
    hidden = any(flag is False for flag in hidden_flags)

    return cancelled_state or hidden


def write_validated_calendar(calendar: Calendar, output_path: Path) -> None:
    payload = calendar.to_ical()

    # Validation step: parse the generated data before replacing final output.
    Calendar.from_ical(payload)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=".ics.tmp",
            dir=output_path.parent,
            delete=False,
        ) as temp_file:
            temp_file.write(payload)
            temp_path = Path(temp_file.name)

        Calendar.from_ical(temp_path.read_bytes())
        temp_path.replace(output_path)
    finally:
        if temp_path and temp_path.exists() and temp_path != output_path:
            temp_path.unlink(missing_ok=True)
