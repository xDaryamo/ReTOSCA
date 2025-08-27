import inspect
import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper
from src.plugins.terraform.mapper import TerraformMapper
from src.plugins.terraform.terraform_mapper_base import TerraformResourceMapperMixin

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder

logger = logging.getLogger(__name__)


class AWSRouteTableMapper(TerraformResourceMapperMixin, SingleResourceMapper):
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
    ) -> None:
        """Translate an aws_route_table resource into a TOSCA Network node.

        Args:
            resource_name: resource name (e.g. 'aws_route_table.example')
            resource_type: resource type (always 'aws_route_table')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
        """
        logger.info("Mapping Route Table resource: '%s'", resource_name)

        # Validate input data
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

        # Build metadata with Terraform and AWS information
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

        # VPC ID (required for route tables)
        vpc_id = values.get("vpc_id")
        if vpc_id:
            metadata["aws_vpc_id"] = vpc_id

        # Process routes for properties
        routes = values.get("route", [])
        processed_routes = []
        if routes:
            processed_routes = self._process_routes(routes)
            metadata["aws_route_count"] = len(routes)

        # Propagating VGWs (Virtual Gateways)
        propagating_vgws = values.get("propagating_vgws", [])
        if propagating_vgws:
            metadata["aws_propagating_vgws"] = propagating_vgws

        # Tags for the route table
        tags = values.get("tags", {})
        if tags:
            metadata["aws_tags"] = tags
            # Use Name tag if available
            if "Name" in tags:
                metadata["aws_name"] = tags["Name"]

        # Tags_all (all tags including provider defaults)
        tags_all = values.get("tags_all", {})
        if tags_all and tags_all != tags:
            metadata["aws_tags_all"] = tags_all

        # Additional AWS properties that might be available
        region = values.get("region")
        if region:
            metadata["aws_region"] = region

        # Set Network properties (only standard TOSCA Simple Profile properties)
        if tags and "Name" in tags:
            route_table_node.with_property("network_name", tags["Name"])
        else:
            route_table_node.with_property("network_name", clean_name)

        # Set network type to indicate this is a routing network
        route_table_node.with_property("network_type", "routing")

        # Set IP version based on routes (default to 4, set to 6 if IPv6 routes exist)
        has_ipv6_routes = any(
            route.get("destination_type") == "ipv6_cidr" for route in processed_routes
        )
        route_table_node.with_property("ip_version", 6 if has_ipv6_routes else 4)

        # Add routes to metadata (not as property - not in TOSCA Simple Profile)
        if processed_routes:
            metadata["aws_routes"] = processed_routes

        # Attach collected metadata to the node
        route_table_node.with_metadata(metadata)

        # Add the standard 'link' capability for Network nodes
        route_table_node.add_capability("link").and_node()

        # Detect dependencies using the Terraform reference system
        self._add_dependencies(route_table_node, resource_data, node_name, routes)

        logger.debug("Route Table node '%s' created successfully.", node_name)

        # Debug: mapped properties
        logger.debug(
            "Mapped properties for '%s':\n"
            "  - VPC ID: %s\n"
            "  - Routes: %d\n"
            "  - Propagating VGWs: %s\n"
            "  - Tags: %s",
            node_name,
            vpc_id,
            len(routes),
            propagating_vgws,
            tags,
        )

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

    def _add_dependencies(
        self,
        route_table_node,
        resource_data: dict[str, Any],
        node_name: str,
        routes: list[dict[str, Any]],
    ) -> None:
        """Add dependency relationships based on VPC and route targets."""
        # Access the full plan via the TerraformMapper instance found on the call stack
        parsed_data: dict[str, Any] = {}
        for frame_info in inspect.stack():
            frame_locals = frame_info.frame.f_locals
            if "self" in frame_locals and isinstance(
                frame_locals["self"], TerraformMapper
            ):
                terraform_mapper = frame_locals["self"]
                parsed_data = terraform_mapper.get_current_parsed_data()
                break
        else:
            logger.warning(
                "Unable to access Terraform plan data to detect dependencies for '%s'",
                node_name,
            )
            return

        dependencies_added = set()

        if parsed_data:
            # Find VPC dependency
            terraform_refs = TerraformMapper.extract_terraform_references(
                resource_data, parsed_data
            )

            for prop_name, target_ref, _relationship_type in terraform_refs:
                if prop_name == "vpc_id" and target_ref not in dependencies_added:
                    if "." in target_ref:
                        # target_ref is like "aws_vpc.example"
                        target_resource_type = target_ref.split(".", 1)[0]
                        target_node_name = BaseResourceMapper.generate_tosca_node_name(
                            target_ref, target_resource_type
                        )
                        # Route Table depends on VPC
                        route_table_node.add_requirement("dependency").to_node(
                            target_node_name
                        ).with_relationship("DependsOn").and_node()

                        dependencies_added.add(target_ref)
                        logger.info(
                            "Added dependency DependsOn from '%s' to VPC '%s'",
                            node_name,
                            target_node_name,
                        )

            # Find route target dependencies (Internet Gateways, NAT Gateways, etc.)
            self._add_route_target_dependencies(
                route_table_node, routes, parsed_data, node_name, dependencies_added
            )

    def _add_route_target_dependencies(
        self,
        route_table_node,
        routes: list[dict[str, Any]],
        parsed_data: dict[str, Any],
        node_name: str,
        dependencies_added: set[str],
    ) -> None:
        """Add dependencies to route targets like Internet Gateways."""
        # Extract all references from the entire resource data

        # Look for references in the configuration section for route targets
        configuration = parsed_data.get("configuration", {})
        root_module = configuration.get("root_module", {})
        config_resources = root_module.get("resources", [])

        # Find our route table configuration
        resource_address = None
        for frame_info in inspect.stack():
            frame_locals = frame_info.frame.f_locals
            if "resource_data" in frame_locals:
                resource_address = frame_locals["resource_data"].get("address")
                break

        if not resource_address:
            return

        config_resource = None
        for config_res in config_resources:
            if config_res.get("address") == resource_address:
                config_resource = config_res
                break

        if not config_resource:
            return

        # Check for references in route blocks
        expressions = config_resource.get("expressions", {})
        route_expression = expressions.get("route", {})

        # Check if route has references (this contains all gateway references)
        if isinstance(route_expression, dict) and "references" in route_expression:
            terraform_refs = route_expression["references"]
            for ref in terraform_refs:
                if ref and ref not in dependencies_added:
                    # Clean reference (remove .id suffix if present)
                    clean_ref = ref[:-3] if ref.endswith(".id") else ref
                    if "." in clean_ref:
                        target_resource_type = clean_ref.split(".", 1)[0]

                        # Map route target types - include both gateway types
                        if target_resource_type in [
                            "aws_internet_gateway",
                            "aws_egress_only_internet_gateway",
                            "aws_nat_gateway",
                            "aws_transit_gateway",
                            "aws_vpc_endpoint",
                            "aws_network_interface",
                        ]:
                            target_node_name = (
                                BaseResourceMapper.generate_tosca_node_name(
                                    clean_ref, target_resource_type
                                )
                            )

                            route_table_node.add_requirement("dependency").to_node(
                                target_node_name
                            ).with_relationship("DependsOn").and_node()

                            dependencies_added.add(clean_ref)
                            logger.info(
                                "Added dependency DependsOn from '%s' to "
                                "route target '%s'",
                                node_name,
                                target_node_name,
                            )
