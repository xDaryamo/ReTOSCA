"""
Terraform Variables Support System

This module provides comprehensive support for extracting Terraform variables,
converting them to TOSCA inputs, tracking variable references, and replacing
values with TOSCA get_input functions where appropriate.
"""

import logging
from dataclasses import dataclass
from typing import Any

from .exceptions import (
    OutputMappingError,
    ValidationError,
    VariableExtractionError,
)

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


@dataclass
class OutputDefinition:
    """Represents a Terraform output definition."""

    name: str
    description: str | None = None
    sensitive: bool = False
    value: Any = None
    depends_on: list[str] | None = None


@dataclass
class ToscaOutputDefinition:
    """Represents a TOSCA output parameter definition."""

    name: str
    description: str | None = None
    value: Any = None


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
            parsed_data: The complete Terraform data (with plan and state)

        Returns:
            Dictionary mapping variable name to VariableDefinition
        Raises:
            ValidationError: If parsed_data is invalid.
            VariableExtractionError: If variable extraction fails.
        """
        if not isinstance(parsed_data, dict):
            raise ValidationError("parsed_data must be a dictionary")

        self._logger.info("Extracting Terraform variables from plan")

        variables = {}

        try:
            # Get plan data which contains variable definitions
            plan_data = parsed_data.get("plan", {})
            config = plan_data.get("configuration", {})
            root_module = config.get("root_module", {})
            terraform_vars = root_module.get("variables", {})

            for var_name, var_config in terraform_vars.items():
                if not isinstance(var_config, dict):
                    self._logger.warning(
                        f"Skipping invalid variable config for '{var_name}'"
                    )
                    continue

                var_def = VariableDefinition(
                    name=var_name,
                    var_type=var_config.get("type"),
                    default=var_config.get("default"),
                    description=var_config.get("description"),
                    sensitive=var_config.get("sensitive", False),
                )
                variables[var_name] = var_def
                self._logger.debug(f"Extracted variable '{var_name}': {var_def}")
        except Exception as e:
            raise VariableExtractionError(f"Failed to extract variables: {e}") from e

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
        Raises:
            ValidationError: If variables parameter is invalid.
        """
        if not isinstance(variables, dict):
            raise ValidationError("variables must be a dictionary")

        self._logger.info("Converting Terraform variables to TOSCA inputs")

        tosca_inputs = {}

        for var_name, var_def in variables.items():
            if not isinstance(var_def, VariableDefinition):
                self._logger.warning(
                    f"Skipping invalid variable definition for '{var_name}'"
                )
                continue

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


class OutputExtractor:
    """Extracts Terraform outputs from plan JSON and converts to TOSCA outputs."""

    def __init__(self):
        self._logger = logger.getChild(self.__class__.__name__)

    def extract_outputs(
        self, parsed_data: dict[str, Any]
    ) -> dict[str, OutputDefinition]:
        """
        Extract all Terraform outputs from the plan JSON.

        Args:
            parsed_data: The complete Terraform data (with plan and state)

        Returns:
            Dictionary mapping output name to OutputDefinition
        """
        self._logger.info("Extracting Terraform outputs from plan")

        outputs = {}

        # Get plan data which contains output definitions
        plan_data = parsed_data.get("plan", {})
        config = plan_data.get("configuration", {})
        root_module = config.get("root_module", {})
        terraform_outputs = root_module.get("outputs", {})

        for output_name, output_config in terraform_outputs.items():
            # Extract resolved value from planned_values if available
            resolved_value = self._extract_resolved_output_value(
                parsed_data, output_name
            )

            output_def = OutputDefinition(
                name=output_name,
                description=output_config.get("description"),
                sensitive=output_config.get("sensitive", False),
                value=resolved_value,
                depends_on=output_config.get("depends_on"),
            )
            outputs[output_name] = output_def
            self._logger.debug(f"Extracted output '{output_name}': {output_def}")

        self._logger.info(f"Extracted {len(outputs)} outputs")
        return outputs

    def _extract_resolved_output_value(
        self, parsed_data: dict[str, Any], output_name: str
    ) -> Any:
        """
        Extract resolved output value from planned_values or state.

        Args:
            parsed_data: The complete Terraform data
            output_name: Name of the output to extract

        Returns:
            The resolved value if available, None otherwise
        """
        # First try planned_values from plan data
        plan_data = parsed_data.get("plan", {})
        planned_values = plan_data.get("planned_values", {})
        if "outputs" in planned_values:
            output_data = planned_values["outputs"].get(output_name, {})
            if "value" in output_data:
                return output_data["value"]

        # Then try state data
        state_data = parsed_data.get("state", {})
        values = state_data.get("values", {})
        if "outputs" in values:
            output_data = values["outputs"].get(output_name, {})
            if "value" in output_data:
                return output_data["value"]

        self._logger.debug(f"No resolved value found for output '{output_name}'")
        return None

    def convert_to_tosca_outputs(
        self, outputs: dict[str, OutputDefinition]
    ) -> dict[str, ToscaOutputDefinition]:
        """
        Convert Terraform outputs to TOSCA output definitions.

        Args:
            outputs: Dictionary of Terraform output definitions

        Returns:
            Dictionary mapping output name to ToscaOutputDefinition
        """
        self._logger.info("Converting Terraform outputs to TOSCA outputs")

        tosca_outputs = {}

        for output_name, output_def in outputs.items():
            # Skip sensitive outputs for security
            if output_def.sensitive:
                self._logger.debug(f"Skipping sensitive output '{output_name}'")
                continue

            # Skip outputs without resolved values (e.g., from plan-only scenarios)
            if output_def.value is None:
                self._logger.debug(
                    f"Skipping output '{output_name}' - no resolved value available"
                )
                continue

            tosca_output = ToscaOutputDefinition(
                name=output_name,
                description=output_def.description,
                value=output_def.value,  # Will be processed later by mapping logic
            )
            tosca_outputs[output_name] = tosca_output
            self._logger.debug(
                f"Converted output '{output_name}' to TOSCA output: {tosca_output}"
            )

        self._logger.info(f"Converted {len(tosca_outputs)} outputs to TOSCA outputs")
        return tosca_outputs


