"""
Terraform-specific base class for resource mappers with variable support.

This module provides an enhanced base class for Terraform resource mappers
that includes access to variable context for handling Terraform variables
and generating appropriate TOSCA get_input functions.
"""

import logging
from abc import ABC
from typing import TYPE_CHECKING, Any

from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from .variables import VariableContext

logger = logging.getLogger(__name__)


class TerraformSingleResourceMapper(SingleResourceMapper, ABC):
    """
    Base class for Terraform resource mappers with variable support.

    This class provides helper methods for accessing the variable context
    and resolving property values based on whether they reference Terraform
    variables or should use concrete values.
    """

    def __init__(self):
        """Initialize the mapper."""
        self._logger = logger.getChild(self.__class__.__name__)
        self._variable_context: VariableContext | None = None

    def set_variable_context(self, context: "VariableContext | None") -> None:
        """
        Set the variable context for this mapper.

        Args:
            context: The VariableContext instance to use for variable resolution
        """
        self._variable_context = context

    def resolve_property_value(
        self,
        resource_address: str,
        property_name: str,
        fallback_value: Any = None,
        context: str = "property",
    ) -> Any:
        """
        Resolve a property value considering variable context.

        Args:
            resource_address: Resource address (e.g., "aws_instance.web")
            property_name: Property name (e.g., "instance_type")
            fallback_value: Value to use if no variable context or resolved value
            context: Context where value will be used
                ("property", "metadata", "attribute")

        Returns:
            Either {"$get_input": "variable_name"} or the concrete resolved value
        """
        if not self._variable_context:
            # No variable context available, return fallback
            return fallback_value

        # Resolve using variable context
        resolved_value = self._variable_context.resolve_property(
            resource_address, property_name, context
        )

        # If resolved value is None, use fallback
        return resolved_value if resolved_value is not None else fallback_value

    def get_concrete_value(
        self, resource_address: str, property_name: str, fallback_value: Any = None
    ) -> Any:
        """
        Always get the concrete resolved value (used for metadata).

        Args:
            resource_address: Resource address (e.g., "aws_instance.web")
            property_name: Property name (e.g., "instance_type")
            fallback_value: Value to use if no variable context or resolved value

        Returns:
            The concrete resolved value
        """
        if not self._variable_context:
            return fallback_value

        concrete_value = self._variable_context.get_concrete_value(
            resource_address, property_name
        )
        return concrete_value if concrete_value is not None else fallback_value

    def is_variable_backed(self, resource_address: str, property_name: str) -> bool:
        """
        Check if a property is backed by a Terraform variable.

        Args:
            resource_address: Resource address (e.g., "aws_instance.web")
            property_name: Property name (e.g., "instance_type")

        Returns:
            True if the property references a variable, False otherwise
        """
        if not self._variable_context:
            return False

        return self._variable_context.is_variable_backed(
            resource_address, property_name
        )

    def get_variable_name(
        self, resource_address: str, property_name: str
    ) -> str | None:
        """
        Get the variable name for a property if it's variable-backed.

        Args:
            resource_address: Resource address (e.g., "aws_instance.web")
            property_name: Property name (e.g., "instance_type")

        Returns:
            Variable name if property is variable-backed, None otherwise
        """
        if not self._variable_context:
            return None

        return self._variable_context.get_variable_name(resource_address, property_name)

    def log_property_resolution(
        self, resource_address: str, property_name: str, resolved_value: Any
    ) -> None:
        """
        Log information about property resolution for debugging.

        Args:
            resource_address: Resource address
            property_name: Property name
            resolved_value: The resolved value
        """
        if self.is_variable_backed(resource_address, property_name):
            var_name = self.get_variable_name(resource_address, property_name)
            if isinstance(resolved_value, dict) and "$get_input" in resolved_value:
                self._logger.debug(
                    f"Property {resource_address}.{property_name} -> "
                    f"$get_input:{var_name} (variable-backed)"
                )
            else:
                self._logger.debug(
                    f"Property {resource_address}.{property_name} -> "
                    f"{resolved_value} (concrete value for metadata/context)"
                )
        else:
            self._logger.debug(
                f"Property {resource_address}.{property_name} -> "
                f"{resolved_value} (no variable)"
            )


class TerraformResourceMapperMixin:
    """
    Mixin for existing Terraform resource mappers to add variable support.

    This can be used to retrofit existing mappers without changing their
    inheritance hierarchy.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._variable_context: VariableContext | None = None
        if not hasattr(self, "_logger"):
            self._logger = logger.getChild(self.__class__.__name__)

    def set_variable_context(self, context: "VariableContext | None") -> None:
        """Set the variable context for this mapper."""
        self._variable_context = context

    def resolve_property_value(
        self,
        resource_address: str,
        property_name: str,
        fallback_value: Any = None,
        context: str = "property",
    ) -> Any:
        """Resolve a property value considering variable context."""
        if not self._variable_context:
            return fallback_value

        resolved_value = self._variable_context.resolve_property(
            resource_address, property_name, context
        )
        return resolved_value if resolved_value is not None else fallback_value

    def get_concrete_value(
        self, resource_address: str, property_name: str, fallback_value: Any = None
    ) -> Any:
        """Always get the concrete resolved value (used for metadata)."""
        if not self._variable_context:
            return fallback_value

        concrete_value = self._variable_context.get_concrete_value(
            resource_address, property_name
        )
        return concrete_value if concrete_value is not None else fallback_value

    def is_variable_backed(self, resource_address: str, property_name: str) -> bool:
        """Check if a property is backed by a Terraform variable."""
        if not self._variable_context:
            return False
        return self._variable_context.is_variable_backed(
            resource_address, property_name
        )
