"""Abstract base class for all clout data converters."""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List
import logging

from src.ir.models import Node, Relation


class BaseConverter(ABC):
    """
    Abstract base class for converting specific parts of clout data to IR.
    
    This class provides shared functionality and enforces a common interface
    for all clout converters. Each concrete converter specializes in handling
    specific sections of clout data (nodes, relationships, policies, etc.).
    
    The design allows converters to focus on their specific domain while
    sharing common utilities for clout data processing.
    """

    def __init__(self, clout: Dict[str, Any]) -> None:
        """
        Initialize converter with clout data.
        
        Args:
            clout: Normalized clout dictionary from Puccini
        """
        self.clout = clout
        self.logger = logging.getLogger(self.__class__.__name__)

    # --------------------------------------------------------------------- #
    # Abstract interface - concrete converters must implement these
    # --------------------------------------------------------------------- #

    def convert_nodes(self) -> List[Node]:
        """
        Convert clout data to IR Node objects.
        
        Concrete converters should override this method if they handle
        node conversion. The default implementation returns an empty list
        for converters that don't process nodes.
        
        Returns:
            List of Node objects converted from clout data
        """
        return []

    def convert_relations(self) -> List[Relation]:
        """
        Convert clout data to IR Relation objects.
        
        Concrete converters should override this method if they handle
        relationship conversion. The default implementation returns an 
        empty list for converters that don't process relationships.
        
        Returns:
            List of Relation objects converted from clout data
        """
        return []

    # --------------------------------------------------------------------- #
    # Shared utility methods for all converters
    # --------------------------------------------------------------------- #

    def _is_node_template(self, vertex: Dict[str, Any]) -> bool:
        """
        Check if a clout vertex represents a TOSCA node template.
        
        Args:
            vertex: Clout vertex dictionary
            
        Returns:
            True if vertex is a NodeTemplate, False otherwise
        """
        kind = vertex.get("metadata", {}).get("puccini", {}).get("kind")
        return kind == "NodeTemplate"

    def _is_relationship(self, edge: Dict[str, Any]) -> bool:
        """
        Check if a clout edge represents a TOSCA relationship.
        
        Args:
            edge: Clout edge dictionary
            
        Returns:
            True if edge is a Relationship, False otherwise
        """
        kind = edge.get("metadata", {}).get("puccini", {}).get("kind")
        return kind == "Relationship"

    def _get_entity_properties(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract properties from a Puccini entity.
        
        Args:
            entity: Puccini entity (vertex or edge)
            
        Returns:
            Properties dictionary, empty if none found
        """
        return entity.get("properties", {}).get("properties", {})

    def _get_entity_metadata(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract metadata from a Puccini entity.
        
        Args:
            entity: Puccini entity (vertex or edge)
            
        Returns:
            Metadata dictionary, empty if none found
        """
        metadata = entity.get("properties", {}).get("metadata")
        # Ensure we always return a dict, never None
        return metadata if isinstance(metadata, dict) else {}

    def _log_conversion(self, item_type: str, item_id: str, success: bool = True) -> None:
        """
        Log conversion progress for debugging and monitoring.
        
        Args:
            item_type: Type of item being converted (e.g., "node", "relation")
            item_id: Identifier of the item
            success: Whether conversion was successful
        """
        if success:
            self.logger.debug("Converted %s: %s", item_type, item_id)
        else:
            self.logger.warning("Failed to convert %s: %s", item_type, item_id)
