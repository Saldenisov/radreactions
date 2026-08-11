"""Narrow public-interface client for official NIST Solution Kinetics pages."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .models import HttpResponse

NIST_HOST = "kinetics.nist.gov"
NIST_PATH_PREFIX = "/solution/"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_USER_AGENT = "RadReactions/3.0 provenance archive"


class NistTransportError(RuntimeError):
    """No HTTP response was received from the official public interface."""


def is_allowed_solution_url(url: str) -> bool:
    parsed = urlparse(url)
    try:
        return (
            parsed.scheme == "https"
            and parsed.hostname == NIST_HOST
            and parsed.port in {None, 443}
            and parsed.username is None
            and parsed.password is None
            and parsed.path.startswith(NIST_PATH_PREFIX)
        )
    except ValueError:
        return False


def fetch_detail(url: str, *, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> HttpResponse:
    """Fetch one allowed Detail URL. HTTP errors are returned for archival."""

    if not is_allowed_solution_url(url):
        raise ValueError(f"NIST URL is outside allowed public interface: {url}")
    request = Request(
        url,
        method="GET",
        headers={
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Referer": "https://kinetics.nist.gov/solution/",
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - URL is allowlisted above.
            body = response.read()
            return HttpResponse(
                status_code=int(getattr(response, "status", 200)),
                body=body,
                content_type=response.headers.get("Content-Type", ""),
                fetched_at=datetime.now(UTC).isoformat(),
            )
    except HTTPError as exc:
        body = exc.read()
        return HttpResponse(
            status_code=int(exc.code),
            body=body,
            content_type=exc.headers.get("Content-Type", ""),
            fetched_at=datetime.now(UTC).isoformat(),
        )
    except OSError as exc:
        raise NistTransportError(f"NIST transport failure: {exc}") from exc
