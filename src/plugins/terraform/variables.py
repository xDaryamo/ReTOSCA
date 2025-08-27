"""
Terraform Variables Support System

This module provides comprehensive support for extracting Terraform variables,
converting them to TOSCA inputs, tracking variable references, and replacing
values with TOSCA get_input functions where appropriate.
"""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class VariableDefinition:
    """Represents a Terraform variable definition."""

    name: str
    var_type: str | None = None
    default: Any = None
    description: str | None = None
    sensitive: bool = False


@dataclass
class ToscaInputDefinition:
    """Represents a TOSCA input parameter definition."""

    name: str
    param_type: str
    description: str | None = None
    default: Any = None
    required: bool = True


class VariableExtractor:
    """Extracts Terraform variables from plan JSON and converts to TOSCA inputs."""

    def __init__(self):
        self._logger = logger.getChild(self.__class__.__name__)

        # Terraform type to TOSCA type mapping
        self._type_mapping = {
            "string": "string",
            "number": "float",  # Conservative choice - can handle both int and float
            "bool": "boolean",
            "list": "list",
            "map": "map",
            "set": "list",  # TOSCA doesn't have set, use list
            # Complex types simplified to map
            "object": "map",
            "tuple": "list",
        }

    def extract_variables(
        self, parsed_data: dict[str, Any]
    ) -> dict[str, VariableDefinition]:
        """
        Extract all Terraform variables from the plan JSON.

        Args:
            parsed_data: The complete Terraform plan JSON

        Returns:
            Dictionary mapping variable name to VariableDefinition
        """
        self._logger.info("Extracting Terraform variables from plan")

        variables = {}
        config = parsed_data.get("configuration", {})
        root_module = config.get("root_module", {})
        terraform_vars = root_module.get("variables", {})

        for var_name, var_config in terraform_vars.items():
            var_def = VariableDefinition(
                name=var_name,
                var_type=var_config.get("type"),
                default=var_config.get("default"),
                description=var_config.get("description"),
                sensitive=var_config.get("sensitive", False),
            )
            variables[var_name] = var_def
            self._logger.debug(f"Extracted variable '{var_name}': {var_def}")

        self._logger.info(f"Extracted {len(variables)} variables")
        return variables

    def convert_to_tosca_inputs(
        self, variables: dict[str, VariableDefinition]
    ) -> dict[str, ToscaInputDefinition]:
        """
        Convert Terraform variables to TOSCA input definitions.

        Args:
            variables: Dictionary of Terraform variable definitions

        Returns:
            Dictionary mapping input name to ToscaInputDefinition
        """
        self._logger.info("Converting Terraform variables to TOSCA inputs")

        tosca_inputs = {}

        for var_name, var_def in variables.items():
            tosca_type = self._map_terraform_type_to_tosca(var_def.var_type)
            required = var_def.default is None  # Required if no default value

            tosca_input = ToscaInputDefinition(
                name=var_name,
                param_type=tosca_type,
                description=var_def.description,
                default=var_def.default,
                required=required,
            )
            tosca_inputs[var_name] = tosca_input
            self._logger.debug(
                f"Converted variable '{var_name}' to TOSCA input: {tosca_input}"
            )

        self._logger.info(f"Converted {len(tosca_inputs)} variables to TOSCA inputs")
        return tosca_inputs

    def _map_terraform_type_to_tosca(self, terraform_type: str | None) -> str:
        """
        Map a Terraform type to a TOSCA type.

        Args:
            terraform_type: Terraform type string (e.g., "string", "list(string)")

        Returns:
            TOSCA type string
        """
        if not terraform_type:
            return "string"  # Default fallback

        # Handle simple types
        if terraform_type in self._type_mapping:
            return self._type_mapping[terraform_type]

        # Handle complex types like list(string), map(string), etc.
        if terraform_type.startswith("list("):
            return "list"
        elif terraform_type.startswith("map("):
            return "map"
        elif terraform_type.startswith("set("):
            return "list"
        elif terraform_type.startswith("object("):
            return "map"
        elif terraform_type.startswith("tuple("):
            return "list"

        # Fallback for unknown types
        self._logger.warning(
            f"Unknown Terraform type '{terraform_type}', using 'string' as fallback"
        )
        return "string"


