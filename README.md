# pretalx starred sessions → ICS exporter

Export a logged-in pretalx user’s starred/favourited sessions to an `.ics` file.

## What it exports

For each favourited submission, the exporter fetches slots from the **current schedule version** and writes ICS events with:

- title (`SUMMARY`)
- room (`LOCATION`)
- speaker **names** (not speaker IDs)
- abstract + talk description (`DESCRIPTION`)
- public talk link (`URL`, also included in `DESCRIPTION`)
- timezone-aware start/end in the event timezone

It also:

- marks cancelled/hidden sessions as `CANCELLED:` + `STATUS:CANCELLED`
- represents multi-slot talks as a recurring series
- validates ICS before replacing the output file (atomic temp-file write)

## Authentication

Session authentication is used (as required by the favourites API):

1. Username/password login (preferred)
   - tries `/{event}/login/?next=...`
   - then `/{event}/login/`
   - then `/orga/login/`
2. Firefox cookie fallback (`cookies.sqlite`, `pretalx_session` by default)

## Quick start (uv)

```bash
uv sync
uv run pretalx-starred-export \
  --base-url https://pretalx.example.org \
  --event-slug demo26 \
  --output-path /workspace/favourites.ics \
  --username attendee@example.org \
  --password super-secret
```

## Configuration

Default config path: `/workspace/.config.yml`

```yaml
base_url: https://pretalx.example.org
event_slug: demo26
output_path: /workspace/favourites.ics

# preferred auth
username: attendee@example.org
password: super-secret

# optional Firefox fallback override
# firefox_profile: /home/user/.mozilla/firefox/abcd1234.default-release
# cookie_name: pretalx_session
```

Environment variable equivalents:

- `PRETALX_STARRED_EXPORT_BASE_URL`
- `PRETALX_STARRED_EXPORT_EVENT_SLUG`
- `PRETALX_STARRED_EXPORT_OUTPUT_PATH`
- `PRETALX_STARRED_EXPORT_USERNAME`
- `PRETALX_STARRED_EXPORT_PASSWORD`
- `PRETALX_STARRED_EXPORT_FIREFOX_PROFILE`
- `PRETALX_STARRED_EXPORT_COOKIE_NAME`

Precedence: **CLI > environment > YAML config**.

## Docker

Build:

```bash
docker build \
  --build-arg UID="$(id -u)" \
  --build-arg GID="$(id -g)" \
  -t pretalx-starred-exporter .
```

Run (mount current directory to `/workspace`):

```bash
docker run --rm -v "$PWD:/workspace" pretalx-starred-exporter
```

## Tests

```bash
uv run pytest
```

## GitHub Actions (optional)

The repository includes `.github/workflows/export-calendar.yml` to generate and publish the ICS on a schedule.

Required repo variables:

- `PRETALX_STARRED_EXPORT_BASE_URL`
- `PRETALX_STARRED_EXPORT_EVENT_SLUG`
- `PRETALX_STARRED_EXPORT_OUTPUT_PATH`
- optional: `PRETALX_STARRED_EXPORT_COOKIE_NAME`

Required repo secrets:

- `PRETALX_STARRED_EXPORT_USERNAME`
- `PRETALX_STARRED_EXPORT_PASSWORD`
