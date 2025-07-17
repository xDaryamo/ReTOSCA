"""Converts clout edges to IR relationships"""

from __future__ import annotations
import logging
from typing import List

from src.clout_to_ir.conversion.helpers.primitives import primary_type

from src.ir.models import Relation
from .base_converter import BaseConverter

logger = logging.getLogger(__name__)


class RelationshipConverter(BaseConverter):
    """
    Converts clout edges into IR Relation objects.
    
    This converter processes the 'edgesOut' sections of clout vertices,
    identifying Relationship edges and transforming them into IR Relation
    objects that represent the topology connections between nodes.
    """


    def convert_relations(self) -> List[Relation]:
        """
        Convert clout edges to IR relations.
        
        Processes all vertices in the clout data, examines their outgoing
        edges, and converts Relationship edges to IR Relation objects.
        
        Returns:
            List of Relation objects extracted from clout edges
        """
        relations: List[Relation] = []
        vertices = self.clout.get("vertexes", {})

        for source_id, vertex in vertices.items():
            edges_out = vertex.get("edgesOut", [])
            
            for edge in edges_out:
                if self._is_relationship(edge):
                    try:
                        relation = self._convert_edge_to_relation(source_id, edge)
                        relations.append(relation)
                        logger.debug(
                            "Converted edge %s -> %s to relation",
                            source_id, edge.get("targetID", "unknown")
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to convert edge from %s: %s", 
                            source_id, str(e)
                        )

        logger.debug("Relationship conversion completed: %d relations extracted", len(relations))
        return relations

    # ------------------------------------------------------------------ #
    # Private conversion methods
    # ------------------------------------------------------------------ #

    def _convert_edge_to_relation(self, source_id: str, edge: dict) -> Relation:
        """
        Convert a single clout edge to an IR Relation.
        
        Args:
            source_id: ID of the source vertex
            edge: Clout edge data dictionary
            
        Returns:
            Relation: IR Relation object
            
        Raises:
            KeyError: If required edge data is missing
            Exception: If edge data is malformed or conversion fails
        """
        # Extract edge properties
        props = edge.get("properties", {})
        target_id = edge.get("targetID")
        
        if not target_id:
            raise ValueError(f"Edge from {source_id} missing targetID")
        
        # Extract relationship type and properties
        relation_type = primary_type(edge)
        properties = self._get_entity_properties(edge)
        
        # Extract relationship-specific data
        capability_name = self._extract_capability_name(props)
        interface_name = self._extract_interface_name(props)
        description = props.get("description")
        
        return Relation(
            source=source_id,
            target=target_id,
            type=relation_type,
            capability=capability_name,
            interface=interface_name,
            properties=properties,
            description=description,
            original_type=relation_type,
        )

    def _extract_capability_name(self, edge_props: dict) -> str | None:
        """
        Extract the target capability name from relationship properties.
        
        Args:
            edge_props: Edge properties dictionary
            
        Returns:
            Capability name or None if not specified
        """
        # Try different possible locations for capability info
        capability = edge_props.get("capability")
        if capability:
            if isinstance(capability, str):
                return capability
            elif isinstance(capability, dict):
                return capability.get("name")
        
        # Try alternative property names
        return (
            edge_props.get("capabilityName") or
            edge_props.get("capability_name") or
            edge_props.get("targetCapability")
        )

    def _extract_interface_name(self, edge_props: dict) -> str | None:
        """
        Extract the relationship interface name from properties.
        
        Args:
            edge_props: Edge properties dictionary
            
        Returns:
            Interface name or None if not specified
        """
        # Check for interface information in properties
        interfaces = edge_props.get("interfaces", {})
        if interfaces:
            # Return first interface name if multiple exist
            return next(iter(interfaces.keys()), None)
        
        # Try alternative property names
        return (
            edge_props.get("interface") or
            edge_props.get("interfaceName") or
            edge_props.get("interface_name")
        )

    def _validate_relation_targets(self, relations: List[Relation]) -> dict:
        """
        Validate that all relation targets exist in the clout vertices.
        
        Args:
            relations: List of relations to validate
            
        Returns:
            Dictionary with validation results
        """
        vertex_ids = set(self.clout.get("vertexes", {}).keys())
        validation_results = {
            "total_relations": len(relations),
            "valid_relations": 0,
            "invalid_targets": [],
            "missing_sources": []
        }
        
        for relation in relations:
            # Check if source exists
            if relation.source not in vertex_ids:
                validation_results["missing_sources"].append(relation.source)
            
            # Check if target exists
            if relation.target not in vertex_ids:
                validation_results["invalid_targets"].append({
                    "source": relation.source,
                    "target": relation.target,
                    "type": relation.type
                })
            else:
                validation_results["valid_relations"] += 1
        
        return validation_results