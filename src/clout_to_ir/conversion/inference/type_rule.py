import re

from src.ir.models import NodeCategory

from .base_rule import BaseRule


class TypeRule(BaseRule):
    """A rule matching the node type string (case-insensitive regex)."""

    def __init__(self, patterns: list[str], category: NodeCategory) -> None:
        self._patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
        self._category = category

    def match(self, node_type: str) -> NodeCategory | None:
        for pattern in self._patterns:
            if pattern.search(node_type):
                return self._category
        return None
