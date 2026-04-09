# pretalx starred sessions → ICS exporter

Exports a logged-in pretalx user's starred/favourited sessions to an `.ics` file via the pretalx API.

## What it does

- Authenticates as a pretalx user (session auth)
  - Preferred: username/password login (`/orga/login/`, CSRF-aware)
  - Fallback: Firefox `cookies.sqlite` (`pretalx_session` cookie)
- Loads favourites from:
  - `GET /api/events/{event}/submissions/favourites/`
- Loads slot details per favourite from:
  - `GET /api/events/{event}/slots/?submission=<code>&expand=submission,room`
- Generates an ICS calendar in the event timezone.
- Includes title, room, speaker(s), description, and date/time.
- Represents multi-slot submissions as a calendar series.
- Prefixes cancelled/hidden sessions with `CANCELLED:`.
- Writes safely through a temporary file and validates generated ICS before replacing the target file.

## Install / run (uv)

```bash
uv sync
uv run pretalx-starred-export --help
```

## Configuration

Default config path: `/workspace/.config.yml`

Example:

```yaml
base_url: https://pretalx.example.org
event_slug: demo26
output_path: /workspace/favourites.ics

# preferred auth
username: attendee@example.org
password: super-secret

# optional fallback override
# firefox_profile: /home/user/.mozilla/firefox/abcd1234.default-release
# cookie_name: pretalx_session
```

## CLI usage

CLI flags override config values:

```bash
uv run pretalx-starred-export \
  --base-url https://pretalx.example.org \
  --event-slug demo26 \
  --output-path /workspace/favourites.ics \
  --username attendee@example.org \
  --password super-secret
```

## Tests

```bash
uv run pytest
```
