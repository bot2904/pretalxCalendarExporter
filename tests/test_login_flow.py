from __future__ import annotations

import requests

from pretalx_star_exporter.exporter import extract_csrf_token, login_with_credentials


class _FakeResponse:
    def __init__(self, text: str = "", status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class _FakeSession:
    def __init__(self) -> None:
        self.cookies = requests.cookies.RequestsCookieJar()
        self.calls: list[tuple[str, str]] = []
        self.last_post_data: dict[str, str] | None = None

    def get(self, url: str, timeout: int = 30) -> _FakeResponse:  # noqa: ARG002
        self.calls.append(("GET", url))
        self.cookies.set("pretalx_csrftoken", "cookie-token")
        html = "<form method=post><input name=csrfmiddlewaretoken type=hidden value=html-token></form>"
        return _FakeResponse(text=html, status_code=200)

    def post(
        self,
        url: str,
        data: dict[str, str],
        headers: dict[str, str],  # noqa: ARG002
        timeout: int = 30,  # noqa: ARG002
        allow_redirects: bool = True,  # noqa: ARG002
    ) -> _FakeResponse:
        self.calls.append(("POST", url))
        self.last_post_data = data
        self.cookies.set("pretalx_session", "session-cookie")
        return _FakeResponse(status_code=200)


class _FallbackSession(_FakeSession):
    def get(self, url: str, timeout: int = 30) -> _FakeResponse:  # noqa: ARG002
        self.calls.append(("GET", url))
        if "orga/login/" not in url:
            return _FakeResponse(status_code=404)

        self.cookies.set("pretalx_csrftoken", "cookie-token")
        html = "<form method=post><input name=csrfmiddlewaretoken type=hidden value=html-token></form>"
        return _FakeResponse(text=html, status_code=200)


def test_extract_csrf_token_accepts_unquoted_attributes() -> None:
    html = "<form><input name=csrfmiddlewaretoken type=hidden value=abc123></form>"
    assert extract_csrf_token(html) == "abc123"


def test_login_with_credentials_uses_event_login_url_first() -> None:
    session = _FakeSession()

    login_with_credentials(
        session=session,
        base_url="https://pretalx.example.org",
        event_slug="demo26",
        username="attendee@example.org",
        password="secret",
        cookie_name="pretalx_session",
    )

    assert session.calls[0] == (
        "GET",
        "https://pretalx.example.org/demo26/login/?next=%2Fdemo26%2Fschedule%2F",
    )
    assert session.calls[1] == (
        "POST",
        "https://pretalx.example.org/demo26/login/?next=%2Fdemo26%2Fschedule%2F",
    )
    assert session.last_post_data is not None
    assert session.last_post_data["csrfmiddlewaretoken"] == "cookie-token"
    assert session.last_post_data["login_email"] == "attendee@example.org"
    assert session.last_post_data["login_password"] == "secret"
    assert session.last_post_data["login"] == "attendee@example.org"
    assert session.last_post_data["password"] == "secret"


def test_login_with_credentials_falls_back_to_orga_login() -> None:
    session = _FallbackSession()

    login_with_credentials(
        session=session,
        base_url="https://pretalx.example.org",
        event_slug="demo26",
        username="attendee@example.org",
        password="secret",
        cookie_name="pretalx_session",
    )

    assert session.calls[-2] == ("GET", "https://pretalx.example.org/orga/login/")
    assert session.calls[-1] == ("POST", "https://pretalx.example.org/orga/login/")
