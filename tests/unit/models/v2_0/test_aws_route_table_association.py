import inspect
import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder

logger = logging.getLogger(__name__)


class AWSRouteTableAssociationMapper(SingleResourceMapper):
    """Map a Terraform 'aws_route_table_association' resource to TOSCA relationships.

    This mapper doesn't create a separate node but instead modifies existing nodes
    to establish the association relationship between a subnet/gateway node and a
    route table node.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_route_table_association'."""
        return resource_type == "aws_route_table_association"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
    ) -> None:
        """Create association relationship between subnet/gateway and route table.

        This mapper doesn't create a new TOSCA node. Instead, it modifies the existing
        subnet or gateway node to add a routing requirement pointing to the route table.

        Args:
            resource_name: resource name (e.g. 'aws_route_table_association.a')
            resource_type: resource type (always 'aws_route_table_association')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
        """
        logger.info("Processing route table association resource: '%s'", resource_name)

        # Extract values and configuration
        values = resource_data.get("values", {})
        if not values:
            logger.warning(
                "Resource '%s' has no 'values' section. Skipping.", resource_name
            )
            return

        # Extract references from configuration
        (
            subnet_address,
            gateway_address,
            route_table_address,
        ) = self._extract_references(resource_data)

        if not route_table_address:
            logger.warning(
                "Could not resolve route table reference for '%s'. Skipping.",
                resource_name,
            )
            return

        if not subnet_address and not gateway_address:
            logger.warning(
                "Could not resolve subnet or gateway reference for '%s'. Skipping.",
                resource_name,
            )
            return

        # Generate TOSCA node names
        route_table_node_name = BaseResourceMapper.generate_tosca_node_name(
            route_table_address, "aws_route_table"
        )

        # Process subnet association
        if subnet_address:
            self._process_subnet_association(
                builder, subnet_address, route_table_node_name, resource_name
            )

        # Process gateway association
        if gateway_address:
            self._process_gateway_association(
                builder, gateway_address, route_table_node_name, resource_name
            )

    def _extract_references(
        self, resource_data: dict[str, Any]
    ) -> tuple[str | None, str | None, str | None]:
        """Extract subnet, gateway, and route table references from configuration.

        Args:
            resource_data: The resource data from Terraform plan

        Returns:
            Tuple of (subnet_address, gateway_address, route_table_address)
        """
        # Import here to avoid circular imports
        from src.plugins.terraform.mapper import TerraformMapper

        # Access the full plan via the TerraformMapper instance found on the call stack
        parsed_data: dict[str, Any] = {}
        for frame_info in inspect.stack():
            frame_locals = frame_info.frame.f_locals
            if "self" in frame_locals and isinstance(
                frame_locals["self"], TerraformMapper
            ):
                parsed_data = frame_locals["self"].get_current_parsed_data()
                break
        else:
            logger.debug("Could not access parsed_data for reference extraction")
            return None, None, None

        # Get the association address
        association_address = resource_data.get("address")
        if not association_address:
            logger.debug("No address found for route table association resource")
            return None, None, None

        # Find configuration for this resource
        configuration = parsed_data.get("configuration", {})
        config_root_module = configuration.get("root_module", {})
        config_resources = config_root_module.get("resources", [])

        association_config = None
        for config_res in config_resources:
            if config_res.get("address") == association_address:
                association_config = config_res
                break

        if not association_config:
            logger.debug(
                "No configuration found for route table association '%s'",
                association_address,
            )
            return None, None, None

        # Extract references from expressions
        expressions = association_config.get("expressions", {})

        # Get subnet reference
        subnet_address = None
        subnet_id_expr = expressions.get("subnet_id", {})
        if subnet_id_expr:
            subnet_references = subnet_id_expr.get("references", [])
            for ref in subnet_references:
                if "aws_subnet" in ref:
                    # Remove .id suffix if present
                    if ref.endswith(".id"):
                        subnet_address = ref[:-3]
                    else:
                        subnet_address = ref
                    break

        # Get gateway reference
        gateway_address = None
        gateway_id_expr = expressions.get("gateway_id", {})
        if gateway_id_expr:
            gateway_references = gateway_id_expr.get("references", [])
            for ref in gateway_references:
                if any(
                    gw_type in ref
                    for gw_type in [
                        "aws_internet_gateway",
                        "aws_egress_only_internet_gateway",
                        "aws_vpn_gateway",
                        "aws_nat_gateway",
                    ]
                ):
                    # Remove .id suffix if present
                    if ref.endswith(".id"):
                        gateway_address = ref[:-3]
                    else:
                        gateway_address = ref
                    break

        # Get route table reference
        route_table_address = None
        route_table_id_expr = expressions.get("route_table_id", {})
        if route_table_id_expr:
            route_table_references = route_table_id_expr.get("references", [])
            for ref in route_table_references:
                if "aws_route_table" in ref:
                    # Remove .id suffix if present
                    if ref.endswith(".id"):
                        route_table_address = ref[:-3]
                    else:
                        route_table_address = ref
                    break

        logger.debug(
            "Extracted references - Subnet: %s, Gateway: %s, Route Table: %s",
            subnet_address,
            gateway_address,
            route_table_address,
        )

        return subnet_address, gateway_address, route_table_address

    def _process_subnet_association(
        self,
        builder: "ServiceTemplateBuilder",
        subnet_address: str,
        route_table_node_name: str,
        resource_name: str,
    ) -> None:
        """Process subnet to route table association.

        Args:
            builder: ServiceTemplateBuilder instance
            subnet_address: Terraform address of the subnet
            route_table_node_name: TOSCA name of the route table node
            resource_name: Original resource name for logging
        """
        # Generate subnet TOSCA node name
        subnet_node_name = BaseResourceMapper.generate_tosca_node_name(
            subnet_address, "aws_subnet"
        )

        # Find the subnet node in the builder
        subnet_node = self._find_node_in_builder(builder, subnet_node_name)
        if not subnet_node:
            logger.warning(
                "Subnet node '%s' not found. The aws_subnet mapper may not "
                "have run yet. Route table association for '%s' will be skipped.",
                subnet_node_name,
                resource_name,
            )
            return

        # Check if route table node exists
        route_table_node = self._find_node_in_builder(builder, route_table_node_name)
        if not route_table_node:
            logger.warning(
                "Route table node '%s' not found. The aws_route_table mapper may not "
                "have run yet. Route table association for '%s' will be skipped.",
                route_table_node_name,
                resource_name,
            )
            return

        # Add the routing requirement to the subnet
        self._add_routing_requirement(
            subnet_node, route_table_node_name, "subnet", resource_name
        )

        logger.info(
            "Successfully added route table association: %s -> %s (subnet)",
            subnet_node_name,
            route_table_node_name,
        )

    def _process_gateway_association(
        self,
        builder: "ServiceTemplateBuilder",
        gateway_address: str,
        route_table_node_name: str,
        resource_name: str,
    ) -> None:
        """Process gateway to route table association.

        Args:
            builder: ServiceTemplateBuilder instance
            gateway_address: Terraform address of the gateway
            route_table_node_name: TOSCA name of the route table node
            resource_name: Original resource name for logging
        """
        # Determine gateway type from address
        gateway_type = self._determine_gateway_type(gateway_address)
        if not gateway_type:
            logger.warning(
                "Unknown gateway type for '%s'. Association will be skipped.",
                gateway_address,
            )
            return

        # Generate gateway TOSCA node name
        gateway_node_name = BaseResourceMapper.generate_tosca_node_name(
            gateway_address, gateway_type
        )

        # Find the gateway node in the builder
        gateway_node = self._find_node_in_builder(builder, gateway_node_name)
        if not gateway_node:
            logger.warning(
                "Gateway node '%s' not found. The %s mapper may not "
                "have run yet. Route table association for '%s' will be skipped.",
                gateway_node_name,
                gateway_type,
                resource_name,
            )
            return

        # Check if route table node exists
        route_table_node = self._find_node_in_builder(builder, route_table_node_name)
        if not route_table_node:
            logger.warning(
                "Route table node '%s' not found. The aws_route_table mapper may not "
                "have run yet. Route table association for '%s' will be skipped.",
                route_table_node_name,
                resource_name,
            )
            return

        # Add the routing requirement to the gateway
        self._add_routing_requirement(
            gateway_node, route_table_node_name, "gateway", resource_name
        )

        logger.info(
            "Successfully added route table association: %s -> %s (gateway)",
            gateway_node_name,
            route_table_node_name,
        )

    def _determine_gateway_type(self, gateway_address: str) -> str | None:
        """Determine the gateway type from the Terraform address.

        Args:
            gateway_address: Terraform address like 'aws_internet_gateway.foo'

        Returns:
            Gateway type string or None if unknown
        """
        if "aws_internet_gateway" in gateway_address:
            return "aws_internet_gateway"
        elif "aws_egress_only_internet_gateway" in gateway_address:
            return "aws_egress_only_internet_gateway"
        elif "aws_vpn_gateway" in gateway_address:
            return "aws_vpn_gateway"
        elif "aws_nat_gateway" in gateway_address:
            return "aws_nat_gateway"
        else:
            return None

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
        source_node,
        route_table_node_name: str,
        association_type: str,
        resource_name: str,
    ) -> None:
        """Add routing requirement to the source node.

        Args:
            source_node: The source node (subnet or gateway) to modify
            route_table_node_name: Name of the route table node
            association_type: Type of association ('subnet' or 'gateway')
            resource_name: Original resource name for logging
        """
        try:
            # Add the routing requirement with LinksTo relationship
            req_builder = (
                source_node.add_requirement("dependency")
                .to_node(route_table_node_name)
                .with_relationship("LinksTo")
            )

            req_builder.and_node()

            logger.debug(
                "Added routing requirement: %s -> %s (type: %s)",
                source_node.name if hasattr(source_node, "name") else "unknown",
                route_table_node_name,
                association_type,
            )

        except Exception as e:
            logger.error(
                "Failed to add route table association requirement for '%s': %s",
                resource_name,
                e,
            )
            raise
