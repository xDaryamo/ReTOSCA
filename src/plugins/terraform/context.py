"""
Terraform Mapping Context

This module provides context objects that are passed to individual resource mappers,
eliminating the need for circular dependencies and stack inspection anti-patterns.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .variables import VariableContext


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

        Moved from TerraformMapper static method to eliminate circular dependency.

        Args:
            resource_data: Single resource data (from state or planned_values).

        Returns:
            List of tuples (property_name, target_resource_address, relationship_type),
            e.g., [("vpc_id", "aws_vpc.main", "DependsOn")].
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

        # Deduplicate references by target resource to avoid redundant requirements
        unique_references = []
        seen_targets = set()

        for prop_name, target_ref, relationship_type in references:
            if target_ref not in seen_targets:
                unique_references.append((prop_name, target_ref, relationship_type))
                seen_targets.add(target_ref)

        return unique_references

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
                    if ref and ref.endswith(".id"):
                        # Strip `.id` to get the clean reference
                        clean_ref = ref[:-3]
                        rel = self._determine_terraform_relationship_type(
                            prop_name, clean_ref
                        )
                        references.append((prop_name, clean_ref, rel))
                    elif ref:
                        rel = self._determine_terraform_relationship_type(
                            prop_name, ref
                        )
                        references.append((prop_name, ref, rel))

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
        # Look in values section (state JSON)
        values = self.parsed_data.get("values", {})
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
