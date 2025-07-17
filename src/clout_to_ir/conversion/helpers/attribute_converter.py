"""Converter for clout attribute data to IR Attribute objects."""

from __future__ import annotations
from typing import Any, Dict

from src.ir.models import Attribute


class AttributeConverter:
    """
    Stateless converter for clout attribute data to IR Attribute objects.
    
    Handles the conversion of raw attribute dictionaries from clout data
    into properly structured IR Attribute objects with type inference
    and value normalization.
    """

    @staticmethod
    def convert(raw_attributes: Dict[str, Any] | None) -> Dict[str, Attribute]:
        """
        Convert clout attribute data to IR Attribute objects.
        
        Takes raw attribute data from clout (typically from vertex properties)
        and converts each key-value pair into a proper IR Attribute object
        with inferred type information and normalized values.
        
        Args:
            raw_attributes: Raw attribute dictionary from clout, or None
            
        Returns:
            Dictionary mapping attribute names to Attribute objects
        """
        if not raw_attributes:
            return {}
        
        attributes = {}
        
        for name, value in raw_attributes.items():
            attribute = Attribute(
                name=name,
                type=AttributeConverter._infer_attribute_type(value),
                value=value,
                default=None,  # Clout doesn't typically have default values
                metadata={}    # Could be extended for clout-specific metadata
            )
            attributes[name] = attribute
        
        return attributes

    @staticmethod
    def _infer_attribute_type(value: Any) -> str:
        """
        Infer the TOSCA data type from a Python value.
        
        Maps Python types to TOSCA-compatible type names for better
        semantic representation in the IR.
        
        Args:
            value: The attribute value
            
        Returns:
            TOSCA-compatible type name
        """
        if value is None:
            return "string"  # Default fallback
        elif isinstance(value, bool):
            return "boolean"
        elif isinstance(value, int):
            return "integer"
        elif isinstance(value, float):
            return "float"
        elif isinstance(value, str):
            return "string"
        elif isinstance(value, list):
            return "list"
        elif isinstance(value, dict):
            return "map"
        else:
            # For complex objects, convert to string representation
            return "string"
