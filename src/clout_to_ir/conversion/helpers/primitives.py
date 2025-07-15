"""Small, pure helpers reused by many strategies."""

from __future__ import annotations

from typing import Any, Dict


def primary_type(entity: Dict[str, Any]) -> str:
    """
    Return the most-specific Puccini type.

    Puccini keeps a dict of all inherited types; the first key is the
    specialised one.
    """
    return next(
        iter(
            entity.get("types")
            or entity.get("properties", {}).get("types", {})
            or {}
        ),
        "Undefined",
    )
