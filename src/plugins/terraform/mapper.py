import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper

from .context import TerraformMappingContext
from .variables import VariableContext

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder

logger = logging.getLogger(__name__)


class TerraformMapper(BaseResourceMapper):
    """
    Terraform-specific mapper.

    Knows how to navigate the JSON produced by
    `terraform show -json` to find all resources defined in the plan.
    """

    def __init__(self) -> None:
        super().__init__()
        # Keep the plan data available for sub-mappers
        self._current_parsed_data: dict[str, Any] | None = None
        # Variable context for handling Terraform variables
        self._variable_context: VariableContext | None = None

    def map(
        self,
        parsed_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
    ) -> None:
        """
        Override to keep parsed_data available to sub-mappers and handle
        two-pass processing with variable support.
        """
        self._current_parsed_data = parsed_data

        # Initialize variable context with combined plan and state data
        self._logger.info("Initializing variable context...")
        self._variable_context = VariableContext(parsed_data)

        # Add TOSCA inputs from Terraform variables
        if self._variable_context.has_variables():
            self._logger.info("Adding TOSCA inputs from Terraform variables")
            tosca_inputs = self._variable_context.get_tosca_inputs()
            for input_name, input_def in tosca_inputs.items():
                input_kwargs = {
                    "default": input_def.default,
                    "required": input_def.required,
                }

                # Only add description if it's not None or empty
                if input_def.description:
                    input_kwargs["description"] = input_def.description

                if input_def.entry_schema:
                    input_kwargs["entry_schema"] = input_def.entry_schema

                builder.with_input(
                    name=input_name,
                    param_type=input_def.param_type,
                    **input_kwargs,
                )
                self._logger.debug(
                    f"Added TOSCA input: {input_name} ({input_def.param_type})"
                )

            # Log variable usage summary for debugging
            self._variable_context.log_variable_usage_summary()
        else:
            self._logger.info(
                "No Terraform variables found, skipping TOSCA input generation"
            )

        # First pass: create all nodes (excluding associations)
        self._logger.info("Starting first pass: creating all primary resources")
        resources = list(self._extract_resources(parsed_data))

        # Track Terraform resource address to TOSCA node name mapping for outputs
        self._tosca_node_mapping: dict[str, str] = {}

        # Separate association resources from primary resources
        primary_resources = []
        association_resources = []

        for resource_name, resource_type, resource_data in resources:
            association_types = ["aws_route_table_association", "aws_volume_attachment"]
            if resource_type in association_types:
                association_resources.append(
                    (resource_name, resource_type, resource_data)
                )
            else:
                primary_resources.append((resource_name, resource_type, resource_data))

        # Process primary resources first
        for resource_name, resource_type, resource_data in primary_resources:
            self._process_single_resource(
                resource_name, resource_type, resource_data, builder
            )

        # Second pass: process associations after all nodes are created
        if association_resources:
            self._logger.info(
                "Starting second pass: processing associations and relationships"
            )
            for resource_name, resource_type, resource_data in association_resources:
                self._process_single_resource(
                    resource_name, resource_type, resource_data, builder
                )

        # Third pass: process outputs after all resources are mapped
        if self._variable_context and self._variable_context.has_outputs():
            self._logger.info("Starting third pass: processing Terraform outputs")
            self._process_outputs(builder)

        self._logger.info("Resource mapping process completed.")

    def _process_single_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
    ) -> None:
        """Process a single resource using the appropriate mapper."""
        mapper_strategy = self._mappers.get(resource_type)

        if mapper_strategy:
            # Uses can_map for a finer check
            if mapper_strategy.can_map(resource_type, resource_data):
                self._logger.debug(
                    f"Mapping resource '{resource_name}' ({resource_type})"
                )

                # Generate TOSCA node name for tracking
                from src.core.common.base_mapper import BaseResourceMapper

                tosca_node_name = BaseResourceMapper.generate_tosca_node_name(
                    resource_name, resource_type
                )

                # Track the mapping for output processing
                self._tosca_node_mapping[resource_name] = tosca_node_name

                # Create context object for dependency injection
                context = TerraformMappingContext(
                    parsed_data=self._current_parsed_data or {},
                    variable_context=self._variable_context,
                )

                # Check if mapper supports context parameter
                import inspect

                sig = inspect.signature(mapper_strategy.map_resource)
                if "context" in sig.parameters:
                    # Delegates work to the specific strategy class with context
                    mapper_strategy.map_resource(
                        resource_name, resource_type, resource_data, builder, context
                    )
                else:
                    # Fallback for mappers that don't support context yet
                    self._logger.debug(
                        f"Mapper {mapper_strategy.__class__.__name__} does not support "
                        "context parameter yet"
                    )
                    mapper_strategy.map_resource(
                        resource_name, resource_type, resource_data, builder
                    )
            else:
                self._logger.warning(
                    f"The mapper for '{resource_type}' cannot handle "
                    f"the specific configuration of '{resource_name}'. "
                    "Skipping."
                )
        else:
            self._logger.warning(
                f"No mapper registered for resource type: '{resource_type}'. Skipping."
            )

    def _process_outputs(self, builder: "ServiceTemplateBuilder") -> None:
        """Process Terraform outputs and add them to the TOSCA service template."""
        if not self._variable_context:
            self._logger.warning("No variable context available for output processing")
            return

        try:
            # Get mapped TOSCA outputs
            tosca_outputs = self._variable_context.get_tosca_outputs(
                self._tosca_node_mapping
            )

            if not tosca_outputs:
                self._logger.info("No outputs to process")
                return

            self._logger.info(f"Processing {len(tosca_outputs)} outputs")

            # Add each output to the service template
            for output_name, tosca_output in tosca_outputs.items():
                output_kwargs = {"value": tosca_output.value}
                if tosca_output.description:
                    output_kwargs["description"] = tosca_output.description

                builder.with_output(name=output_name, **output_kwargs)
                self._logger.debug(f"Added output '{output_name}' to service template")

            self._logger.info("Successfully processed all outputs")

        except Exception as e:
            self._logger.error(f"Error processing outputs: {e}")
            # Don't re-raise - outputs are not critical for basic functionality

    def get_current_parsed_data(self) -> dict[str, Any]:
        """Return current plan data for sub-mappers."""
        return self._current_parsed_data or {}

    def get_variable_context(self) -> VariableContext | None:
        """Return the current variable context for sub-mappers."""
        return self._variable_context

    @staticmethod
    def extract_terraform_references(
        resource_data: dict[str, Any],
        parsed_data: dict[str, Any] | None = None,
    ) -> list[tuple[str, str, str]]:
        """
        Extract all Terraform references from a resource to create TOSCA
        requirements.

        Args:
            resource_data: Single resource data (from state or planned_values).
            parsed_data: Full JSON dict (can be plan or state).

        Returns:
            List of tuples (property_name, target_resource_address, relationship_type),
            e.g., [("vpc_id", "aws_vpc.main", "DependsOn")].
        """
        references: list[tuple[str, str, str]] = []

        if not parsed_data:
            return references

        resource_address = resource_data.get("address")
        if not resource_address:
            return references

        # Try two approaches: configuration (for plans) or depends_on (for state)

        # Approach 1: Extract from configuration (terraform plan JSON)
        configuration = parsed_data.get("configuration", {})
        if configuration:
            references.extend(
                TerraformMapper._extract_from_configuration(
                    resource_address, configuration
                )
            )

        # Approach 2: Extract from depends_on (terraform state JSON)
        depends_on = resource_data.get("depends_on", [])
        if depends_on:
            for dependency in depends_on:
                # dependency is like "aws_vpc.main"
                rel_type = TerraformMapper._determine_terraform_relationship_type(
                    "dependency", dependency
                )
                references.append(("dependency", dependency, rel_type))

        # Approach 3: Infer relationships from property values (only if no explicit
        # depends_on)
        if not depends_on:
            references.extend(
                TerraformMapper._extract_from_property_patterns(
                    resource_data, parsed_data
                )
            )

        # Deduplicate references by target resource to avoid redundant requirements
        unique_references = []
        seen_targets = set()

        for prop_name, target_ref, relationship_type in references:
            if target_ref not in seen_targets:
                unique_references.append((prop_name, target_ref, relationship_type))
                seen_targets.add(target_ref)

        return unique_references

    @staticmethod
    def _extract_from_configuration(
        resource_address: str, configuration: dict[str, Any]
    ) -> list[tuple[str, str, str]]:
        """Extract references from configuration expressions (plan JSON)."""
        references: list[tuple[str, str, str]] = []

        root_module = configuration.get("root_module", {})
        config_resources = root_module.get("resources", [])

        config_resource: dict[str, Any] | None = None
        for config_res in config_resources:
            if config_res.get("address") == resource_address:
                config_resource = config_res
                break

        if not config_resource:
            return references

        # Extract references from the resource's expressions
        expressions = config_resource.get("expressions", {})
        for prop_name, expr_data in expressions.items():
            if isinstance(expr_data, dict) and "references" in expr_data:
                terraform_refs = expr_data["references"]
                for ref in set(terraform_refs):  # avoid duplicates
                    if ref and ref.endswith(".id"):
                        # Strip `.id` to get the clean reference
                        clean_ref = ref[:-3]
                        rel = TerraformMapper._determine_terraform_relationship_type(
                            prop_name, clean_ref
                        )
                        references.append((prop_name, clean_ref, rel))
                    elif ref:
                        rel = TerraformMapper._determine_terraform_relationship_type(
                            prop_name, ref
                        )
                        references.append((prop_name, ref, rel))

        return references

    @staticmethod
    def _extract_from_property_patterns(
        resource_data: dict[str, Any], parsed_data: dict[str, Any]
    ) -> list[tuple[str, str, str]]:
        """Extract relationships from property value patterns."""
        references: list[tuple[str, str, str]] = []

        # Get resource values
        values = resource_data.get("values", {})
        if not values:
            return references

        # Look for common reference patterns in property values
        # For example: vpc_id pointing to an actual VPC
        vpc_id = values.get("vpc_id")
        if vpc_id and isinstance(vpc_id, str):
            # Find the VPC resource that has this ID
            vpc_resource = TerraformMapper._find_resource_by_id(
                parsed_data, vpc_id, "aws_vpc"
            )
            if vpc_resource:
                rel_type = TerraformMapper._determine_terraform_relationship_type(
                    "vpc_id", vpc_resource
                )
                references.append(("ref_vpc_id", vpc_resource, rel_type))

        return references

    @staticmethod
    def _find_resource_by_id(
        parsed_data: dict[str, Any], resource_id: str, resource_type: str
    ) -> str | None:
        """Find a resource address by its ID and type."""
        # Look in structured state data
        state_data = parsed_data.get("state", {})
        values = state_data.get("values", {})
        if values:
            root_module = values.get("root_module", {})
            resources = root_module.get("resources", [])

            for resource in resources:
                if (
                    resource.get("type") == resource_type
                    and resource.get("values", {}).get("id") == resource_id
                ):
                    return resource.get("address")

        return None

    @staticmethod
    def _determine_terraform_relationship_type(
        property_name: str, target_resource: str
    ) -> str:
        """
        Determine the TOSCA relationship type based on a Terraform property
        name and the target resource.
        """
        # Common AWS/Terraform patterns
        if property_name in ["vpc_id", "subnet_id", "subnet_ids"]:
            return "DependsOn"
        if property_name in ["security_group_ids", "security_groups"]:
            # Could be ConnectsTo in some cases
            return "DependsOn"
        if "network" in property_name.lower():
            if "aws_network" in target_resource or "aws_subnet" in target_resource:
                return "LinksTo"  # network connections
            return "DependsOn"
        if property_name in ["load_balancer", "target_group", "load_balancer_arn"]:
            return "ConnectsTo"
        if property_name in ["instance_id", "instance_ids"]:
            return "HostedOn"  # compute-container relationship
        # Generic default
        return "DependsOn"

    def _extract_resources(
        self, parsed_data: dict[str, Any]
    ) -> Iterable[tuple[str, str, dict[str, Any]]]:
        """
        Extract all resources from a Terraform JSON (plan or state).

        Yields:
            (resource_full_address, resource_type, resource_data)
        """
        self._logger.info("Starting extraction of resources from Terraform JSON.")

        # Try to find resources in either planned_values (for plan) or values (for
        # state)
        root_module = None

        # Check for planned state (from plan)
        planned_values = parsed_data.get("planned_values")
        if planned_values:
            root_module = planned_values.get("root_module")
            self._logger.debug("Found 'planned_values' structure (plan JSON)")

        # Check for applied state (from structured state data)
        if not root_module:
            state_data = parsed_data.get("state", {})
            values = state_data.get("values", {})
            if values:
                root_module = values.get("root_module")
                self._logger.debug("Found 'values' structure (state JSON)")

        if not root_module:
            self._logger.warning(
                "No 'planned_values' or 'values' found in JSON. No resources to map."
            )
            return

        # Recurse through modules
        yield from self._find_resources_in_module(root_module)

    def _find_resources_in_module(
        self, module_data: dict[str, Any]
    ) -> Iterable[tuple[str, str, dict[str, Any]]]:
        """Recursively extract resources from a module and its submodules."""
        # 1) Resources in this module
        for resource in module_data.get("resources", []):
            resource_type = resource.get("type")
            resource_name = resource.get("name")
            full_address = resource.get("address")  # e.g., "aws_instance.app_server"

            if not (resource_type and resource_name and full_address):
                continue

            self._logger.debug(
                f"Found resource: {full_address} (Type: {resource_type})"
            )
            # Return full address as name, type, and raw data
            yield full_address, resource_type, resource

        # 2) Recurse into child modules
        for child in module_data.get("child_modules", []):
            yield from self._find_resources_in_module(child)
