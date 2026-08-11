"""Public-corpus visibility rules."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from typing import Any


def is_public_buxton_reaction(
    reaction: Mapping[str, Any] | None,
    public_tables: Collection[int],
) -> bool:
    """Return whether a Buxton reaction is validated and publishable."""
    if not reaction:
        return False
    try:
        return int(reaction.get("validated") or 0) == 1 and int(
            reaction.get("table_no")
        ) in public_tables
    except (TypeError, ValueError):
        return False
