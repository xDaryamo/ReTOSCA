"""Main converter that orchestrates clout-to-IR conversion"""

from __future__ import annotations
from typing import Any, Dict, List

from src.ir.models import DeploymentModel, Node, Relation
from .base_converter import BaseConverter
from .node_converter import NodeConverter
from .relationship_converter import RelationshipConverter


class CloutToIRConverter:
    """
    Main converter that transforms Clout data into IR DeploymentModel.
    
    This converter coordinates multiple specialized converters to process 
    different sections of clout data (nodes, relationships, etc.) and 
    assembles them into a complete IR representation.
    
    The conversion process is extensible - new converters can be easily
    added to handle additional clout sections like policies or workflows.
    """

    def __init__(self, clout: Dict[str, Any], *, keep_meta: bool = False) -> None:
        """
        Initialize the converter with clout data.
        
        Args:
            clout: Normalized clout dictionary from Puccini
            keep_meta: Whether to preserve clout metadata in IR
        """
        self._clout = clout
        self._keep_meta = keep_meta
        
        # Register all converters you need – easy to extend
        self._converters: List[BaseConverter] = [
            NodeConverter(clout),
            RelationshipConverter(clout),
        ]

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def convert(self) -> DeploymentModel:
        """
        Convert clout data to IR DeploymentModel.
        
        Processes the clout through all registered converters and 
        assembles the final IR model with proper validation.
        
        Returns:
            DeploymentModel: Complete IR model with nodes and relationships
            
        Raises:
            CloutTransformError: If conversion fails due to invalid data
        """
        nodes: List[Node] = []
        relations: List[Relation] = []

        # Convert through all registered converters
        for converter in self._converters:
            nodes.extend(converter.convert_nodes())
            relations.extend(converter.convert_relations())

        # Extract top-level clout data
        tosca_props = self._clout.get("properties", {}).get("tosca", {})
        inputs = tosca_props.get("inputs", {})
        outputs = tosca_props.get("outputs", {})

        # Preserve metadata if requested
        metadata = self._clout.get("metadata", {}) if self._keep_meta else {}

        return DeploymentModel(
            nodes=nodes,
            relationships=relations,
            inputs=inputs,
            outputs=outputs,
            metadata=metadata
        )
