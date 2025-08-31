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

        # Generate a unique TOSCA node name using the utility function
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

        # Add dependencies using injected context
        if context:
            terraform_refs = context.extract_terraform_references(resource_data)
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

                if "." in target_ref:
                    # target_ref is like "aws_vpc.main"
                    target_resource_type = target_ref.split(".", 1)[0]
                    target_node_name = BaseResourceMapper.generate_tosca_node_name(
                        target_ref, target_resource_type
                    )

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