class OutputMapper:
    """Maps Terraform outputs to TOSCA outputs with intelligent attribute mapping."""

    def __init__(self, parsed_data: dict[str, Any]):
        self._logger = logger.getChild(self.__class__.__name__)
        self.parsed_data = parsed_data

        # Mapping of Terraform resource types to TOSCA node types and their attributes
        self._resource_attribute_mapping = {
            "aws_instance": {
                "tosca_node_type": "Compute",
                "attribute_mappings": {
                    "private_ip": None,
                    "public_ip": "public_address",
                    "private_dns": None,  # Not available in Simple Profile
                    "public_dns": None,  # Not available in Simple Profile
                    "id": None,  # Not available in Simple Profile
                    "arn": None,  # Not available in Simple Profile
                },
            },
            "aws_vpc": {
                "tosca_node_type": "Network",
                "attribute_mappings": {
                    "id": None,  # Not available in Simple Profile
                    "arn": None,  # Not available in Simple Profile
                    "cidr_block": "cidr",  # Maps to Network.cidr property
                },
            },
            "aws_subnet": {
                "tosca_node_type": "Network",
                "attribute_mappings": {
                    "id": None,
                    "arn": None,
                    "cidr_block": "cidr",
                },
            },
            "aws_s3_bucket": {
                "tosca_node_type": "Storage.ObjectStorage",
                "attribute_mappings": {
                    "id": None,
                    "arn": None,
                    "bucket": "name",  # Maps to ObjectStorage.name property
                },
            },
            # Add more resource types as needed
        }

    def map_output_value(
        self, output_def: OutputDefinition, tosca_nodes: dict[str, str]
    ) -> Any:
        """
        Map a Terraform output value to appropriate TOSCA output value.

        Args:
            output_def: Terraform output definition
            tosca_nodes: Map of Terraform resource addresses to TOSCA node names

        Returns:
            Either a $get_attribute function or hardcoded value
        Raises:
            ValidationError: If parameters are invalid.
            OutputMappingError: If mapping fails.
        """
        if not isinstance(output_def, OutputDefinition):
            raise ValidationError("output_def must be an OutputDefinition instance")
        if not isinstance(tosca_nodes, dict):
            raise ValidationError("tosca_nodes must be a dictionary")

        if output_def.value is None:
            return None

        try:
            # Try to extract resource reference from output expression
            resource_ref, attribute_name = self._extract_resource_reference(
                output_def.name
            )

            if resource_ref and attribute_name:
                # Check if we can map this to a TOSCA attribute
                tosca_attribute = self._map_terraform_attribute_to_tosca(
                    resource_ref, attribute_name
                )

                if tosca_attribute and resource_ref in tosca_nodes:
                    tosca_node_name = tosca_nodes[resource_ref]
                    self._logger.debug(
                        f"Mapping output '{output_def.name}' to get_attribute: "
                        f"[{tosca_node_name}, {tosca_attribute}]"
                    )
                    return {"$get_attribute": [tosca_node_name, tosca_attribute]}
        except Exception as e:
            raise OutputMappingError(
                f"Failed to map output '{output_def.name}': {e}"
            ) from e

        # Fallback to hardcoded value
        self._logger.debug(
            f"Using hardcoded value for output '{output_def.name}': {output_def.value}"
        )
        return output_def.value

    # Note: lru_cache on methods can cause memory leaks but provides
    # performance benefits for output reference extraction.
    def _extract_resource_reference(
        self, output_name: str
    ) -> tuple[str | None, str | None]:
        """
        Extract resource reference and attribute from Terraform output expression.

        Args:
            output_name: Name of the output definition

        Returns:
            Tuple of (resource_address, attribute_name) or (None, None)
        """
        if not output_name:
            return None, None

        try:
            # Look in configuration for output expressions
            plan_data = self.parsed_data.get("plan", {})
            config = plan_data.get("configuration", {})
            root_module = config.get("root_module", {})
            outputs = root_module.get("outputs", {})

            output_config = outputs.get(output_name, {})
            expression = output_config.get("expression", {})

            # Check for direct resource attribute references
            if "references" in expression:
                references = expression["references"]
                # Use next() to find the first matching pattern
                for ref in references:
                    parts = ref.split(".")
                    if len(parts) >= 3:  # resource_type.name.attribute
                        resource_type, resource_name, attribute_name = parts[:3]
                        resource_address = f"{resource_type}.{resource_name}"
                        return resource_address, attribute_name
        except Exception as e:
            self._logger.warning(
                f"Error extracting reference for output '{output_name}': {e}"
            )

        return None, None

    def _map_terraform_attribute_to_tosca(
        self, resource_address: str, terraform_attribute: str
    ) -> str | None:
        """
        Map a Terraform resource attribute to TOSCA node attribute.

        Args:
            resource_address: Terraform resource address (e.g., "aws_instance.web")
            terraform_attribute: Terraform attribute name (e.g., "private_ip")

        Returns:
            TOSCA attribute name if mappable, None otherwise
        """
        resource_type = resource_address.split(".")[0]
        mapping = self._resource_attribute_mapping.get(resource_type, {})
        attribute_mappings = mapping.get("attribute_mappings", {})
        if not isinstance(attribute_mappings, dict):
            return None

        return attribute_mappings.get(terraform_attribute)


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

        try:
            # Get configuration from plan data
            plan_data = self.parsed_data.get("plan", {})
            config = plan_data.get("configuration", {})
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
                        # Use generator expression for more efficient processing
                        var_refs = (
                            ref for ref in references if ref and ref.startswith("var.")
                        )

                        for ref in var_refs:
                            var_name = ref[4:]  # Remove "var." prefix
                            key = (resource_address, prop_name)
                            self._variable_references[key] = var_name
                            self._logger.debug(
                                "Found variable reference: %s.%s -> %s",
                                resource_address,
                                prop_name,
                                var_name,
                            )
        except Exception as e:
            raise VariableExtractionError(f"Failed to build reference map: {e}") from e

        # Build resolved values map from plan data planned_values
        plan_data = self.parsed_data.get("plan", {})
        planned_values = plan_data.get("planned_values", {})
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

        # Initialize output components
        self.output_extractor = OutputExtractor()
        self.output_mapper = OutputMapper(parsed_data)

        # Extract variables and convert to TOSCA inputs
        self.terraform_variables = self.extractor.extract_variables(parsed_data)
        self.tosca_inputs = self.extractor.convert_to_tosca_inputs(
            self.terraform_variables
        )

        # Extract outputs and convert to TOSCA outputs
        self.terraform_outputs = self.output_extractor.extract_outputs(parsed_data)
        self.tosca_outputs = self.output_extractor.convert_to_tosca_outputs(
            self.terraform_outputs
        )

        self._logger.info(
            "Initialized VariableContext with %d variables, %d TOSCA inputs, "
            "%d outputs, %d TOSCA outputs",
            len(self.terraform_variables),
            len(self.tosca_inputs),
            len(self.terraform_outputs),
            len(self.tosca_outputs),
        )

    def has_variables(self) -> bool:
        """Check if the Terraform project has any variables."""
        return len(self.terraform_variables) > 0

    def get_tosca_inputs(self) -> dict[str, ToscaInputDefinition]:
        """Get all TOSCA input definitions."""
        return self.tosca_inputs

    def has_outputs(self) -> bool:
        """Check if the Terraform project has any outputs."""
        return len(self.terraform_outputs) > 0

    def get_tosca_outputs(
        self, tosca_nodes: dict[str, str]
    ) -> dict[str, ToscaOutputDefinition]:
        """
        Get all TOSCA output definitions with mapped values.

        Args:
            tosca_nodes: Map of Terraform resource addresses to TOSCA node names

        Returns:
            Dictionary of TOSCA output definitions with properly mapped values
        """
        mapped_outputs = {}

        for output_name, tosca_output in self.tosca_outputs.items():
            terraform_output = self.terraform_outputs[output_name]
            mapped_value = self.output_mapper.map_output_value(
                terraform_output, tosca_nodes
            )

            # Create new TOSCA output with mapped value
            mapped_output = ToscaOutputDefinition(
                name=output_name,
                description=tosca_output.description,
                value=mapped_value,
            )
            mapped_outputs[output_name] = mapped_output

        return mapped_outputs

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
        self._logger.info(f"Total outputs: {len(self.terraform_outputs)}")
        self._logger.info(f"Total TOSCA outputs: {len(self.tosca_outputs)}")

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

        # Log output information
        for output_name, output_def in self.terraform_outputs.items():
            value_type = "resolved" if output_def.value is not None else "unresolved"
            sensitive_flag = " (sensitive)" if output_def.sensitive else ""
            self._logger.info(f"Output '{output_name}': {value_type}{sensitive_flag}")

        self._logger.info("=== End Variable Usage Summary ===")