class VariableReferenceTracker:
    """Tracks which resource properties reference Terraform variables."""

    def __init__(self, parsed_data: dict[str, Any]):
        self._logger = logger.getChild(self.__class__.__name__)
        self.parsed_data = parsed_data

        # Map: (resource_address, property_name) -> variable_name
        self._variable_references: dict[tuple[str, str], str] = {}

        # Map: (resource_address, property_name) -> resolved_value
        self._resolved_values: dict[tuple[str, str], Any] = {}

        self._build_reference_map()

    def _build_reference_map(self):
        """Build the complete map of variable references and resolved values."""
        self._logger.info("Building variable reference map")

        config = self.parsed_data.get("configuration", {})
        root_module = config.get("root_module", {})
        resources = root_module.get("resources", [])

        # Build reference map from configuration
        for resource in resources:
            resource_address = resource.get("address")
            if not resource_address:
                continue

            expressions = resource.get("expressions", {})
            for prop_name, expr_data in expressions.items():
                if isinstance(expr_data, dict) and "references" in expr_data:
                    references = expr_data["references"]
                    for ref in references:
                        if ref and ref.startswith("var."):
                            var_name = ref[4:]  # Remove "var." prefix
                            key = (resource_address, prop_name)
                            self._variable_references[key] = var_name
                            self._logger.debug(
                                "Found variable reference: %s.%s -> %s",
                                resource_address,
                                prop_name,
                                var_name,
                            )

        # Build resolved values map from planned_values
        planned_values = self.parsed_data.get("planned_values", {})
        root_module_planned = planned_values.get("root_module", {})
        self._extract_resolved_values(root_module_planned)

        self._logger.info(
            "Built reference map: %d variable references, %d resolved values",
            len(self._variable_references),
            len(self._resolved_values),
        )

    def _extract_resolved_values(
        self, module_data: dict[str, Any], module_prefix: str = ""
    ):
        """Recursively extract resolved values from planned_values."""
        resources = module_data.get("resources", [])

        for resource in resources:
            resource_address = resource.get("address", "")
            if module_prefix:
                resource_address = f"{module_prefix}.{resource_address}"

            values = resource.get("values", {})
            for prop_name, value in values.items():
                key = (resource_address, prop_name)
                self._resolved_values[key] = value

        # Recurse into child modules
        for child_module in module_data.get("child_modules", []):
            child_address = child_module.get("address", "")
            self._extract_resolved_values(child_module, child_address)

    def is_variable_reference(self, resource_address: str, property_name: str) -> bool:
        """Check if a resource property references a variable."""
        key = (resource_address, property_name)
        return key in self._variable_references

    def get_variable_name(
        self, resource_address: str, property_name: str
    ) -> str | None:
        """Get the variable name referenced by a resource property."""
        key = (resource_address, property_name)
        return self._variable_references.get(key)

    def get_resolved_value(self, resource_address: str, property_name: str) -> Any:
        """Get the resolved (concrete) value for a resource property."""
        key = (resource_address, property_name)
        return self._resolved_values.get(key)

    def should_use_get_input(
        self, resource_address: str, property_name: str, context: str = "property"
    ) -> bool:
        """
        Determine if a property should use $get_input or concrete value.

        Args:
            resource_address: Resource address (e.g., "aws_instance.web")
            property_name: Property name (e.g., "instance_type")
            context: Where the value will be used ("property", "metadata", "attribute")

        Returns:
            True if should use $get_input, False if should use concrete value
        """
        # IMPORTANT EXCEPTION: Never use $get_input in metadata
        if context == "metadata":
            return False

        # Use $get_input if this property references a variable
        return self.is_variable_reference(resource_address, property_name)

    def get_all_variable_references(self) -> dict[tuple[str, str], str]:
        """Get all variable references for debugging/logging."""
        return self._variable_references.copy()


