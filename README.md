# pretalx starred sessions → ICS exporter

Exports a logged-in pretalx user's starred/favourited sessions to an `.ics` file via the pretalx API.

## What it does

- Authenticates as a pretalx user (session auth)
  - Preferred: username/password login (CSRF-aware). Tries `/{event}/login/?next=...` first, then `/{event}/login/`, then `/orga/login/`.
  - Fallback: Firefox `cookies.sqlite` (`pretalx_session` cookie)
- Loads favourites from:
  - `GET /api/events/{event}/submissions/favourites/`
- Loads slot details per favourite from:
  - `GET /api/events/{event}/slots/?submission=<code>&expand=submission,room&schedule=<current_schedule_id>`
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

## Docker (lightweight)

Build the image (using your host UID/GID so generated files stay owned by your user):

```bash
docker build \
  --build-arg UID="$(id -u)" \
  --build-arg GID="$(id -g)" \
  -t pretalx-starred-exporter .
```

Run it with your local config/output directory mounted at `/workspace`:

```bash
docker run --rm -v "$PWD:/workspace" pretalx-starred-exporter
```

This uses the default config path (`/workspace/.config.yml`) from inside the container.

You can also override config values directly via CLI flags:

```bash
docker run --rm -v "$PWD:/workspace" pretalx-starred-exporter \
  --base-url https://pretalx.example.org \
  --event-slug demo26 \
  --output-path /workspace/favourites.ics \
  --username attendee@example.org \
  --password super-secret
```

Or pass configuration via environment variables (useful for CI/secrets):

```bash
docker run --rm -v "$PWD:/workspace" \
  -e PRETALX_STARRED_EXPORT_BASE_URL=https://pretalx.example.org \
  -e PRETALX_STARRED_EXPORT_EVENT_SLUG=demo26 \
  -e PRETALX_STARRED_EXPORT_OUTPUT_PATH=/workspace/favourites.ics \
  -e PRETALX_STARRED_EXPORT_USERNAME=attendee@example.org \
  -e PRETALX_STARRED_EXPORT_PASSWORD=super-secret \
  pretalx-starred-exporter
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

Equivalent environment variables:

- `PRETALX_STARRED_EXPORT_BASE_URL`
- `PRETALX_STARRED_EXPORT_EVENT_SLUG`
- `PRETALX_STARRED_EXPORT_OUTPUT_PATH`
- `PRETALX_STARRED_EXPORT_USERNAME`
- `PRETALX_STARRED_EXPORT_PASSWORD`
- `PRETALX_STARRED_EXPORT_FIREFOX_PROFILE`
- `PRETALX_STARRED_EXPORT_COOKIE_NAME`

Configuration precedence is:

1. CLI flags
2. Environment variables
3. YAML config file

## CLI usage

CLI flags override environment variables and config file values:

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

## GitHub Actions automation

This repository includes `.github/workflows/export-calendar.yml` to run the exporter on a schedule and publish the generated ICS to a dedicated `calendar` branch.

### Required repository variables (Settings → Secrets and variables → Actions → Variables)

- `PRETALX_STARRED_EXPORT_BASE_URL` (example: `https://pretalx.example.org`)
- `PRETALX_STARRED_EXPORT_EVENT_SLUG` (example: `demo26`)
- `PRETALX_STARRED_EXPORT_OUTPUT_PATH` (example: `out/favourites.ics`)
- Optional: `PRETALX_STARRED_EXPORT_COOKIE_NAME` (defaults to `pretalx_session` if unset)

### Required repository secrets (Settings → Secrets and variables → Actions → Secrets)

- `PRETALX_STARRED_EXPORT_USERNAME`
- `PRETALX_STARRED_EXPORT_PASSWORD`

The workflow passes credentials via environment variables only (not CLI arguments), and masks both username and password in logs.

### GitHub Pages

The workflow publishes from the `calendar` branch. Configure GitHub Pages source to:

- **Branch:** `calendar`
- **Folder:** `/ (root)`

After enabling Pages, your ICS will be available at:

- `https://<owner>.github.io/<repo>/favourites.ics` (or whatever file name you set in `PRETALX_STARRED_EXPORT_OUTPUT_PATH`)
