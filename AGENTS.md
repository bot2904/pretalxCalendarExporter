# AGENTS.md

## Project focus
Build a Python script that exports a **logged-in pretalx user's starred sessions** to an `.ics` file.

## Canonical references
- API docs index: https://docs.pretalx.org/api/
- API fundamentals (auth, versions, pagination): https://docs.pretalx.org/api/fundamentals/
- Endpoint viewer (ReDoc): https://docs.pretalx.org/api/resources/
- OpenAPI schema (best for scripting): https://docs.pretalx.org/schema.yml

## Key endpoints to use
- `GET /api/events/{event}/submissions/favourites/` → list of favourited submission codes
- `POST /api/events/{event}/submissions/{code}/favourite/` → add favourite
- `DELETE /api/events/{event}/submissions/{code}/favourite/` → remove favourite
- `GET /api/events/{event}/slots/?submission=<code>&expand=submission,room` → slot + timing data
- Ready-made ICS export (session-auth): `/{event}/schedule/export/faved.ics`

## Source locations in pretalx repo
Local cached checkout used during exploration:
- `/home/pi/.cache/checkouts/github.com/pretalx/pretalx`

Most relevant files:
- `doc/api/fundamentals.rst`
- `doc/api/schema.yml`
- `src/pretalx/api/urls.py`
- `src/pretalx/api/views/submission.py` (favourites endpoints)
- `src/pretalx/static/agenda/js/favourite.js` (client-side favourites flow)
- `src/pretalx/schedule/exporters.py` (`FavedICalExporter`)
- `src/pretalx/agenda/urls.py` + `src/pretalx/agenda/views/schedule.py` (export route handling)
- `src/tests/api/views/integration/test_submission.py` (favourites auth/behaviour)

## Auth/behaviour notes
- Favourites API endpoint docs explicitly say they use **session authentication**.
- Access requires `schedule.list_schedule` permission on the event.
- For logged-in attendees, session cookies are the practical auth path (`pretalx_session`; CSRF token for POST/DELETE).
- Anonymous stars are stored client-side in localStorage key `${eventSlug}_favs`.