class PropertyResolver:
    """Resolves property values based on variable context."""

    def __init__(self, variable_tracker: VariableReferenceTracker):
        self._logger = logger.getChild(self.__class__.__name__)
        self.variable_tracker = variable_tracker

    def resolve_property_value(
        self, resource_address: str, property_name: str, context: str = "property"
    ) -> Any:
        """
        Resolve a property value, returning either $get_input function or concrete
        value.

        Args:
            resource_address: Resource address (e.g., "aws_instance.web")
            property_name: Property name (e.g., "instance_type")
            context: Context where value will be used
                ("property", "metadata", "attribute")

        Returns:
            Either {"$get_input": "variable_name"} or the concrete resolved value
        """
        should_use_get_input = self.variable_tracker.should_use_get_input(
            resource_address, property_name, context
        )

        if should_use_get_input:
            var_name = self.variable_tracker.get_variable_name(
                resource_address, property_name
            )
            if var_name:
                self._logger.debug(
                    "Using $get_input for %s.%s -> %s",
                    resource_address,
                    property_name,
                    var_name,
                )
                return {"$get_input": var_name}

        # Fall back to concrete resolved value
        resolved_value = self.variable_tracker.get_resolved_value(
            resource_address, property_name
        )
        self._logger.debug(
            "Using concrete value for %s.%s -> %s",
            resource_address,
            property_name,
            resolved_value,
        )
        return resolved_value


class VariableContext:
    """
    Main context class that orchestrates variable support.

    This class provides a unified interface for all variable-related operations
    and is used by the TerraformMapper and individual resource mappers.
    """

    def __init__(self, parsed_data: dict[str, Any]):
        self._logger = logger.getChild(self.__class__.__name__)
        self.parsed_data = parsed_data

        # Initialize components
        self.extractor = VariableExtractor()
        self.reference_tracker = VariableReferenceTracker(parsed_data)
        self.property_resolver = PropertyResolver(self.reference_tracker)

        # Extract variables and convert to TOSCA inputs
        self.terraform_variables = self.extractor.extract_variables(parsed_data)
        self.tosca_inputs = self.extractor.convert_to_tosca_inputs(
            self.terraform_variables
        )

        self._logger.info(
            "Initialized VariableContext with %d variables, %d TOSCA inputs",
            len(self.terraform_variables),
            len(self.tosca_inputs),
        )

    def has_variables(self) -> bool:
        """Check if the Terraform project has any variables."""
        return len(self.terraform_variables) > 0

    def get_tosca_inputs(self) -> dict[str, ToscaInputDefinition]:
        """Get all TOSCA input definitions."""
        return self.tosca_inputs

    def resolve_property(
        self, resource_address: str, property_name: str, context: str = "property"
    ) -> Any:
        """Resolve a property value considering variable context."""
        return self.property_resolver.resolve_property_value(
            resource_address, property_name, context
        )

    def is_variable_backed(self, resource_address: str, property_name: str) -> bool:
        """Check if a property is backed by a variable."""
        return self.reference_tracker.is_variable_reference(
            resource_address, property_name
        )

    def get_concrete_value(self, resource_address: str, property_name: str) -> Any:
        """Always get the concrete resolved value (used for metadata)."""
        return self.reference_tracker.get_resolved_value(
            resource_address, property_name
        )

    def get_variable_name(
        self, resource_address: str, property_name: str
    ) -> str | None:
        """Get the variable name for a property if it's variable-backed."""
        return self.reference_tracker.get_variable_name(resource_address, property_name)

    def log_variable_usage_summary(self):
        """Log a summary of variable usage for debugging."""
        self._logger.info("=== Variable Usage Summary ===")
        self._logger.info(f"Total variables: {len(self.terraform_variables)}")
        self._logger.info(f"Total TOSCA inputs: {len(self.tosca_inputs)}")

        references = self.reference_tracker.get_all_variable_references()
        self._logger.info(f"Total variable references: {len(references)}")

        # Group references by variable
        var_usage = {}
        for (resource_addr, prop_name), var_name in references.items():
            if var_name not in var_usage:
                var_usage[var_name] = []
            var_usage[var_name].append(f"{resource_addr}.{prop_name}")

        for var_name, usages in var_usage.items():
            self._logger.info(f"Variable '{var_name}' used in: {', '.join(usages)}")

        self._logger.info("=== End Variable Usage Summary ===")
