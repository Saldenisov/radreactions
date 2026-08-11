"""Pure NIST Detail-response classifier.

No response becomes accepted solely because it was saved successfully.  In
particular, a 5xx body is provenance, not a Detail page and not an empty page.
"""

from __future__ import annotations

import re

from .models import ResponseClassification, ResponseKind

_DETAIL_SIGNALS = (
    re.compile(r"<TH[^>]*>\s*Reaction\s*</TH>", re.IGNORECASE),
    re.compile(r"<B[^>]*>\s*Squib\s*:\s*</B>", re.IGNORECASE),
    re.compile(r"<TH[^>]*>\s*Rate constant\s*</TH>", re.IGNORECASE),
)
_EMPTY_SIGNALS = (
    re.compile(r"Search returned\s+0\s+records?", re.IGNORECASE),
    re.compile(r"No records? matched", re.IGNORECASE),
)
_BACKEND_SIGNALS = (
    ("backend_connection", re.compile(r"cannot get a connection", re.IGNORECASE)),
    ("backend_pool", re.compile(r"pool error", re.IGNORECASE)),
    ("backend_unavailable", re.compile(r"unable to connect to (?:the )?database", re.IGNORECASE)),
    ("backend_search", re.compile(r"search not submitted due to errors", re.IGNORECASE)),
    (
        "cloudflare_error",
        re.compile(r"(?:cf-error-code|cf-error-details|cloudflare ray id)", re.IGNORECASE),
    ),
    (
        "cloudflare_origin",
        re.compile(
            r"<title[^>]*>\s*(?:web server is down|connection timed out|"
            r"origin is unreachable|a timeout occurred)\s*</title>",
            re.IGNORECASE,
        ),
    ),
)


def classify_detail_response(*, status_code: int | None, html: str) -> ResponseClassification:
    """Classify one expected NIST Detail response without mutating state."""

    if status_code in {403, 429}:
        return ResponseClassification(ResponseKind.BLOCKED, f"blocked HTTP {status_code}")
    if status_code is None:
        return ResponseClassification(
            ResponseKind.RETRYABLE, "transport failure without HTTP response"
        )
    if 500 <= status_code <= 599:
        return ResponseClassification(ResponseKind.RETRYABLE, f"retryable HTTP {status_code}")
    if status_code != 200:
        return ResponseClassification(ResponseKind.INVALID, f"unexpected HTTP {status_code}")

    for name, pattern in _BACKEND_SIGNALS:
        if pattern.search(html):
            return ResponseClassification(ResponseKind.RETRYABLE, name)
    if any(pattern.search(html) for pattern in _EMPTY_SIGNALS):
        return ResponseClassification(ResponseKind.CONFIRMED_EMPTY, "explicit zero-record response")
    if sum(bool(pattern.search(html)) for pattern in _DETAIL_SIGNALS) >= 2:
        return ResponseClassification(ResponseKind.ACCEPTED, "valid NIST Detail signature")
    return ResponseClassification(ResponseKind.INVALID, "HTTP 200 without NIST Detail signature")
