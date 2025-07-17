"""Converts clout vertices to IR nodes"""

from __future__ import annotations
import logging
from typing import List

from src.ir.models import Node
from .base_converter import BaseConverter
from .helpers.attribute_converter import AttributeConverter
from .helpers.capability_converter import CapabilityConverter
from .helpers.requirement_converter import RequirementConverter
from .helpers.primitives import primary_type
from .inference import infer_category

logger = logging.getLogger(__name__)


class NodeConverter(BaseConverter):
    """
    Converts clout vertices into IR Node objects.
    
    This converter processes the 'vertexes' section of clout data,
    identifying NodeTemplate vertices and transforming them into
    IR Node objects with proper categorization and type inference.
    """

    def convert_nodes(self) -> List[Node]:
        """
        Convert clout vertices to IR nodes.
        
        Processes all vertices in the clout data, filters for NodeTemplate
        vertices, and converts each one to an IR Node object.
        
        Returns:
            List of Node objects extracted from clout vertices
        """
        nodes: List[Node] = []

        for vertex_id, vertex in self.clout.get("vertexes", {}).items():
            if self._is_node_template(vertex):
                try:
                    node = self._convert_vertex_to_node(vertex_id, vertex)
                    nodes.append(node)
                    logger.debug("Converted vertex %s to node", vertex_id)
                except Exception as e:
                    logger.error("Failed to convert vertex %s: %s", vertex_id, str(e))

        logger.debug("Node conversion completed: %d nodes extracted", len(nodes))
        return nodes


    # ------------------------------------------------------------------ #
    # Private conversion methods
    # ------------------------------------------------------------------ #

    def _convert_vertex_to_node(self, vertex_id: str, vertex: dict) -> Node:
        """
        Convert a single clout vertex to an IR Node.
        
        Args:
            vertex_id: Unique identifier for the vertex
            vertex: Clout vertex data dictionary
            
        Returns:
            Node: IR Node object
            
        Raises:
            Exception: If vertex data is malformed or conversion fails
        """
        # Extract vertex properties
        props = vertex.get("properties", {})
        name = props.get("name", vertex_id)  # Fallback to ID if no name
        node_type = primary_type(vertex)
        raw_capabilities = props.get("capabilities")
        
        # Infer node category using type and capabilities
        category = infer_category(node_type, raw_capabilities)
        
        # Convert nested structures using helper converters
        attributes = AttributeConverter.convert(props.get("attributes"))
        capabilities = CapabilityConverter.convert(props.get("capabilities"))
        requirements = RequirementConverter.convert(props.get("requirements"))
        
        # Extract additional node data
        properties = self._get_entity_properties(vertex)
        metadata = self._get_entity_metadata(vertex)
        description = props.get("description")
        
        # Handle compute-specific properties if category is COMPUTE
        cpu_count, mem_size = self._extract_compute_resources(properties, category)
        
        return Node(
            id=vertex_id,
            name=name,
            type=node_type,
            category=category,
            properties=properties,
            attributes=attributes,
            capabilities=capabilities,
            requirements=requirements,
            description=description,
            metadata=metadata,
            original_type=node_type,
            cpu_count=cpu_count,
            mem_size=mem_size,
        )

    def _extract_compute_resources(self, properties: dict, category) -> tuple[int | None, int | None]:
        """
        Extract compute resources (CPU, memory) from node properties.
        
        Args:
            properties: Node properties dictionary
            category: Node category (for optimization)
            
        Returns:
            Tuple of (cpu_count, mem_size_mb) or (None, None)
        """
        # Only extract compute resources for compute nodes
        if category and hasattr(category, 'value') and category.value == "Compute":
            cpu_count = properties.get("cpu_count") or properties.get("num_cpus")
            mem_size = properties.get("mem_size") or properties.get("memory_size")
            
            # Convert memory to MB if needed
            if mem_size and isinstance(mem_size, str):
                mem_size = self._parse_memory_size(mem_size)
            
            return cpu_count, mem_size
        
        return None, None

    def _parse_memory_size(self, mem_str: str) -> int | None:
        """
        Parse memory size string to MB integer.
        
        Args:
            mem_str: Memory size string (e.g., "2GB", "1024MB", "512")
            
        Returns:
            Memory size in MB, or None if parsing fails
        """
        try:
            mem_str = mem_str.strip().upper()
            
            if mem_str.endswith("GB"):
                return int(float(mem_str[:-2]) * 1024)
            elif mem_str.endswith("MB"):
                return int(mem_str[:-2])
            elif mem_str.endswith("KB"):
                return int(float(mem_str[:-2]) / 1024)
            else:
                # Assume MB if no unit
                return int(mem_str)
        except (ValueError, AttributeError):
            logger.warning("Could not parse memory size: %s", mem_str)
            return None
