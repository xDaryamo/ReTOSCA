from typing import Any

from src.ir.models import NodeCategory

from .base_rule import BaseRule


class CapabilityRule(BaseRule):
    """A rule matching the capabilities section of a node."""

    def __init__(
        self, names_or_types: list[str], category: NodeCategory
    ) -> None:
        self._names_or_types = {name.lower() for name in names_or_types}
        self._category = category

    def match(self, capabilities: dict[str, Any]) -> NodeCategory | None:
        for name, body in capabilities.items():
            if name.lower() in self._names_or_types:
                return self._category
            cap_type = next(iter(body.get("types", {})), "").lower()
            if cap_type in self._names_or_types:
                return self._category
        return None
