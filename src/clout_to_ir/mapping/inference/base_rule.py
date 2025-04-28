from abc import ABC, abstractmethod
from typing import Any

from src.ir.models import NodeCategory


class BaseRule(ABC):
    """Abstract base class for category inference rules."""

    @abstractmethod
    def match(self, entity: Any) -> NodeCategory | None:
        """Attempt to infer a NodeCategory from the given entity."""
        pass
