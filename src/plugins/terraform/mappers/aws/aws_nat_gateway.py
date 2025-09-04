import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSNATGatewayMapper(SingleResourceMapper):
    """Map a Terraform 'aws_nat_gateway' resource to a TOSCA Network node.

    NAT (Network Address Translation) Gateways enable outbound internet access
    for resources in private subnets while preventing inbound internet access.
    They are mapped to Network nodes to represent their network gateway functionality.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_nat_gateway'."""
        return resource_type == "aws_nat_gateway"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Translate aws_nat_gateway into a TOSCA Network node.

        Args:
            resource_name: resource name (e.g. 'aws_nat_gateway.main')
            resource_type: resource type (always 'aws_nat_gateway')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for variable resolution
        """
        logger.info("Mapping NAT Gateway resource: '%s'", resource_name)

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

        # Create the NAT Gateway node as a Network node
        nat_node = builder.add_node(name=node_name, node_type="Network")

        # Extract AWS NAT Gateway properties
        values.get("subnet_id")
        values.get("allocation_id")
        connectivity_type = values.get("connectivity_type", "public")
        values.get("private_ip")
        values.get("secondary_allocation_ids", [])
        values.get("secondary_private_ip_address_count")
        values.get("secondary_private_ip_addresses", [])
        tags = values.get("tags", {})

        # Set Network properties based on NAT Gateway characteristics
        # Connectivity type determines the network type
        if connectivity_type == "private":
            nat_node.with_property("network_type", "private")
        else:
            nat_node.with_property("network_type", "public")

        # NAT Gateways primarily handle IPv4 traffic
        nat_node.with_property("ip_version", 4)

        # Use Name tag if available, otherwise generate descriptive name
        if tags and "Name" in tags:
            nat_node.with_property("network_name", f"NATGW-{tags['Name']}")
        else:
            nat_node.with_property("network_name", f"NATGW-{clean_name}")

        # Add the standard 'link' capability for Network nodes
        nat_node.add_capability("link").and_node()

        # Get resolved values specifically for metadata (always concrete values)
        if context:
            metadata_values = context.get_resolved_values(resource_data, "metadata")
        else:
            metadata_values = resource_data.get("values", {})

        # Build metadata with Terraform and AWS information
        metadata: dict[str, Any] = {}

        # Original resource information
        metadata["original_resource_type"] = resource_type
        metadata["original_resource_name"] = clean_name
        metadata["aws_component_type"] = "NATGateway"
        metadata["description"] = (
            "AWS NAT Gateway providing outbound internet access for private subnets"
        )

        # NAT Gateway specific metadata
        metadata["aws_gateway_type"] = "nat"
        metadata["aws_traffic_direction"] = "outbound_only"
        metadata["aws_ip_version_support"] = "ipv4"

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # AWS NAT Gateway specific properties - use metadata_values for concrete values
        metadata_subnet_id = metadata_values.get("subnet_id")
        if metadata_subnet_id:
            metadata["aws_subnet_id"] = metadata_subnet_id

        metadata_allocation_id = metadata_values.get("allocation_id")
        if metadata_allocation_id:
            metadata["aws_allocation_id"] = metadata_allocation_id

        metadata_connectivity_type = metadata_values.get("connectivity_type", "public")
        metadata["aws_connectivity_type"] = metadata_connectivity_type

        metadata_private_ip = metadata_values.get("private_ip")
        if metadata_private_ip:
            metadata["aws_private_ip"] = metadata_private_ip

        metadata_secondary_allocation_ids = metadata_values.get(
            "secondary_allocation_ids", []
        )
        if metadata_secondary_allocation_ids:
            metadata["aws_secondary_allocation_ids"] = metadata_secondary_allocation_ids

        metadata_secondary_count = metadata_values.get(
            "secondary_private_ip_address_count"
        )
        if metadata_secondary_count is not None:
            metadata["aws_secondary_private_ip_address_count"] = (
                metadata_secondary_count
            )

        metadata_secondary_ips = metadata_values.get(
            "secondary_private_ip_addresses", []
        )
        if metadata_secondary_ips:
            metadata["aws_secondary_private_ip_addresses"] = metadata_secondary_ips

        # Computed attributes
        metadata_id = metadata_values.get("id")
        if metadata_id:
            metadata["aws_id"] = metadata_id

        metadata_network_interface_id = metadata_values.get("network_interface_id")
        if metadata_network_interface_id:
            metadata["aws_network_interface_id"] = metadata_network_interface_id

        metadata_public_ip = metadata_values.get("public_ip")
        if metadata_public_ip:
            metadata["aws_public_ip"] = metadata_public_ip

        metadata_private_ip_computed = metadata_values.get("private_ip")
        if metadata_private_ip_computed:
            metadata["aws_private_ip_computed"] = metadata_private_ip_computed

        # Tags for the NAT Gateway - use metadata values for concrete resolution
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        # Tags_all (all tags including provider defaults)
        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

        # Attach collected metadata to the node
        nat_node.with_metadata(metadata)

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
                    # target_ref is like "aws_subnet.private" or "aws_eip.nat"
                    target_resource_type = target_ref.split(".", 1)[0]
                    target_node_name = BaseResourceMapper.generate_tosca_node_name(
                        target_ref, target_resource_type
                    )

                    # Add requirement with the property name as the requirement name
                    requirement_name = (
                        prop_name if prop_name not in ["dependency"] else "dependency"
                    )

                    (
                        nat_node.add_requirement(requirement_name)
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

        logger.debug("NAT Gateway node '%s' created successfully.", node_name)

        # Debug: mapped properties - use metadata values for concrete display
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Mapped properties for '%s':", node_name)
            logger.debug("  - Connectivity Type: %s", metadata_connectivity_type)
            logger.debug("  - Subnet ID: %s", metadata_subnet_id)
            logger.debug("  - Allocation ID: %s", metadata_allocation_id)
            logger.debug("  - Private IP: %s", metadata_private_ip)
            logger.debug("  - Public IP: %s", metadata_public_ip)
            logger.debug("  - Network Interface ID: %s", metadata_network_interface_id)
            logger.debug("  - Tags: %s", metadata_tags)
