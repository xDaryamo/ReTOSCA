"""Strategy dedicated to Capabilities conversion."""

from __future__ import annotations

from typing import Any, Dict

from src.ir.models import Capability

from .primitives import primary_type


class CapabilityMapper:
    """Stateless converter for the capabilities section."""

    @staticmethod
    def map(raw: Dict[str, Any] | None) -> Dict[str, Capability]:
        raw = raw or {}
        caps: Dict[str, Capability] = {}
        for name, data in raw.items():
            caps[name] = Capability(
                name=name,
                type=primary_type(data),
                properties=data.get("properties", {}),
                description=data.get("description"),
                count_min=data.get("minRelationshipCount", 0),
                count_max=data.get("maxRelationshipCount", -1),
            )
        return caps
