"""Converts clout requirement data to IR Requirement objects"""

from __future__ import annotations
from typing import Any, Dict, List

from src.ir.models import Requirement
from .primitives import primary_type


class RequirementConverter:
    """
    Stateless converter for transforming Puccini requirement data to IR.
    
    This converter handles the conversion of TOSCA requirements from
    clout format to IR Requirement objects, preserving relationship
    type information and capability references.
    """

    @staticmethod
    def convert(raw_requirements: List[Dict[str, Any]] | None) -> List[Requirement]:
        """
        Convert clout requirement data to IR Requirement objects.
        
        Args:
            raw_requirements: List of requirement dictionaries from clout,
                            or None if no requirements exist
                            
        Returns:
            List of Requirement objects, empty if no requirements provided
        """
        if not raw_requirements:
            return []
        
        requirements: List[Requirement] = []
        
        for entry in raw_requirements:
            requirement = RequirementConverter._convert_single_requirement(entry)
            requirements.append(requirement)
        
        return requirements

    @staticmethod
    def _convert_single_requirement(entry: Dict[str, Any]) -> Requirement:
        """
        Convert a single requirement entry to IR Requirement.
        
        Args:
            entry: Single requirement dictionary from clout
            
        Returns:
            Requirement: IR Requirement object
        """
        # Extract relationship type if present
        relationship_type = None
        if relationship := entry.get("relationship"):
            relationship_type = primary_type(relationship)
        
        # Extract capability reference with fallback logic
        capability = (
            entry.get("capabilityTypeName") or
            entry.get("capabilityName") or
            entry.get("capability") or
            "Undefined"
        )
        
        # Extract target node reference
        target_node = (
            entry.get("nodeTemplateName") or
            entry.get("node") or
            entry.get("target_node")
        )
        
        # Extract requirement name
        requirement_name = entry.get("name", "")
        
        # Extract additional properties for IR
        count_min = entry.get("lowerBound", 0)
        count_max = entry.get("upperBound", -1)  # -1 = unbounded
        
        return Requirement(
            name=requirement_name,
            capability=capability,
            target_node=target_node,
            relationship=relationship_type,
            count_min=count_min,
            count_max=count_max,
        )
