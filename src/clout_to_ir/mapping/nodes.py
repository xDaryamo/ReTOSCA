"""Strategy that maps only NodeTemplate vertexes."""

from __future__ import annotations

import logging
from typing import List

from src.ir.models import Node

from .attributes import AttributeMapper
from .base_strategy import IMapperStrategy
from .capabilities import CapabilityMapper
from .inference import infer_category
from .primitives import primary_type
from .requirements import RequirementMapper

logger = logging.getLogger(__name__)


class NodeMapper(IMapperStrategy):
    """Extract Node objects from clout['vertexes']."""

    def map_nodes(self) -> List[Node]:
        nodes: List[Node] = []

        for v_id, vertex in self.clout.get("vertexes", {}).items():
            if (
                vertex.get("metadata", {}).get("puccini", {}).get("kind")
                != "NodeTemplate"
            ):
                continue

            props = vertex.get("properties", {})
            node_type = primary_type(vertex)
            raw_caps = props.get("capabilities")
            category = infer_category(node_type, raw_caps)

            node = Node(
                id=v_id,
                type=node_type,
                category=category,
                properties=props.get("properties", {}),
                attributes=AttributeMapper.map(props.get("attributes")),
                description=props.get("description"),
                metadata=props.get("metadata") or {},
                capabilities=CapabilityMapper.map(props.get("capabilities")),
                requirements=RequirementMapper.map(props.get("requirements")),
                original_type=primary_type(vertex),
            )
            nodes.append(node)
            logger.debug("Node mapped: %s (%s)", node.id, node.type)

        return nodes
