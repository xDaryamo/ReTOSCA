import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.provisioning.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSRouteMapper(SingleResourceMapper):
    """Map a Terraform 'aws_route' resource to TOSCA routing relationships.

    This mapper doesn't create a separate node but instead modifies existing nodes
    to establish routing relationships between route tables and target resources
    (gateways, instances, etc.).

    Individual routes define specific routing entries and should be represented as
    requirements/relationships rather than standalone TOSCA nodes.
    """

    def can_map(self, resource_type: str, _resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_route'."""
        return resource_type == "aws_route"

    def map_resource(
        self,
        resource_name: str,
        _resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Create routing relationship for an individual route entry.

        This mapper doesn't create a new TOSCA node. Instead, it modifies the
        existing route table node to add routing requirements pointing to the
        target resource.

        Args:
            resource_name: Resource name (e.g. 'aws_route.example')
            resource_type: Resource type (always 'aws_route')
            resource_data: Resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for dependency resolution and
                variable handling
        """
        logger.info("Processing route resource: '%s'", resource_name)

        # Get resolved values using the context for properties
        if context:
            values = context.get_resolved_values(resource_data, "property")
        else:
            # Fallback to original values if no context available
            values = resource_data.get("values", {})
        # Debug logging for the values we're getting
        logger.debug("Raw resource_data keys: %s", list(resource_data.keys()))
        logger.debug(
            "Resolved values keys: %s", list(values.keys()) if values else "None"
        )

        # Check what values are not None
        non_none_values = (
            {k: v for k, v in values.items() if v is not None} if values else {}
        )
        logger.debug("Non-None resolved values: %s", non_none_values)

        # Always also check the raw values
        raw_values = resource_data.get("values", {})
        logger.debug(
            "Raw values - gateway_id: %s, route_table_id: %s",
            raw_values.get("gateway_id"),
            raw_values.get("route_table_id"),
        )
        # If resolved values are empty or missing important fields, use raw values
        important_fields = ["gateway_id", "route_table_id"]
        if not values or all(values.get(field) is None for field in important_fields):
            if raw_values and any(
                raw_values.get(field) is not None for field in important_fields
            ):
                logger.debug("Using raw values instead of resolved values")
                values = raw_values

        if not values:
            logger.warning(
                "Resource '%s' has no 'values' section. Skipping.", resource_name
            )
            return

        # Extract destination information
        destination_info = self._extract_destination_info(values)
        if not destination_info:
            logger.warning(
                "Could not extract valid destination information for route '%s'. "
                "Skipping.",
                resource_name,
            )
            return

        # Find route table and target references from configuration
        if not context:
            logger.warning(
                "No context provided to resolve references for '%s'. Skipping.",
                resource_name,
            )
            return

        route_table_address, target_address, target_type = self._extract_references(
            resource_data, context, values
        )

        if not route_table_address:
            logger.warning(
                "Could not resolve route table reference for '%s'. Skipping.",
                resource_name,
            )
            return

        if not target_address:
            logger.warning(
                "Could not resolve target reference for '%s'. Skipping.",
                resource_name,
            )
            return

        if not target_type:
            logger.warning(
                "Could not resolve target type for '%s'. Skipping.",
                resource_name,
            )
            return

        # Generate TOSCA node names using context-aware logic
        if context:
            route_table_node_name = context.generate_tosca_node_name_from_address(
                route_table_address, "aws_route_table"
            )
            target_node_name = context.generate_tosca_node_name_from_address(
                target_address, target_type
            )
        else:
            route_table_node_name = BaseResourceMapper.generate_tosca_node_name(
                route_table_address, "aws_route_table"
            )
            target_node_name = BaseResourceMapper.generate_tosca_node_name(
                target_address, target_type
            )

        # Find the route table node in the builder
        route_table_node = self._find_node_in_builder(builder, route_table_node_name)
        if not route_table_node:
            logger.warning(
                "Route table node '%s' not found. The aws_route_table mapper may not "
                "have run yet. Route for '%s' will be skipped.",
                route_table_node_name,
                resource_name,
            )
            return

        # Check if target node exists
        target_node = self._find_node_in_builder(builder, target_node_name)
        if not target_node:
            logger.warning(
                "Target node '%s' not found. The %s mapper may not "
                "have run yet. Route for '%s' will be skipped.",
                target_node_name,
                target_type,
                resource_name,
            )
            return

        # Add the routing requirement to the route table as a dependency
        self._add_routing_requirement(
            route_table_node,
            target_node_name,
            destination_info,
            resource_name,
        )

        # Note: metadata values would be used for logging/debugging but are not
        # needed for this relationship-only mapper

        logger.info(
            "Successfully added route: %s -> %s (destination: %s)",
            route_table_node_name,
            target_node_name,
            destination_info.get("destination", "unknown"),
        )

    def _extract_destination_info(
        self, values: dict[str, Any]
    ) -> dict[str, str] | None:
        """Extract destination information from route values.

        Args:
            values: Route values from Terraform

        Returns:
            Dictionary with destination info or None if invalid
        """
        destination_info = {}

        # Check for IPv4 CIDR block
        if values.get("destination_cidr_block"):
            destination_info["destination"] = values["destination_cidr_block"]
            destination_info["destination_type"] = "ipv4_cidr"
            destination_info["ip_version"] = "4"
        # Check for IPv6 CIDR block
        elif values.get("destination_ipv6_cidr_block"):
            destination_info["destination"] = values["destination_ipv6_cidr_block"]
            destination_info["destination_type"] = "ipv6_cidr"
            destination_info["ip_version"] = "6"
        # Check for prefix list
        elif values.get("destination_prefix_list_id"):
            destination_info["destination"] = values["destination_prefix_list_id"]
            destination_info["destination_type"] = "prefix_list"
            destination_info["ip_version"] = "4"  # Assume IPv4 unless specified
        else:
            return None

        return destination_info

    def _extract_references(
        self,
        resource_data: dict[str, Any],
        context: "TerraformMappingContext",
        values: dict[str, Any],
    ) -> tuple[str | None, str | None, str | None]:
        """Extract route table and target references from the resource configuration.

        Args:
            resource_data: The resource data from Terraform plan
            context: TerraformMappingContext containing parsed data
            values: Route values for fallback target resolution

        Returns:
            Tuple of (route_table_address, target_address, target_type)
        """
        # Extract all Terraform references using context
        terraform_refs = context.extract_terraform_references(resource_data)

        route_table_address = None
        target_address = None
        target_type = None

        # Process each reference to find route table and target
        for prop_name, target_ref, _ in terraform_refs:
            if "." in target_ref:
                target_resource_type = target_ref.split(".", 1)[0]

                # Check for route table reference
                if (
                    prop_name == "route_table_id"
                    and target_resource_type == "aws_route_table"
                ):
                    route_table_address = target_ref

                # Check for various target types
                elif prop_name in self._get_target_property_names():
                    if target_resource_type in self._get_supported_target_types():
                        target_address = target_ref
                        target_type = target_resource_type

        # If we couldn't find references from configuration, try to map using
        # state data with concrete IDs
        if not route_table_address or not target_address:
            logger.debug(
                "Attempting to extract from state values with gateway_id=%s, "
                "route_table_id=%s",
                values.get("gateway_id"),
                values.get("route_table_id"),
            )
            (route_table_address, target_address, target_type) = (
                self._extract_from_state_values(
                    values, context, route_table_address, target_address, target_type
                )
            )

        logger.debug(
            "Extracted references - Route Table: %s, Target: %s (Type: %s)",
            route_table_address,
            target_address,
            target_type,
        )

        return route_table_address, target_address, target_type

    def _get_target_property_names(self) -> list[str]:
        """Get list of possible target property names for routes."""
        return [
            "gateway_id",
            "nat_gateway_id",
            "network_interface_id",
            "instance_id",
            "vpc_peering_connection_id",
            "transit_gateway_id",
            "vpc_endpoint_id",
            "egress_only_gateway_id",
            "carrier_gateway_id",
            "local_gateway_id",
            "core_network_arn",
        ]

    def _get_supported_target_types(self) -> list[str]:
        """Get list of supported target resource types."""
        return [
            "aws_internet_gateway",
            "aws_egress_only_internet_gateway",
            "aws_nat_gateway",
            "aws_network_interface",
            "aws_instance",
            "aws_vpc_peering_connection",
            "aws_transit_gateway",
            "aws_vpc_endpoint",
            "aws_carrier_gateway",
            "aws_local_gateway",
        ]

    def _extract_from_state_values(
        self,
        values: dict[str, Any],
        context: "TerraformMappingContext",
        route_table_address: str | None,
        target_address: str | None,
        target_type: str | None,
    ) -> tuple[str | None, str | None, str | None]:
        """Extract route table and target information from state values.

        This method maps concrete IDs from the state back to Terraform resource
        addresses by looking up the resources in the context.

        Args:
            values: Route values from Terraform state
            context: TerraformMappingContext containing parsed data
            route_table_address: Existing route table address (if any)
            target_address: Existing target address (if any)
            target_type: Existing target type (if any)

        Returns:
            Tuple of (route_table_address, target_address, target_type)
        """
        # Try to find route table address if not already found
        # Instead of looking up by ID, map to the expected Terraform resource patterns
        if not route_table_address:
            route_table_id = values.get("route_table_id")
            if route_table_id:
                # Map common route table naming patterns
                route_table_address = self._map_route_table_id_to_address(
                    route_table_id, context
                )
        # Try to find target address if not already found
        if not target_address:
            # Check for different target types
            gateway_id = values.get("gateway_id")
            if gateway_id and gateway_id != "local":
                if gateway_id.startswith("igw-"):
                    target_address = self._map_gateway_id_to_address(
                        gateway_id, "aws_internet_gateway", context
                    )
                    target_type = "aws_internet_gateway"
                elif gateway_id.startswith("nat-"):
                    target_address = self._map_gateway_id_to_address(
                        gateway_id, "aws_nat_gateway", context
                    )
                    target_type = "aws_nat_gateway"
                elif gateway_id.startswith("eigw-"):
                    target_address = self._map_gateway_id_to_address(
                        gateway_id, "aws_egress_only_internet_gateway", context
                    )
                    target_type = "aws_egress_only_internet_gateway"
                # Add more gateway types as needed
            # Check for other target types
            if not target_address:
                nat_gateway_id = values.get("nat_gateway_id")
                if nat_gateway_id:
                    target_address = self._map_gateway_id_to_address(
                        nat_gateway_id, "aws_nat_gateway", context
                    )
                    target_type = "aws_nat_gateway"

                instance_id = values.get("instance_id")
                if instance_id:
                    target_address = self._map_instance_id_to_address(
                        instance_id, context
                    )
                    target_type = "aws_instance"
        return route_table_address, target_address, target_type

    def _map_route_table_id_to_address(
        self,
        route_table_id: str,
        context: "TerraformMappingContext",
    ) -> str | None:
        """Map a route table ID to its Terraform resource address.

        Args:
            route_table_id: The concrete route table ID (e.g., 'rtb-abc123')
            context: TerraformMappingContext containing parsed data

        Returns:
            The Terraform resource address (e.g., 'aws_route_table.public') or None
        """
        return self._find_resource_by_id(context, route_table_id, "aws_route_table")

    def _map_gateway_id_to_address(
        self,
        gateway_id: str,
        gateway_type: str,
        context: "TerraformMappingContext",
    ) -> str | None:
        """Map a gateway ID to its Terraform resource address.

        Args:
            gateway_id: The concrete gateway ID (e.g., 'igw-abc123')
            gateway_type: The expected gateway resource type
            context: TerraformMappingContext containing parsed data

        Returns:
            The Terraform resource address (e.g., 'aws_internet_gateway.main')
            or None
        """
        return self._find_resource_by_id(context, gateway_id, gateway_type)

    def _map_instance_id_to_address(
        self,
        instance_id: str,
        context: "TerraformMappingContext",
    ) -> str | None:
        """Map an instance ID to its Terraform resource address.

        Args:
            instance_id: The concrete instance ID (e.g., 'i-abc123')
            context: TerraformMappingContext containing parsed data

        Returns:
            The Terraform resource address (e.g., 'aws_instance.web') or None
        """
        return self._find_resource_by_id(context, instance_id, "aws_instance")

    def _find_resource_by_id(
        self,
        context: "TerraformMappingContext",
        resource_id: str,
        resource_type: str,
    ) -> str | None:
        """Find a Terraform resource address by looking for a concrete ID.

        Args:
            context: TerraformMappingContext containing parsed data
            resource_id: The concrete resource ID (e.g., 'igw-abc123')
            resource_type: The resource type to search for
                (e.g., 'aws_internet_gateway')

        Returns:
            The Terraform resource address (e.g., 'aws_internet_gateway.main')
            or None
        """
        # Access the context's parsed data to find resources with matching IDs
        try:
            logger.debug(
                "Searching for resource_type=%s with id=%s", resource_type, resource_id
            )
            # Look through all resources in the context for matching type and ID
            if context.parsed_data:
                logger.debug("Context has parsed_data")
                # Check for state structure first
                state_data = context.parsed_data.get("state", {})
                state_values = state_data.get("values", {}) if state_data else {}
                if state_values and "root_module" in state_values:
                    resources = state_values["root_module"].get("resources", [])
                    logger.debug("Found %d resources to check in state", len(resources))

                    for resource in resources:
                        if resource.get("type") == resource_type:
                            resource_values = resource.get("values", {})
                            resource_id_found = resource_values.get("id")
                            logger.debug(
                                "Checking %s resource with id=%s",
                                resource_type,
                                resource_id_found,
                            )
                            # Check if the ID matches
                            if resource_id_found == resource_id:
                                address = resource.get("address")
                                logger.debug("Found matching resource: %s", address)
                                return address

                # Also check planned_values structure if state not available
                planned_values = context.parsed_data.get("planned_values", {})
                if planned_values and "root_module" in planned_values:
                    resources = planned_values["root_module"].get("resources", [])
                    logger.debug(
                        "Found %d resources to check in planned_values", len(resources)
                    )

                    for resource in resources:
                        if resource.get("type") == resource_type:
                            resource_values = resource.get("values", {})
                            resource_id_found = resource_values.get("id")
                            logger.debug(
                                "Checking %s resource with id=%s",
                                resource_type,
                                resource_id_found,
                            )
                            # Check if the ID matches
                            if resource_id_found == resource_id:
                                address = resource.get("address")
                                logger.debug("Found matching resource: %s", address)
                                return address
            else:
                logger.debug("Context missing parsed_data")

        except Exception as e:
            logger.debug("Error searching for resource by ID %s: %s", resource_id, e)
        logger.debug(
            "No matching resource found for %s with id %s", resource_type, resource_id
        )
        return None

    def _infer_target_from_values(
        self, values: dict[str, Any]
    ) -> tuple[str | None, str | None]:
        """Infer target address and type from concrete values when references
        aren't available.

        This is a fallback method for cases where Terraform references don't provide
        the target information directly.

        Args:
            values: Route values from Terraform

        Returns:
            Tuple of (target_address, target_type) or (None, None)
        """
        # Check for local route (target is "local")
        gateway_id = values.get("gateway_id")
        if gateway_id == "local":
            logger.debug("Detected local route - no target node mapping needed")
            return None, None

        # For other gateway types, we can't easily map to specific resources
        # without the Terraform configuration references
        logger.debug(
            "Could not infer target from values - configuration references needed"
        )
        return None, None

    def _find_node_in_builder(self, builder: "ServiceTemplateBuilder", node_name: str):
        """Find a node in the builder by name.

        Args:
            builder: The ServiceTemplateBuilder instance
            node_name: Name of the node to find

        Returns:
            The node object if found, None otherwise
        """
        try:
            # Use the get_node method
            return builder.get_node(node_name)

        except Exception as e:
            logger.debug("Error while searching for node '%s': %s", node_name, e)
            return None

    def _add_routing_requirement(
        self,
        route_table_node,
        target_node_name: str,
        destination_info: dict[str, str],
        resource_name: str,
    ) -> None:
        """Add routing dependency to the route table node.

        Since TOSCA Network nodes only support 'dependency' requirements,
        we add the routing target as a dependency with LinksTo relationship
        and routing information in the relationship properties.

        Args:
            route_table_node: The route table node to modify
            target_node_name: Name of the target node
            destination_info: Information about the route destination
            resource_name: Original resource name for logging
        """
        try:
            # Use dependency requirement with routing information in
            # relationship properties
            relationship_type = self._determine_routing_relationship_type(
                destination_info
            )

            req_builder = (
                route_table_node.add_requirement("dependency")
                .to_node(target_node_name)
                .with_relationship(relationship_type)
            )

            req_builder.and_node()

            logger.debug(
                "Added routing dependency: %s -> %s (destination: %s, "
                "relationship: %s)",
                (
                    route_table_node.name
                    if hasattr(route_table_node, "name")
                    else "unknown"
                ),
                target_node_name,
                destination_info.get("destination", "unknown"),
                relationship_type,
            )

        except Exception as e:
            logger.error(
                "Failed to add routing dependency for '%s': %s",
                resource_name,
                e,
            )
            raise

    def _sanitize_requirement_name(self, name: str) -> str:
        """Sanitize a string for use as a requirement name.

        Args:
            name: Original name string

        Returns:
            Sanitized name safe for use as a requirement name
        """
        # Replace problematic characters with underscores
        sanitized = name.replace("/", "_").replace(":", "_").replace(".", "_")
        # Remove any remaining special characters
        sanitized = "".join(c if c.isalnum() or c == "_" else "_" for c in sanitized)
        # Remove consecutive underscores
        while "__" in sanitized:
            sanitized = sanitized.replace("__", "_")
        # Remove leading/trailing underscores
        sanitized = sanitized.strip("_")
        # Ensure it doesn't start with a number
        if sanitized and sanitized[0].isdigit():
            sanitized = f"route_{sanitized}"
        # Ensure we have a valid name
        if not sanitized:
            sanitized = "route"
        return sanitized

    def _determine_routing_relationship_type(
        self, destination_info: dict[str, str]
    ) -> str:
        """Determine the appropriate TOSCA relationship type for the routing
        requirement.

        Args:
            destination_info: Information about the route destination

        Returns:
            TOSCA relationship type string
        """
        destination_type = destination_info.get("destination_type", "")

        # For network routing, LinksTo is the most appropriate relationship
        # as it represents network connectivity and routing paths
        if destination_type in ["ipv4_cidr", "ipv6_cidr"]:
            return "LinksTo"
        elif destination_type == "prefix_list":
            return "LinksTo"
        else:
            # Default to LinksTo for routing relationships
            return "LinksTo"
