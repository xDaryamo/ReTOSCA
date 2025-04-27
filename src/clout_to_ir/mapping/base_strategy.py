"""Abstract base-class for all mapping strategies."""

from __future__ import annotations

from abc import ABC
from typing import Any, Dict, List

from src.ir.models import Node, Relation


class IMapperStrategy(ABC):
    """Interface enforced for every strategy plugged into StrategyFactory."""

    def __init__(self, clout: Dict[str, Any]) -> None:
        self.clout = clout

    # --------------------------------------------------------------------- #
    # The majority of concrete strategies only need to implement one of
    # these methods, but having both in the interface makes orchestration
    # trivial in the factory.
    # --------------------------------------------------------------------- #

    def map_nodes(self) -> List[Node]:
        """
        Return IR `Node` objects
        (empty if strategy is not node-oriented).
        """
        return []

    def map_relations(self) -> List[Relation]:
        """
        Return IR `Relation` objects
        (empty if strategy is not rel-oriented).
        """
        return []
