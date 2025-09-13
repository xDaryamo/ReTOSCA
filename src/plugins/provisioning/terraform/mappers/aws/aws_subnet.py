import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.provisioning.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSSubnetMapper(SingleResourceMapper):
    """Map a Terraform 'aws_subnet' resource to a TOSCA Network node.

    This mapper is specific to the 'aws_subnet' resource type.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_subnet'."""
        return resource_type == "aws_subnet"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Perform translation from aws_subnet to tosca.nodes.Network.

        Args:
            resource_name: The name/identifier of the resource
            resource_type: The type/kind of resource (e.g., 'aws_subnet')
            resource_data: The resource configuration data
            builder: The ServiceTemplateBuilder to populate with TOSCA resources
            context: TerraformMappingContext containing dependencies for reference
                extraction
        """
        logger.info("Mapping Subnet resource: '%s'", resource_name)

        # Get resolved values using the context for properties
        if context:
            values = context.get_resolved_values(resource_data, "property")
        else:
            # Fallback to original values if no context available
            values = resource_data.get("values", {})

        if not values:
            logger.warning(
                "Resource '%s' has no 'values' section. Skipping.", resource_name
            )
            return

        # Generate a unique TOSCA node name using array-aware logic
        if context:
            node_name = context.generate_tosca_node_name_from_address(
                resource_name, resource_type
            )
        else:
            # Fallback to base mapper logic
            node_name = BaseResourceMapper.generate_tosca_node_name(
                resource_name, resource_type
            )

        # Extract the clean name for metadata (without the type prefix)
        if "." in resource_name:
            _, clean_name = resource_name.split(".", 1)
        else:
            clean_name = resource_name

        # Create the Network node representing the subnet
        subnet_node = builder.add_node(name=node_name, node_type="Network")

        # Extract AWS Subnet properties and map them to TOSCA Network properties

        # CIDR block of the subnet
        cidr_block = values.get("cidr_block")

        # Availability Zone
        availability_zone = values.get("availability_zone")

        # IPv6 CIDR block
        ipv6_cidr_block = values.get("ipv6_cidr_block")

        # Tags for the subnet
        tags = values.get("tags", {})

        # Map standard TOSCA Network properties

        # CIDR block -> maps directly to the TOSCA 'cidr' property
        if cidr_block:
            subnet_node.with_property("cidr", cidr_block)

        # IPv6 CIDR block - store in metadata since TOSCA Network doesn't have an
        # ipv6_cidr property; the ipv6_cidr_block will be stored in metadata for
        # reference

        # Network name from availability zone or Name tag
        if tags and "Name" in tags:
            subnet_node.with_property("network_name", tags["Name"])
        elif availability_zone:
            subnet_node.with_property("network_name", f"subnet-{availability_zone}")

        # Determine IP version
        ip_version = 4  # Default
        if ipv6_cidr_block:
            if cidr_block:
                ip_version = 4  # Dual stack, prefer IPv4
            else:
                ip_version = 6  # IPv6 only

        subnet_node.with_property("ip_version", ip_version)

        # DHCP is enabled by default in AWS VPCs/Subnets
        subnet_node.with_property("dhcp_enabled", True)

        # Add the standard 'link' capability for Network nodes
        subnet_node.add_capability("link").and_node()

        # Get resolved values specifically for metadata (always concrete values)
        if context:
            metadata_values = context.get_resolved_values(resource_data, "metadata")
        else:
            metadata_values = resource_data.get("values", {})

        # Build metadata containing Terraform and AWS information
        metadata = {}

        # Original resource information
        metadata["original_resource_type"] = resource_type
        metadata["original_resource_name"] = clean_name

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # AWS Subnet specific information - use metadata_values for concrete values
        metadata_availability_zone = metadata_values.get("availability_zone")
        if metadata_availability_zone:
            metadata["aws_availability_zone"] = metadata_availability_zone

        metadata_ipv6_cidr_block = metadata_values.get("ipv6_cidr_block")
        if metadata_ipv6_cidr_block:
            metadata["aws_ipv6_cidr_block"] = metadata_ipv6_cidr_block

        metadata_map_public_ip_on_launch = metadata_values.get(
            "map_public_ip_on_launch"
        )
        if metadata_map_public_ip_on_launch is not None:
            metadata["aws_map_public_ip_on_launch"] = metadata_map_public_ip_on_launch

        metadata_vpc_id = metadata_values.get("vpc_id")
        if metadata_vpc_id:
            metadata["aws_vpc_id"] = metadata_vpc_id

        # AWS Subnet tags - use concrete metadata values
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        # Extract additional AWS info for extra metadata

        # Tags_all (all tags including provider defaults)
        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

        # Customer-owned IP pool (only for Outpost subnets)
        metadata_customer_owned_ipv4_pool = metadata_values.get(
            "customer_owned_ipv4_pool"
        )
        if metadata_customer_owned_ipv4_pool:
            metadata["aws_customer_owned_ipv4_pool"] = metadata_customer_owned_ipv4_pool

        # Map public IP on customer-owned pool
        metadata_map_customer_owned_ip_on_launch = metadata_values.get(
            "map_customer_owned_ip_on_launch"
        )
        if metadata_map_customer_owned_ip_on_launch is not None:
            metadata["aws_map_customer_owned_ip_on_launch"] = (
                metadata_map_customer_owned_ip_on_launch
            )

        # Outpost ARN (present for Outpost subnets)
        metadata_outpost_arn = metadata_values.get("outpost_arn")
        if metadata_outpost_arn:
            metadata["aws_outpost_arn"] = metadata_outpost_arn

        # Subnet ID (populated after creation)
        metadata_subnet_id = metadata_values.get("id")
        if metadata_subnet_id:
            metadata["aws_subnet_id"] = metadata_subnet_id

        # ARN (populated after creation)
        metadata_arn = metadata_values.get("arn")
        if metadata_arn:
            metadata["aws_arn"] = metadata_arn

        # Owner ID (populated after creation)
        metadata_owner_id = metadata_values.get("owner_id")
        if metadata_owner_id:
            metadata["aws_owner_id"] = metadata_owner_id

        # Attach all metadata to the node
        subnet_node.with_metadata(metadata)

        # Add all discovered dependencies using injected context with filtering
        if context:
            # Import DependencyFilter at runtime to avoid circular dependency
            from src.plugins.provisioning.terraform.context import DependencyFilter

            # Create synthetic route table dependencies based on subnet context
            synthetic_dependencies = self._create_synthetic_route_table_dependencies(
                metadata_values, context, resource_name
            )

            # Subnet dependencies are generally clean, but use filtering for consistency
            # No exclusions needed for subnets - they legitimately depend on VPC
            # Include synthetic route table dependencies
            dependency_filter = DependencyFilter(
                synthetic_dependencies=synthetic_dependencies
            )

            terraform_refs = context.extract_filtered_terraform_references(
                resource_data, dependency_filter
            )
            logger.debug(
                f"Found {len(terraform_refs)} terraform references for {resource_name}"
            )

            for prop_name, target_ref, relationship_type in terraform_refs:
                logger.debug(
                    "Processing reference: %s -> %s (%s)",
                    prop_name,
                    target_ref,
                    relationship_type,
                )

                # target_ref is now already resolved to TOSCA node name by context
                target_node_name = target_ref

                # Add requirement with standardized dependency name
                # Map all AWS-specific property names to standard TOSCA dependency
                requirement_name = "dependency"

                (
                    subnet_node.add_requirement(requirement_name)
                    .to_node(target_node_name)
                    .with_relationship(relationship_type)
                    .and_node()
                )

                logger.info(
                    "Added %s requirement '%s' to '%s' with relationship %s",
                    requirement_name,
                    target_node_name,
                    node_name,
                    relationship_type,
                )
        else:
            logger.warning(
                "No context provided to detect dependencies for resource '%s'",
                resource_name,
            )

        logger.debug("Network Subnet node '%s' created successfully.", node_name)

        # Log mapped properties for debugging
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Mapped properties for '{node_name}':")
            logger.debug(f"  - CIDR Block: {cidr_block}")
            logger.debug(f"  - Availability Zone: {metadata_availability_zone}")
            logger.debug(f"  - IPv6 CIDR: {metadata_ipv6_cidr_block}")
            logger.debug(f"  - Public IP on Launch: {metadata_map_public_ip_on_launch}")
            logger.debug(f"  - VPC ID: {metadata_vpc_id}")
            logger.debug(f"  - Tags: {metadata_tags}")
            customer_ip_launch = metadata_map_customer_owned_ip_on_launch
            logger.debug(f"  - Customer-owned IP Launch: {customer_ip_launch}")

    def _create_synthetic_route_table_dependencies(
        self,
        metadata_values: dict[str, Any],
        context: "TerraformMappingContext",
        resource_name: str,
    ) -> list[tuple[str, str, str]]:
        """
        Create synthetic dependencies between subnets and their corresponding
        route tables.

        This method analyzes subnet characteristics (public/private, AZ,
        naming patterns) and finds matching route tables to create DependsOn
        relationships.

        Args:
            metadata_values: Resolved metadata values for the subnet
            context: Terraform mapping context for finding route table resources
            resource_name: Subnet resource name for logging

        Returns:
            List of synthetic dependencies as (prop_name, target_ref,
            relationship_type) tuples
        """
        synthetic_dependencies: list[tuple[str, str, str]] = []

        # Analyze subnet context to determine characteristics
        subnet_context = self._analyze_subnet_context(metadata_values, resource_name)
        if not subnet_context:
            logger.debug(f"Could not determine subnet context for {resource_name}")
            return synthetic_dependencies

        # Find matching route tables based on context
        matching_route_tables = self._find_matching_route_tables(
            subnet_context, context, resource_name
        )

        # Create synthetic dependencies for each matching route table
        for route_table_address in matching_route_tables:
            synthetic_dependencies.append(
                ("dependency", route_table_address, "DependsOn")
            )
            logger.info(
                f"Added synthetic route table dependency: "
                f"{resource_name} -> {route_table_address}"
            )

        return synthetic_dependencies

    def _analyze_subnet_context(
        self, metadata_values: dict[str, Any], resource_name: str
    ) -> dict[str, Any] | None:
        """
        Analyze subnet characteristics to determine context for route table matching.

        Args:
            metadata_values: Resolved metadata values for the subnet
            resource_name: Subnet resource name

        Returns:
            Dictionary containing subnet context information or None if analysis fails
        """
        context = {}

        # Extract availability zone
        availability_zone = metadata_values.get("availability_zone")
        if availability_zone:
            context["availability_zone"] = availability_zone
            # Extract AZ suffix (e.g., "a", "b", "c" from "eu-west-1a")
            if availability_zone and len(availability_zone) > 0:
                context["az_suffix"] = availability_zone[-1]

        # Determine if subnet is public or private based on naming patterns and metadata
        subnet_name = ""
        tags = metadata_values.get("tags", {})
        if tags and "Name" in tags:
            subnet_name = tags["Name"].lower()
            context["name"] = tags["Name"]

        # Analyze resource name for patterns
        resource_name_lower = resource_name.lower()

        # Determine subnet type (public/private)
        if "public" in subnet_name or "public" in resource_name_lower:
            context["type"] = "public"
        elif "private" in subnet_name or "private" in resource_name_lower:
            context["type"] = "private"
        else:
            # Try to infer from map_public_ip_on_launch setting
            map_public_ip = metadata_values.get("map_public_ip_on_launch", False)
            context["type"] = "public" if map_public_ip else "private"

        # Extract module information from resource address
        if "." in resource_name:
            parts = resource_name.split(".")
            if len(parts) > 2 and parts[0] == "module":
                context["module"] = parts[1]

        # Extract VPC ID for additional context
        vpc_id = metadata_values.get("vpc_id")
        if vpc_id:
            context["vpc_id"] = vpc_id

        logger.debug(f"Subnet context for {resource_name}: {context}")
        return context

    def _find_matching_route_tables(
        self,
        subnet_context: dict[str, Any],
        context: "TerraformMappingContext",
        resource_name: str,
    ) -> list[str]:
        """
        Find route tables that match the subnet's context.

        Args:
            subnet_context: Context information about the subnet
            context: Terraform mapping context
            resource_name: Subnet resource name for logging

        Returns:
            List of matching route table addresses
        """
        matching_tables: list[str] = []

        # Get all route table resources from the parsed data
        route_tables = self._get_all_route_tables(context)
        if not route_tables:
            logger.debug(f"No route tables found for matching with {resource_name}")
            return matching_tables

        subnet_type = subnet_context.get("type")
        subnet_az_suffix = subnet_context.get("az_suffix")
        subnet_module = subnet_context.get("module")
        subnet_vpc_id = subnet_context.get("vpc_id")

        logger.debug(
            f"Looking for {subnet_type} route tables matching subnet {resource_name} "
            f"(AZ: {subnet_az_suffix}, Module: {subnet_module}, VPC: {subnet_vpc_id})"
        )

        for route_table_address, route_table_data in route_tables:
            route_table_values = route_table_data.get("values", {})
            route_table_tags = route_table_values.get("tags", {})
            route_table_name = route_table_tags.get("Name", "").lower()
            route_table_vpc_id = route_table_values.get("vpc_id")

            # Skip if not in the same VPC
            if (
                subnet_vpc_id
                and route_table_vpc_id
                and subnet_vpc_id != route_table_vpc_id
            ):
                continue

            # Check module context - route tables should be in the same module
            route_table_module = None
            if "." in route_table_address:
                parts = route_table_address.split(".")
                if len(parts) > 2 and parts[0] == "module":
                    route_table_module = parts[1]

            if (
                subnet_module
                and route_table_module
                and subnet_module != route_table_module
            ):
                continue

            # Match based on subnet type
            route_table_type = None
            if "public" in route_table_name or "public" in route_table_address.lower():
                route_table_type = "public"
            elif (
                "private" in route_table_name
                or "private" in route_table_address.lower()
            ):
                route_table_type = "private"

            # For public subnets, match with public route tables
            if subnet_type == "public" and route_table_type == "public":
                matching_tables.append(route_table_address)
                logger.debug(
                    f"Matched public subnet {resource_name} with public "
                    f"route table {route_table_address}"
                )
                continue

            # For private subnets, prefer route tables with matching AZ suffix
            if subnet_type == "private" and route_table_type == "private":
                # First, try to find exact AZ match
                if subnet_az_suffix:
                    # Check if route table name ends with the AZ suffix (more
                    # precise matching)
                    # Look for patterns like "eu-west-1a", "us-east-1c", etc.
                    if (
                        route_table_name.endswith(subnet_az_suffix)
                        or f"-{subnet_az_suffix}" in route_table_name
                    ):
                        matching_tables.append(route_table_address)
                        logger.debug(
                            f"Matched private subnet {resource_name} with "
                            f"AZ-specific route table {route_table_address}"
                        )
                        break  # Stop searching after finding AZ-specific match

                # Store generic private route table as fallback
                if not any(
                    az_suffix in route_table_name
                    for az_suffix in ["a", "b", "c", "d", "e", "f"]
                ):
                    # Only use if no AZ-specific match was found
                    if not matching_tables:  # Only add if no matches yet
                        matching_tables.append(route_table_address)
                        logger.debug(
                            f"Matched private subnet {resource_name} with "
                            f"generic private route table {route_table_address}"
                        )

        logger.debug(
            f"Found {len(matching_tables)} matching route tables for "
            f"{resource_name}: {matching_tables}"
        )
        return matching_tables

    def _get_all_route_tables(
        self, context: "TerraformMappingContext"
    ) -> list[tuple[str, dict]]:
        """
        Get all route table resources from the parsed data.

        Args:
            context: Terraform mapping context

        Returns:
            List of tuples (route_table_address, route_table_data)
        """
        route_tables: list[tuple[str, dict]] = []

        if not context.parsed_data:
            return route_tables

        # Look in both planned_values and state data
        for data_key in ["planned_values", "state"]:
            if data_key in context.parsed_data:
                if data_key == "planned_values":
                    root_module = context.parsed_data[data_key].get("root_module", {})
                else:
                    # state data
                    state_data = context.parsed_data[data_key]
                    values = state_data.get("values", {})
                    root_module = values.get("root_module", {}) if values else {}

                if root_module:
                    route_tables.extend(
                        self._search_route_tables_in_module(root_module)
                    )

        # Remove duplicates based on address
        unique_tables = []
        seen_addresses = set()
        for address, data in route_tables:
            if address not in seen_addresses:
                unique_tables.append((address, data))
                seen_addresses.add(address)

        return unique_tables

    def _search_route_tables_in_module(
        self, module_data: dict
    ) -> list[tuple[str, dict]]:
        """
        Recursively search for route table resources in a module.

        Args:
            module_data: Module data containing resources

        Returns:
            List of tuples (route_table_address, route_table_data)
        """
        route_tables: list[tuple[str, dict]] = []

        # Search in current module resources
        for resource in module_data.get("resources", []):
            resource_type = resource.get("type")
            resource_address = resource.get("address")

            if resource_type == "aws_route_table" and resource_address:
                route_tables.append((resource_address, resource))

        # Search in child modules
        for child_module in module_data.get("child_modules", []):
            route_tables.extend(self._search_route_tables_in_module(child_module))

        return route_tables
