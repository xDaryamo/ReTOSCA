"""Compose concrete strategies and build the final DeploymentModel"""

from __future__ import annotations

from typing import Any, Dict, List

from src.ir.models import DeploymentModel, Node, Relation

from .base_strategy import IMapperStrategy
from .nodes import NodeMapper
from .relationships import RelationshipMapper


class StrategyFactory:
    """
    Very small orchestrator that bundles together the
    concrete mapping strategies required to build an IR.
    """

    def __init__(self, clout: Dict[str, Any], *, keep_meta: bool) -> None:
        self._clout = clout
        self._keep_meta = keep_meta

        # Register all strategies you need – easy to extend
        self._strategies: List[IMapperStrategy] = [
            NodeMapper(clout),
            RelationshipMapper(clout),
        ]

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #

    def build_ir(self) -> DeploymentModel:
        nodes: List[Node] = []
        relations: List[Relation] = []

        for strat in self._strategies:
            nodes.extend(strat.map_nodes())
            relations.extend(strat.map_relations())

        metadata = self._clout.get("metadata", {}) if self._keep_meta else {}
        return DeploymentModel(
            nodes=nodes, relationships=relations, metadata=metadata
        )
