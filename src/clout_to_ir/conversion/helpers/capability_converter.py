"""Converter for transforming clout capabilities to IR Capability objects."""

from __future__ import annotations
from typing import Any, Dict

from src.ir.models import Capability
from .primitives import primary_type


class CapabilityConverter:
    """
    Stateless converter for transforming clout capability data to IR.
    
    Converts raw clout capability definitions into properly structured
    IR Capability objects with type information, properties, and 
    relationship count constraints.
    """

    @staticmethod
    def convert(raw_capabilities: Dict[str, Any] | None) -> Dict[str, Capability]:
        """
        Convert clout capability data to IR Capability objects.
        
        Processes capability definitions from clout data and transforms
        them into IR Capability objects with proper type extraction
        and constraint handling.
        
        Args:
            raw_capabilities: Raw capability data from clout, or None
            
        Returns:
            Dictionary mapping capability names to Capability objects.
            Returns empty dict if input is None or empty.
        """
        if not raw_capabilities:
            return {}

        capabilities: Dict[str, Capability] = {}
        
        for name, data in raw_capabilities.items():
            try:
                capability = CapabilityConverter._convert_single_capability(name, data)
                capabilities[name] = capability
            except Exception as e:
                # Log error but continue processing other capabilities
                import logging
                logger = logging.getLogger(__name__)
                logger.warning("Failed to convert capability %s: %s", name, str(e))
        
        return capabilities

    @staticmethod
    def _convert_single_capability(name: str, data: Dict[str, Any]) -> Capability:
        """
        Convert a single capability definition to IR Capability object.
        
        Args:
            name: Capability name
            data: Capability data dictionary from clout
            
        Returns:
            Capability: IR Capability object
            
        Raises:
            Exception: If capability data is malformed
        """
        # Extract capability type using shared utility
        capability_type = primary_type(data)
        
        # Extract properties (nested under 'properties' key)
        properties = data.get("properties", {})
        
        # Extract description
        description = data.get("description")
        
        # Extract relationship count constraints
        count_min = CapabilityConverter._extract_count_constraint(
            data, "minRelationshipCount", default=0
        )
        count_max = CapabilityConverter._extract_count_constraint(
            data, "maxRelationshipCount", default=-1
        )
        
        return Capability(
            name=name,
            type=capability_type,
            properties=properties,
            description=description,
            count_min=count_min,
            count_max=count_max,
        )

    @staticmethod
    def _extract_count_constraint(data: Dict[str, Any], key: str, default: int) -> int:
        """
        Extract and validate relationship count constraint.
        
        Args:
            data: Capability data dictionary
            key: Key to extract (e.g., "minRelationshipCount")
            default: Default value if key not found
            
        Returns:
            Integer count constraint, or default if invalid
        """
        try:
            value = data.get(key, default)
            if isinstance(value, int):
                return value
            elif isinstance(value, str) and value.isdigit():
                return int(value)
            else:
                return default
        except (ValueError, TypeError):
            return default