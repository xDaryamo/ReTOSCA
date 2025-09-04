import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSRouteTableMapper(SingleResourceMapper):
    """Map a Terraform 'aws_route_table' resource to a TOSCA Network node.

    A Route Table defines routing rules for network traffic within a VPC.
    It's mapped as a Network node with routing-specific properties and metadata.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_route_table'."""
        _ = resource_data  # Parameter required by protocol but not used
        return resource_type == "aws_route_table"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Translate an aws_route_table resource into a TOSCA Network node.

        Args:
            resource_name: resource name (e.g. 'aws_route_table.example')
            resource_type: resource type (always 'aws_route_table')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
        """
        logger.info("Mapping Route Table resource: '%s'", resource_name)

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

        # Create the Route Table node as a Network node
        route_table_node = builder.add_node(name=node_name, node_type="Network")

        # Extract AWS Route Table properties and map them to TOSCA Network properties

        # Routes configuration
        routes = values.get("route", [])

        # Tags for the route table
        tags = values.get("tags", {})

        # Map standard TOSCA Network properties

        # Set Network properties (only standard TOSCA Simple Profile properties)
        if tags and "Name" in tags:
            route_table_node.with_property("network_name", tags["Name"])
        else:
            route_table_node.with_property("network_name", clean_name)

        # Set network type to indicate this is a routing network
        route_table_node.with_property("network_type", "routing")

        # Process routes to determine IP version
        processed_routes = []
        if routes:
            processed_routes = self._process_routes(routes)

        # Set IP version based on routes (default to 4, set to 6 if IPv6 routes exist)
        has_ipv6_routes = any(
            route.get("destination_type") == "ipv6_cidr" for route in processed_routes
        )
        route_table_node.with_property("ip_version", 6 if has_ipv6_routes else 4)

        # DHCP is enabled by default in AWS VPCs/Route Tables
        route_table_node.with_property("dhcp_enabled", True)

        # Add the standard 'link' capability for Network nodes
        route_table_node.add_capability("link").and_node()

        # Get resolved values specifically for metadata (always concrete values)
        if context:
            metadata_values = context.get_resolved_values(resource_data, "metadata")
        else:
            metadata_values = resource_data.get("values", {})

        # Build metadata containing Terraform and AWS information
        metadata: dict[str, Any] = {}

        # Original resource information
        metadata["original_resource_type"] = resource_type
        metadata["original_resource_name"] = clean_name
        metadata["aws_component_type"] = "RouteTable"
        metadata["description"] = "AWS Route Table defining network routing rules"

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # AWS Route Table specific information - use metadata_values for concrete values
        metadata_vpc_id = metadata_values.get("vpc_id")
        if metadata_vpc_id:
            metadata["aws_vpc_id"] = metadata_vpc_id

        # Process routes for metadata
        metadata_routes = metadata_values.get("route", [])
        if metadata_routes:
            metadata_processed_routes = self._process_routes(metadata_routes)
            metadata["aws_routes"] = metadata_processed_routes
            metadata["aws_route_count"] = len(metadata_routes)

        # Propagating VGWs (Virtual Gateways)
        metadata_propagating_vgws = metadata_values.get("propagating_vgws", [])
        if metadata_propagating_vgws:
            metadata["aws_propagating_vgws"] = metadata_propagating_vgws

        # AWS Route Table tags - use concrete metadata values
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags
            # Use Name tag if available
            if "Name" in metadata_tags:
                metadata["aws_name"] = metadata_tags["Name"]

        # Extract additional AWS info for extra metadata

        # Tags_all (all tags including provider defaults)
        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

        # Region information
        metadata_region = metadata_values.get("region")
        if metadata_region:
            metadata["aws_region"] = metadata_region

        # Owner ID (populated after creation)
        metadata_owner_id = metadata_values.get("owner_id")
        if metadata_owner_id:
            metadata["aws_owner_id"] = metadata_owner_id

        # Route Table ID (populated after creation)
        metadata_route_table_id = metadata_values.get("id")
        if metadata_route_table_id:
            metadata["aws_route_table_id"] = metadata_route_table_id

        # Associations (populated after creation)
        metadata_associations = metadata_values.get("associations", [])
        if metadata_associations:
            metadata["aws_associations"] = metadata_associations

        # Attach all metadata to the node
        route_table_node.with_metadata(metadata)

        # Add the standard 'link' capability for Network nodes
        route_table_node.add_capability("link").and_node()

        # Add dependencies using injected context with synthetic default route
        # dependencies
        if context:
            # Import DependencyFilter at runtime to avoid circular dependency
            from src.plugins.terraform.context import DependencyFilter

            # Analyze routes to create synthetic default route dependencies
            synthetic_dependencies = self._create_synthetic_default_route_dependencies(
                metadata_values, context, resource_name
            )

            # Create filter with synthetic dependencies for default routes
            dependency_filter = DependencyFilter(
                synthetic_dependencies=synthetic_dependencies
            )

            terraform_refs = context.extract_filtered_terraform_references(
                resource_data, dependency_filter
            )
            logger.debug(
                f"Found {len(terraform_refs)} terraform references "
                f"(including synthetic) for {resource_name}"
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

                # Add requirement with the property name as the requirement name
                requirement_name = (
                    prop_name if prop_name not in ["dependency"] else "dependency"
                )

                (
                    route_table_node.add_requirement(requirement_name)
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

        logger.debug(f"Route Table Network node '{node_name}' created successfully.")

        # Log mapped properties for debugging
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Mapped properties for '{node_name}':")
            logger.debug(f"  - VPC ID: {metadata_vpc_id}")
            logger.debug(f"  - Routes: {len(metadata_routes)}")
            logger.debug(f"  - Propagating VGWs: {metadata_propagating_vgws}")
            logger.debug(f"  - Tags: {metadata_tags}")
            logger.debug(f"  - Region: {metadata_region}")

    def _process_routes(self, routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Process and clean route information for metadata."""
        processed_routes = []

        for route in routes:
            processed_route = {}

            # Destination information
            if route.get("cidr_block"):
                processed_route["destination"] = route["cidr_block"]
                processed_route["destination_type"] = "ipv4_cidr"
            elif route.get("ipv6_cidr_block"):
                processed_route["destination"] = route["ipv6_cidr_block"]
                processed_route["destination_type"] = "ipv6_cidr"
            elif route.get("destination_prefix_list_id"):
                processed_route["destination"] = route["destination_prefix_list_id"]
                processed_route["destination_type"] = "prefix_list"

            # Target information
            target_fields = [
                "gateway_id",
                "nat_gateway_id",
                "network_interface_id",
                "transit_gateway_id",
                "vpc_endpoint_id",
                "vpc_peering_connection_id",
                "egress_only_gateway_id",
                "carrier_gateway_id",
                "core_network_arn",
                "local_gateway_id",
            ]

            for field in target_fields:
                if route.get(field):
                    processed_route["target"] = route[field]
                    processed_route["target_type"] = field
                    break

            if processed_route:
                processed_routes.append(processed_route)

        return processed_routes

    def _create_synthetic_default_route_dependencies(
        self,
        metadata_values: dict[str, Any],
        context: "TerraformMappingContext",
        resource_name: str,
    ) -> list[tuple[str, str, str]]:
        """
        Analyze route table routes to create synthetic default route dependencies.

        Creates dependencies for default routes (0.0.0.0/0) to their targets:
        - Public route tables -> Internet Gateway
        - Private route tables -> NAT Gateway (matching AZ if possible)

        Enhanced to handle both explicit and implicit routing relationships.

        Args:
            metadata_values: Resolved metadata values for the route table
            context: Terraform mapping context for finding target resources
            resource_name: Route table resource name for logging

        Returns:
            List of synthetic dependencies as (prop_name, target_ref,
            relationship_type) tuples
        """
        synthetic_dependencies = []

        # Get routes from metadata
        routes = metadata_values.get("route", [])

        # First, try to find explicit default routes
        explicit_route_found = False
        if routes:
            # Analyze each route to find default routes
            for route in routes:
                # Check if this is a default route (0.0.0.0/0)
                cidr_block = route.get("cidr_block")
                if cidr_block != "0.0.0.0/0":
                    continue

                # Found a default route, determine the target
                target_address = self._find_default_route_target(route, context)
                if target_address:
                    synthetic_dependencies.append(
                        ("default_route", target_address, "DependsOn")
                    )
                    logger.info(
                        f"Added synthetic default route dependency: "
                        f"{resource_name} -> {target_address}"
                    )
                    explicit_route_found = True

        # If no explicit default routes found, infer based on route table type
        if not explicit_route_found:
            logger.debug(
                f"No explicit default routes found for {resource_name}, "
                f"attempting inference"
            )
            inferred_dependencies = self._infer_route_table_dependencies(
                metadata_values, context, resource_name
            )
            synthetic_dependencies.extend(inferred_dependencies)

        return synthetic_dependencies

    def _find_default_route_target(
        self, route: dict[str, Any], context: "TerraformMappingContext"
    ) -> str | None:
        """
        Find the target resource for a default route.

        Args:
            route: Route configuration from route table
            context: Terraform mapping context for finding resources

        Returns:
            Target resource address if found, None otherwise
        """
        # Check for Internet Gateway
        gateway_id = route.get("gateway_id")
        if gateway_id and gateway_id.startswith("igw-"):
            return self._find_resource_by_aws_id(
                context, gateway_id, "aws_internet_gateway"
            )

        # Check for NAT Gateway
        nat_gateway_id = route.get("nat_gateway_id")
        if nat_gateway_id and nat_gateway_id.startswith("nat-"):
            return self._find_resource_by_aws_id(
                context, nat_gateway_id, "aws_nat_gateway"
            )

        # Check for other gateway types
        if gateway_id and gateway_id.startswith("nat-"):
            return self._find_resource_by_aws_id(context, gateway_id, "aws_nat_gateway")

        return None

    def _find_resource_by_aws_id(
        self,
        context: "TerraformMappingContext",
        aws_id: str,
        resource_type: str,
    ) -> str | None:
        """
        Find a Terraform resource address by its AWS ID and type.

        Args:
            context: Terraform mapping context containing parsed data
            aws_id: AWS resource ID (e.g., 'igw-123abc', 'nat-456def')
            resource_type: Resource type (e.g., 'aws_internet_gateway',
                'aws_nat_gateway')

        Returns:
            Terraform resource address or None if not found
        """
        try:
            # Look in state data first
            state_data = context.parsed_data.get("state", {})
            if state_data:
                values = state_data.get("values", {})
                if values:
                    root_module = values.get("root_module", {})
                    resources = root_module.get("resources", [])

                    for resource in resources:
                        if resource.get("type") == resource_type:
                            resource_values = resource.get("values", {})
                            if resource_values.get("id") == aws_id:
                                return resource.get("address")

            # Also check in planned values
            planned_values = context.parsed_data.get("planned_values", {})
            if planned_values:
                root_module = planned_values.get("root_module", {})
                resources = root_module.get("resources", [])

                for resource in resources:
                    if resource.get("type") == resource_type:
                        resource_values = resource.get("values", {})
                        if resource_values.get("id") == aws_id:
                            return resource.get("address")

        except Exception as e:
            logger.debug(
                f"Error finding resource {resource_type} with ID {aws_id}: {e}"
            )

        return None

    def _infer_route_table_dependencies(
        self,
        metadata_values: dict[str, Any],
        context: "TerraformMappingContext",
        resource_name: str,
    ) -> list[tuple[str, str, str]]:
        """
        Infer route table dependencies based on route table characteristics.

        This handles cases where route tables don't have explicit default routes
        but should logically depend on gateways based on their type (public/private).

        Args:
            metadata_values: Resolved metadata values for the route table
            context: Terraform mapping context for finding target resources
            resource_name: Route table resource name for logging

        Returns:
            List of inferred dependencies as (prop_name, target_ref,
            relationship_type) tuples
        """
        inferred_dependencies = []

        # Classify route table as public or private
        is_public = self._classify_route_table_type(metadata_values, resource_name)

        if is_public:
            logger.debug(f"Classified {resource_name} as public route table")
            # Find Internet Gateway for this VPC
            vpc_id = metadata_values.get("vpc_id")
            if vpc_id:
                igw_address = self._find_internet_gateway_for_vpc(context, vpc_id)
                if igw_address:
                    inferred_dependencies.append(
                        ("dependency", igw_address, "DependsOn")
                    )
                    logger.info(
                        f"Inferred Internet Gateway dependency: "
                        f"{resource_name} -> {igw_address}"
                    )
                else:
                    logger.warning(
                        f"Could not find Internet Gateway for public route table "
                        f"{resource_name}"
                    )
        else:
            logger.debug(f"Classified {resource_name} as private route table")
            # Find appropriate NAT Gateway
            nat_gateway_address = self._find_nat_gateway_for_private_route_table(
                metadata_values, context, resource_name
            )
            if nat_gateway_address:
                inferred_dependencies.append(
                    ("dependency", nat_gateway_address, "DependsOn")
                )
                logger.info(
                    f"Inferred NAT Gateway dependency: "
                    f"{resource_name} -> {nat_gateway_address}"
                )
            else:
                logger.debug(
                    f"Could not find appropriate NAT Gateway for private "
                    f"route table {resource_name}"
                )

        return inferred_dependencies

    def _classify_route_table_type(
        self, metadata_values: dict[str, Any], resource_name: str
    ) -> bool:
        """
        Classify a route table as public or private based on various indicators.

        Args:
            metadata_values: Resolved metadata values for the route table
            resource_name: Route table resource name

        Returns:
            True if route table is classified as public, False if private
        """
        # Check tags for explicit classification
        tags = metadata_values.get("tags", {})

        # Look for explicit type indicators in tags
        for tag_key, tag_value in tags.items():
            tag_key_lower = tag_key.lower()
            tag_value_lower = str(tag_value).lower()

            # Check for explicit type tags
            if tag_key_lower in ["type", "tier", "visibility"]:
                if "public" in tag_value_lower:
                    return True
                elif "private" in tag_value_lower:
                    return False

            # Check Name tag for public/private indicators
            if tag_key_lower == "name":
                if "public" in tag_value_lower:
                    return True
                elif "private" in tag_value_lower:
                    return False

        # Check resource name for public/private indicators
        resource_name_lower = resource_name.lower()
        if "public" in resource_name_lower:
            return True
        elif "private" in resource_name_lower:
            return False

        # Default assumption: if no clear indicators, assume private for safety
        # (private route tables are more common and less likely to cause issues)
        logger.debug(
            f"Could not determine route table type for {resource_name}, "
            f"defaulting to private"
        )
        return False

    def _find_internet_gateway_for_vpc(
        self,
        context: "TerraformMappingContext",
        vpc_id: str,
    ) -> str | None:
        """
        Find the Internet Gateway associated with a specific VPC.

        Args:
            context: Terraform mapping context containing parsed data
            vpc_id: VPC ID to search for associated Internet Gateway

        Returns:
            Terraform address of the Internet Gateway if found, None otherwise
        """
        try:
            # Search in both state and planned values
            for data_key in ["state", "planned_values"]:
                if data_key in context.parsed_data:
                    if data_key == "state":
                        state_data = context.parsed_data[data_key]
                        values = state_data.get("values", {})
                        root_module = values.get("root_module", {}) if values else {}
                    else:
                        # planned_values
                        root_module = context.parsed_data[data_key].get(
                            "root_module", {}
                        )

                    if root_module:
                        igw_address = self._search_internet_gateway_in_module(
                            root_module, vpc_id
                        )
                        if igw_address:
                            return igw_address

        except Exception as e:
            logger.debug(f"Error searching for Internet Gateway for VPC {vpc_id}: {e}")

        return None

    def _search_internet_gateway_in_module(
        self, module_data: dict, vpc_id: str
    ) -> str | None:
        """
        Recursively search for Internet Gateway in a module that's associated
        with the VPC.

        Args:
            module_data: Module data containing resources
            vpc_id: VPC ID to match against

        Returns:
            Internet Gateway address if found, None otherwise
        """
        # Search in current module resources
        for resource in module_data.get("resources", []):
            resource_type = resource.get("type", "")
            resource_values = resource.get("values", {})

            # Look for Internet Gateway resources
            if resource_type == "aws_internet_gateway":
                # Check if this IGW is associated with our VPC
                resource_vpc_id = resource_values.get("vpc_id")
                if resource_vpc_id == vpc_id:
                    return resource.get("address")

        # Search in child modules
        for child_module in module_data.get("child_modules", []):
            result = self._search_internet_gateway_in_module(child_module, vpc_id)
            if result:
                return result

        return None

    def _find_nat_gateway_for_private_route_table(
        self,
        metadata_values: dict[str, Any],
        context: "TerraformMappingContext",
        resource_name: str,
    ) -> str | None:
        """
        Find an appropriate NAT Gateway for a private route table.

        Attempts to match based on availability zone or naming patterns.

        Args:
            metadata_values: Resolved metadata values for the route table
            context: Terraform mapping context containing parsed data
            resource_name: Route table resource name for AZ inference

        Returns:
            Terraform address of an appropriate NAT Gateway if found, None otherwise
        """
        try:
            # Extract availability zone hint from route table name/tags
            az_hint = self._extract_availability_zone_hint(
                metadata_values, resource_name
            )

            # Search for NAT Gateways in the same VPC
            vpc_id = metadata_values.get("vpc_id")
            if not vpc_id:
                logger.debug(f"No VPC ID found for route table {resource_name}")
                return None

            nat_gateways = self._find_nat_gateways_in_vpc(context, vpc_id)

            if not nat_gateways:
                logger.debug(f"No NAT Gateways found for VPC {vpc_id}")
                return None

            # If we have an AZ hint, try to find a matching NAT Gateway
            if az_hint:
                for nat_gw_address, nat_gw_data in nat_gateways:
                    # Check if NAT Gateway name/tags indicate same AZ
                    if self._nat_gateway_matches_az(nat_gw_data, az_hint):
                        logger.debug(
                            f"Found AZ-matched NAT Gateway: {nat_gw_address} "
                            f"for {resource_name}"
                        )
                        return nat_gw_address

            # If no AZ match or no AZ hint, return the first available NAT Gateway
            if nat_gateways:
                selected_nat_gw = nat_gateways[0][0]
                logger.debug(
                    f"Selected first available NAT Gateway: {selected_nat_gw} "
                    f"for {resource_name}"
                )
                return selected_nat_gw

        except Exception as e:
            logger.debug(
                f"Error finding NAT Gateway for route table {resource_name}: {e}"
            )

        return None

    def _extract_availability_zone_hint(
        self, metadata_values: dict[str, Any], resource_name: str
    ) -> str | None:
        """
        Extract availability zone hint from route table metadata or name.

        Args:
            metadata_values: Resolved metadata values for the route table
            resource_name: Route table resource name

        Returns:
            Availability zone string if detected, None otherwise
        """
        # Check tags for AZ information
        tags = metadata_values.get("tags", {})

        # Look for AZ in Name tag
        name_tag = tags.get("Name", "")
        az_from_name = self._extract_az_from_string(name_tag)
        if az_from_name:
            return az_from_name

        # Look for explicit AZ tags
        for tag_key, tag_value in tags.items():
            if "az" in tag_key.lower() or "zone" in tag_key.lower():
                return str(tag_value)

        # Extract from resource name
        az_from_resource = self._extract_az_from_string(resource_name)
        if az_from_resource:
            return az_from_resource

        return None

    def _extract_az_from_string(self, text: str) -> str | None:
        """
        Extract availability zone pattern from a string.

        Looks for patterns like: us-east-1a, eu-west-1b, etc.

        Args:
            text: String to search for AZ pattern

        Returns:
            AZ string if found, None otherwise
        """
        import re

        # Pattern for AWS availability zones: region-direction-number-letter
        # Examples: us-east-1a, eu-west-1b, ap-southeast-2c
        az_pattern = r"[a-z]{2}-[a-z]+-\d+[a-z]"

        matches = re.findall(az_pattern, text.lower())
        if matches:
            return matches[0]  # Return the first match

        return None

    def _find_nat_gateways_in_vpc(
        self, context: "TerraformMappingContext", vpc_id: str
    ) -> list[tuple[str, dict]]:
        """
        Find all NAT Gateways in a specific VPC.

        Args:
            context: Terraform mapping context containing parsed data
            vpc_id: VPC ID to search for NAT Gateways

        Returns:
            List of (address, resource_data) tuples for NAT Gateways in the VPC
        """
        nat_gateways = []

        try:
            # Search in both state and planned values
            for data_key in ["state", "planned_values"]:
                if data_key in context.parsed_data:
                    if data_key == "state":
                        state_data = context.parsed_data[data_key]
                        values = state_data.get("values", {})
                        root_module = values.get("root_module", {}) if values else {}
                    else:
                        # planned_values
                        root_module = context.parsed_data[data_key].get(
                            "root_module", {}
                        )

                    if root_module:
                        nat_gws = self._search_nat_gateways_in_module(
                            root_module, vpc_id
                        )
                        nat_gateways.extend(nat_gws)

        except Exception as e:
            logger.debug(f"Error searching for NAT Gateways in VPC {vpc_id}: {e}")

        return nat_gateways

    def _search_nat_gateways_in_module(
        self, module_data: dict, vpc_id: str
    ) -> list[tuple[str, dict]]:
        """
        Recursively search for NAT Gateways in a module that are in the specified VPC.

        Args:
            module_data: Module data containing resources
            vpc_id: VPC ID to match against

        Returns:
            List of (address, resource_data) tuples for matching NAT Gateways
        """
        nat_gateways = []

        # Search in current module resources
        for resource in module_data.get("resources", []):
            resource_type = resource.get("type", "")
            resource_values = resource.get("values", {})

            # Look for NAT Gateway resources
            if resource_type == "aws_nat_gateway":
                # Check if this NAT Gateway is in our VPC (indirectly via subnet)
                subnet_id = resource_values.get("subnet_id")
                if subnet_id and self._subnet_belongs_to_vpc(
                    module_data, subnet_id, vpc_id
                ):
                    nat_gateways.append((resource.get("address"), resource))

        # Search in child modules
        for child_module in module_data.get("child_modules", []):
            child_nat_gws = self._search_nat_gateways_in_module(child_module, vpc_id)
            nat_gateways.extend(child_nat_gws)

        return nat_gateways

    def _subnet_belongs_to_vpc(
        self, module_data: dict, subnet_id: str, vpc_id: str
    ) -> bool:
        """
        Check if a subnet belongs to a specific VPC by searching subnet resources.

        Args:
            module_data: Module data containing resources
            subnet_id: Subnet ID to check
            vpc_id: VPC ID to match against

        Returns:
            True if subnet belongs to the VPC, False otherwise
        """
        try:
            # Search for subnet resource with the given ID
            for resource in module_data.get("resources", []):
                if resource.get("type") == "aws_subnet":
                    resource_values = resource.get("values", {})
                    if (
                        resource_values.get("id") == subnet_id
                        and resource_values.get("vpc_id") == vpc_id
                    ):
                        return True
        except Exception:
            pass

        return False

    def _nat_gateway_matches_az(self, nat_gw_data: dict, az_hint: str) -> bool:
        """
        Check if a NAT Gateway matches an availability zone hint.

        Args:
            nat_gw_data: NAT Gateway resource data
            az_hint: Availability zone hint to match against

        Returns:
            True if NAT Gateway appears to be in the same AZ, False otherwise
        """
        try:
            # Check NAT Gateway tags for AZ information
            resource_values = nat_gw_data.get("values", {})
            tags = resource_values.get("tags", {})

            # Check Name tag
            name_tag = tags.get("Name", "")
            if az_hint.lower() in name_tag.lower():
                return True

            # Check resource address for AZ hints
            address = nat_gw_data.get("address", "")
            if az_hint.lower() in address.lower():
                return True

        except Exception:
            pass

        return False
