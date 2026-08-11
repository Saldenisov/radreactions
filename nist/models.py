"""Typed, side-effect-free NIST ingestion values."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DetailStatus(StrEnum):
    """Canonical state of one NIST Detail URL."""

    QUEUED = "queued"
    ACCEPTED = "accepted"
    CONFIRMED_EMPTY = "confirmed_empty"
    RETRYABLE = "retryable"
    BLOCKED = "blocked"
    INVALID = "invalid"


class ResponseKind(StrEnum):
    """Classification of an immutable HTTP attempt."""

    ACCEPTED = "accepted"
    CONFIRMED_EMPTY = "confirmed_empty"
    RETRYABLE = "retryable"
    BLOCKED = "blocked"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class ResponseClassification:
    kind: ResponseKind
    reason: str

    @property
    def usable_detail(self) -> bool:
        return self.kind is ResponseKind.ACCEPTED


@dataclass(frozen=True, slots=True)
class HttpResponse:
    """Network response before it is stored in the immutable archive."""

    status_code: int | None
    body: bytes
    content_type: str
    fetched_at: str
