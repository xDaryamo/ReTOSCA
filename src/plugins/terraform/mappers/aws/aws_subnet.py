import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

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

        # Generate a unique TOSCA node name using the utility function
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

        # IPv6 CIDR block
        if ipv6_cidr_block:
            subnet_node.with_property("ipv6_cidr", ipv6_cidr_block)

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

        # Add all discovered dependencies using injected context
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
