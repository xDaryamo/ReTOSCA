"""
Terraform Mapping Context

This module provides context objects that are passed to individual resource mappers,
eliminating the need for circular dependencies and stack inspection anti-patterns.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .variables import VariableContext


@dataclass
class DependencyFilter:
    """
    Configuration for filtering Terraform dependencies during TOSCA mapping.

    Allows mappers to control which dependencies are included, excluded,
    or synthetically added to the TOSCA output.
    """

    # Property names to exclude from dependency extraction
    exclude_properties: set[str] | None = None

    # Resource types to exclude as dependency targets
    exclude_target_types: set[str] | None = None

    # Custom filter function: (prop_name, target_ref, relationship_type) -> bool
    # Return False to exclude the dependency
    custom_filter: Callable[[str, str, str], bool] | None = None

    # Synthetic dependencies to add: [(prop_name, target_ref, relationship_type)]
    synthetic_dependencies: list[tuple[str, str, str]] | None = None


@dataclass
class TerraformMappingContext:
    """
    Context object containing all dependencies needed by individual resource mappers.

    This eliminates the need for single mappers to import TerraformMapper directly,
    breaking circular dependencies while providing access to shared utilities.
    """

    parsed_data: dict[str, Any]
    variable_context: "VariableContext | None"

    def extract_terraform_references(
        self, resource_data: dict[str, Any]
    ) -> list[tuple[str, str, str]]:
        """
        Extract all Terraform references from a resource to create TOSCA requirements.

        This is the original method that extracts all dependencies without filtering.
        For most use cases, use extract_filtered_terraform_references() instead.
        """
        return self._do_extract_terraform_references(resource_data, None)

    def extract_filtered_terraform_references(
        self,
        resource_data: dict[str, Any],
        dependency_filter: DependencyFilter | None = None,
    ) -> list[tuple[str, str, str]]:
        """
        Extract Terraform references with intelligent filtering support.

        This method allows mappers to control which dependencies are included
        in the final TOSCA output through filtering rules and synthetic dependencies.

        Args:
            resource_data: Single resource data (from state or planned_values).
            dependency_filter: Optional filter configuration for
                controlling dependencies.

        Returns:
            List of tuples (property_name, target_resource_address, relationship_type),
            e.g., [("vpc_id", "aws_vpc.main", "DependsOn")].
        """
        return self._do_extract_terraform_references(resource_data, dependency_filter)

    def _do_extract_terraform_references(
        self, resource_data: dict[str, Any], dependency_filter: DependencyFilter | None
    ) -> list[tuple[str, str, str]]:
        """
        Internal method to extract and filter Terraform references.
        """
        references: list[tuple[str, str, str]] = []

        if not self.parsed_data:
            return references

        resource_address = resource_data.get("address")
        if not resource_address:
            return references

        # Try two approaches: configuration (for plans) or depends_on (for state)

        # Approach 1: Extract from configuration (terraform plan JSON)
        configuration = self.parsed_data.get("configuration", {})
        if not configuration:
            # Try to get configuration from plan sub-object
            plan_data = self.parsed_data.get("plan", {})
            configuration = plan_data.get("configuration", {})

        if configuration:
            references.extend(
                self._extract_from_configuration(resource_address, configuration)
            )

        # Approach 2: Extract from depends_on (terraform state JSON)
        depends_on = resource_data.get("depends_on", [])
        if depends_on:
            for dependency in depends_on:
                # dependency is like "aws_vpc.main"
                rel_type = self._determine_terraform_relationship_type(
                    "dependency", dependency
                )
                references.append(("dependency", dependency, rel_type))

        # Approach 3: Infer relationships from property patterns (only if no
        # explicit depends_on)
        if not depends_on:
            references.extend(self._extract_from_property_patterns(resource_data))

        # Apply filtering if specified
        if dependency_filter:
            references = self._apply_dependency_filter(references, dependency_filter)

        # Resolve references to actual TOSCA node names and deduplicate
        resolved_references = []
        seen_targets = set()

        for prop_name, target_ref, relationship_type in references:
            # Check if this is a variable reference
            is_variable_ref = (
                target_ref.startswith("var.")
                or target_ref.startswith("local.")
                or target_ref.startswith("data.")
            )
            if is_variable_ref:
                # For variable/data references, keep the original reference string
                if target_ref not in seen_targets:
                    resolved_references.append(
                        (prop_name, target_ref, relationship_type)
                    )
                    seen_targets.add(target_ref)
            else:
                # For resource references, resolve to TOSCA node name
                tosca_target = self.resolve_array_reference_with_context(
                    resource_data, target_ref
                )

                if tosca_target and tosca_target not in seen_targets:
                    resolved_references.append(
                        (prop_name, tosca_target, relationship_type)
                    )
                    seen_targets.add(tosca_target)

        # Add synthetic dependencies if specified
        if dependency_filter and dependency_filter.synthetic_dependencies:
            for (
                prop_name,
                target_ref,
                relationship_type,
            ) in dependency_filter.synthetic_dependencies:
                # Resolve synthetic target references
                tosca_target = self.resolve_array_reference_with_context(
                    resource_data, target_ref
                )
                if tosca_target and tosca_target not in seen_targets:
                    resolved_references.append(
                        (prop_name, tosca_target, relationship_type)
                    )
                    seen_targets.add(tosca_target)

        return resolved_references

    def _extract_from_configuration(
        self, resource_address: str, configuration: dict[str, Any]
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
                    if not ref:
                        continue

                    # Clean up the reference by removing .id suffix if present
                    clean_ref = ref
                    if ref.endswith(".id"):
                        clean_ref = ref[:-3]

                    # Parse the reference to better understand its structure
                    components = (
                        TerraformMappingContext.parse_terraform_resource_address(
                            clean_ref
                        )
                    )

                    # If this is a valid resource reference, determine relationship type
                    if components["type"] and components["name"]:
                        rel = self._determine_terraform_relationship_type(
                            prop_name, clean_ref
                        )
                        references.append((prop_name, clean_ref, rel))

        return references

    def _extract_from_property_patterns(
        self, resource_data: dict[str, Any]
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
            vpc_resource = self._find_resource_by_id(vpc_id, "aws_vpc")
            if vpc_resource:
                rel_type = self._determine_terraform_relationship_type(
                    "vpc_id", vpc_resource
                )
                references.append(("ref_vpc_id", vpc_resource, rel_type))

        return references

    def _find_resource_by_id(self, resource_id: str, resource_type: str) -> str | None:
        """Find a resource address by its ID and type."""
        # Look in structured state data
        state_data = self.parsed_data.get("state", {})
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

    def get_resolved_values(
        self, resource_data: dict[str, Any], context: str = "property"
    ) -> dict[str, Any]:
        """
        Get resolved values for a resource, handling variable references appropriately.

        Args:
            resource_data: Single resource data (from state or planned_values)
            context: Context for resolution ("property", "metadata", "attribute")
                - "property": May return $get_input for variable references
                - "metadata": Always returns concrete values
                - "attribute": May return $get_input for variable references

        Returns:
            Dictionary of resolved values where variable references are handled
            according to the context
        """
        original_values = resource_data.get("values", {})
        if not original_values:
            return {}

        if not self.variable_context:
            # No variable context available, return original values
            return original_values

        resource_address = resource_data.get("address")
        if not resource_address:
            # No resource address, can't resolve variables
            return original_values

        resolved_values = {}

        for prop_name, original_value in original_values.items():
            resolved_value = self.variable_context.resolve_property(
                resource_address, prop_name, context
            )

            # If resolution didn't change the value, use the original
            if resolved_value is None:
                resolved_values[prop_name] = original_value
            else:
                resolved_values[prop_name] = resolved_value

        return resolved_values

    def _determine_terraform_relationship_type(
        self, property_name: str, target_resource: str
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

    # --- Helper methods for resource address parsing ---

    @staticmethod
    def parse_terraform_resource_address(resource_address: str) -> dict[str, str]:
        """
        Parse a Terraform resource address into components.

        Examples:
        - "aws_eip.nat" ->
          {"module": None, "type": "aws_eip", "name": "nat", "index": None}
        - "module.vpc.aws_eip.nat[0]" ->
          {"module": "module.vpc", "type": "aws_eip", "name": "nat", "index": "0"}
        - "module.vpc.aws_nat_gateway.this[1]" ->
          {
              "module": "module.vpc",
              "type": "aws_nat_gateway",
              "name": "this",
              "index": "1"
          }

        Args:
            resource_address: Full Terraform resource address

        Returns:
            Dictionary with parsed components: module, type, name, index
        """
        components: dict[str, str] = {"module": "", "type": "", "name": "", "index": ""}

        if not resource_address:
            return components

        # Handle array index [n] at the end
        if "[" in resource_address and "]" in resource_address:
            # Extract index
            index_start = resource_address.rfind("[")
            index_end = resource_address.rfind("]")
            if index_start < index_end:
                components["index"] = resource_address[index_start + 1 : index_end]
                resource_address = resource_address[:index_start]

        # Split by dots
        parts = resource_address.split(".")

        if len(parts) >= 2:
            # Check if it starts with "module."
            if parts[0] == "module" and len(parts) >= 4:
                # module.vpc.aws_eip.nat format
                components["module"] = f"{parts[0]}.{parts[1]}"
                components["type"] = parts[2]
                components["name"] = parts[3]
            else:
                # Direct resource: aws_eip.nat format
                components["type"] = parts[0]
                components["name"] = parts[1]

        return components

    @staticmethod
    def generate_tosca_node_name_from_address(
        resource_address: str, resource_type: str | None = None
    ) -> str:
        """
        Generate a TOSCA node name from a Terraform resource address.

        Args:
            resource_address: Full Terraform resource address
            resource_type: Optional resource type (if not in address)

        Returns:
            TOSCA-compatible node name
        """
        components = TerraformMappingContext.parse_terraform_resource_address(
            resource_address
        )

        # Use provided resource_type if components didn't extract it
        if not components["type"] and resource_type:
            components["type"] = resource_type

        # Build the TOSCA node name
        parts = []

        # Add module prefix if present
        if components["module"]:
            module_clean = components["module"].replace(".", "_")
            parts.append(module_clean)

        # Add resource type
        if components["type"]:
            parts.append(components["type"])

        # Add resource name
        if components["name"]:
            name_clean = (
                components["name"]
                .replace("-", "_")
                .replace("[", "_")
                .replace("]", "")
                .replace('"', "")
                .replace("'", "")
                .replace(" ", "_")
            )
            parts.append(name_clean)

        # Add index if present
        if components["index"]:
            parts.append(components["index"])

        return "_".join(parts) if parts else "unknown_resource"

    def resolve_terraform_reference_to_tosca_node(
        self, terraform_ref: str
    ) -> str | None:
        """
        Resolve a Terraform resource reference to the corresponding TOSCA node name.

        This method attempts to find the actual TOSCA node name for a given Terraform
        resource reference, handling array indices properly.

        Args:
            terraform_ref: Terraform resource reference
                (e.g., "module.vpc.aws_eip.nat[0]")

        Returns:
            TOSCA node name if found, None if not resolvable
        """
        if not terraform_ref:
            return None

        # First, try to find the resource in the parsed data to get the exact address
        exact_address = self._find_exact_resource_address(terraform_ref)
        if exact_address:
            # Generate TOSCA node name from the exact address
            components = TerraformMappingContext.parse_terraform_resource_address(
                exact_address
            )
            if components["type"]:
                return TerraformMappingContext.generate_tosca_node_name_from_address(
                    exact_address, components["type"]
                )

        # Only generate TOSCA node names for resources that actually exist
        # Return None if the resource cannot be found in the parsed data
        return None

    def _find_exact_resource_address(self, terraform_ref: str) -> str | None:
        """
        Find the exact resource address in the parsed data that matches the reference.

        This is important for handling cases where the reference might be to an array
        resource but we need the specific indexed address.

        Args:
            terraform_ref: Terraform resource reference

        Returns:
            Exact resource address if found, None otherwise
        """
        if not self.parsed_data:
            return None

        # Look in both planned_values and state data
        for data_key in ["planned_values", "state"]:
            if data_key in self.parsed_data:
                if data_key == "planned_values":
                    root_module = self.parsed_data[data_key].get("root_module", {})
                else:
                    # state data
                    state_data = self.parsed_data[data_key]
                    values = state_data.get("values", {})
                    root_module = values.get("root_module", {}) if values else {}

                if root_module:
                    exact_address = self._search_resources_for_reference(
                        root_module, terraform_ref
                    )
                    if exact_address:
                        return exact_address

        return None

    def _search_resources_for_reference(
        self, module_data: dict, terraform_ref: str
    ) -> str | None:
        """
        Recursively search for a resource that matches the reference.

        Args:
            module_data: Module data containing resources
            terraform_ref: Terraform resource reference to find

        Returns:
            Exact resource address if found, None otherwise
        """
        # Parse the reference components
        ref_components = TerraformMappingContext.parse_terraform_resource_address(
            terraform_ref
        )

        # Search in current module resources
        for resource in module_data.get("resources", []):
            resource_address = resource.get("address", "")
            if not resource_address:
                continue

            # Parse resource address components
            res_components = TerraformMappingContext.parse_terraform_resource_address(
                resource_address
            )

            # Check if this resource matches the reference
            if self._components_match(ref_components, res_components):
                return resource_address

        # Search in child modules
        for child_module in module_data.get("child_modules", []):
            result = self._search_resources_for_reference(child_module, terraform_ref)
            if result:
                return result

        return None

    def _components_match(self, ref_components: dict, res_components: dict) -> bool:
        """
        Check if reference components match resource components.

        This handles cases where the reference might not have an index but
        the resource does, or vice versa.

        Args:
            ref_components: Components from the reference
            res_components: Components from the resource

        Returns:
            True if components match, False otherwise
        """
        # Type and name must match
        if (
            ref_components["type"] != res_components["type"]
            or ref_components["name"] != res_components["name"]
        ):
            return False

        # Module must match (both None or both same value)
        if ref_components["module"] != res_components["module"]:
            return False

        # If both have indices, they must match
        if ref_components["index"] and res_components["index"]:
            return ref_components["index"] == res_components["index"]

        # If reference has no index but resource does, it could be a match
        # (reference to array without specific index)
        return True

    def _apply_dependency_filter(
        self,
        references: list[tuple[str, str, str]],
        dependency_filter: DependencyFilter,
    ) -> list[tuple[str, str, str]]:
        """
        Apply dependency filtering rules to the extracted references.

        Args:
            references: List of (prop_name, target_ref, relationship_type) tuples
            dependency_filter: Filter configuration

        Returns:
            Filtered list of references
        """
        filtered_references = []

        for prop_name, target_ref, relationship_type in references:
            # Check property exclusions
            if dependency_filter.exclude_properties:
                if prop_name in dependency_filter.exclude_properties:
                    continue

            # Check target type exclusions
            if dependency_filter.exclude_target_types:
                # Extract resource type from target reference using proper parsing
                components = TerraformMappingContext.parse_terraform_resource_address(
                    target_ref
                )
                target_type = components.get("type")
                if (
                    target_type
                    and target_type in dependency_filter.exclude_target_types
                ):
                    continue

            # Apply custom filter if specified
            if dependency_filter.custom_filter:
                if not dependency_filter.custom_filter(
                    prop_name, target_ref, relationship_type
                ):
                    continue

            # If we made it here, include the reference
            filtered_references.append((prop_name, target_ref, relationship_type))

        return filtered_references

    def resolve_array_reference_with_context(
        self, resource_data: dict, terraform_ref: str
    ) -> str | None:
        """
        Resolve a Terraform reference considering array index context from the source
        resource.

        When an array resource references another array resource without specifying an
        index, we try to infer the correct index based on the source resource's index.

        Args:
            resource_data: Data of the resource making the reference
            terraform_ref: Terraform resource reference to resolve

        Returns:
            TOSCA node name of the target resource, None if not resolvable
        """
        if not terraform_ref:
            return None

        # Get the address of the source resource
        source_address = resource_data.get("address", "")
        if not source_address:
            return self.resolve_terraform_reference_to_tosca_node(terraform_ref)

        # Parse source resource components
        source_components = TerraformMappingContext.parse_terraform_resource_address(
            source_address
        )

        # Parse reference components
        ref_components = TerraformMappingContext.parse_terraform_resource_address(
            terraform_ref
        )

        # If source has an index but reference doesn't, try to apply the same index
        if source_components["index"] and not ref_components["index"]:
            # Try to find the target resource with the same index
            indexed_ref = f"{terraform_ref}[{source_components['index']}]"

            # Check if this indexed resource exists
            exact_address = self._find_exact_resource_address(indexed_ref)
            if exact_address:
                return TerraformMappingContext.generate_tosca_node_name_from_address(
                    exact_address, ref_components["type"]
                )

            # If indexed resource doesn't exist, try to find the unindexed resource
            # (index 0)
            unindexed_ref_with_0 = f"{terraform_ref}[0]"
            exact_address_0 = self._find_exact_resource_address(unindexed_ref_with_0)
            if exact_address_0:
                return TerraformMappingContext.generate_tosca_node_name_from_address(
                    exact_address_0, ref_components["type"]
                )

            # If neither indexed nor index-0 resource exists,
            # try the original unindexed reference
            exact_address_orig = self._find_exact_resource_address(terraform_ref)
            if exact_address_orig:
                return TerraformMappingContext.generate_tosca_node_name_from_address(
                    exact_address_orig, ref_components["type"]
                )

        # No special array handling needed, use standard resolution
        return self.resolve_terraform_reference_to_tosca_node(terraform_ref)
