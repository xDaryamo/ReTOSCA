"""Strategy that maps Relationship edges."""

from __future__ import annotations

import logging
from typing import List

from src.ir.models import Relation

from .base_strategy import IMapperStrategy
from .primitives import primary_type

logger = logging.getLogger(__name__)


class RelationshipMapper(IMapperStrategy):
    """Walk every vertex → edgesOut to produce IR Relations."""

    def map_relations(self) -> List[Relation]:
        relations: List[Relation] = []
        vertices = self.clout.get("vertexes", {})

        for src_id, vertex in vertices.items():
            for edge in vertex.get("edgesOut", []):
                if (
                    edge.get("metadata", {}).get("puccini", {}).get("kind")
                    != "Relationship"
                ):
                    continue

                props = edge.get("properties", {})
                rel = Relation(
                    source=src_id,
                    target=edge["targetID"],
                    type=primary_type(edge),
                    properties=props.get("properties", {}),
                    capability=props.get("capability"),
                    description=props.get("description"),
                    original_type=primary_type(edge),
                )
                relations.append(rel)
                logger.debug(
                    "Relation mapped: %s -> %s (%s)",
                    rel.source,
                    rel.target,
                    rel.type,
                )

        return relations
