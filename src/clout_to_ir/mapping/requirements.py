"""Strategy dedicated to Requirements conversion."""

from __future__ import annotations

from typing import Any, Dict, List

from src.ir.models import Requirement

from .primitives import primary_type


class RequirementMapper:
    """Stateless converter for the Puccini requirement section."""

    @staticmethod
    def map(raw: List[Dict[str, Any]] | None) -> List[Requirement]:
        raw = raw or []
        reqs: List[Requirement] = []
        for entry in raw:
            relationship_type = None
            if rel := entry.get("relationship"):
                relationship_type = primary_type(rel)
            reqs.append(
                Requirement(
                    name=entry.get("name", ""),
                    capability=entry.get("capabilityTypeName")
                    or entry.get("capabilityName"),
                    target_node=entry.get("nodeTemplateName"),
                    relationship=relationship_type,
                )
            )
        return reqs
