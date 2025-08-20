import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder

logger = logging.getLogger(__name__)


class AWSVPCMapper(SingleResourceMapper):
    """Map a Terraform 'aws_vpc' resource into a tosca.nodes.Network node."""

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """This mapper is specific to the 'aws_vpc' resource type."""
        return resource_type == "aws_vpc"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
    ) -> None:
        """Perform translation from aws_vpc to tosca.nodes.Network."""
        logger.info(f"Mapping AWS VPC resource: '{resource_name}'")

        # Actual values are under the 'values' key in the plan JSON
        values = resource_data.get("values", {})
        if not values:
            logger.warning(
                f"Resource '{resource_name}' has no 'values' section. Skipping."
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

        # Create the main Network node
        network_node = builder.add_node(name=node_name, node_type="Network")

        # Extract AWS VPC properties and map them to TOSCA Network properties

        # CIDR block -> maps directly to the TOSCA 'cidr' property
        cidr_block = values.get("cidr_block")

        # Instance tenancy (default, dedicated, host)
        instance_tenancy = values.get("instance_tenancy")

        # Enable DNS hostname resolution
        enable_dns_hostnames = values.get("enable_dns_hostnames")

        # Enable DNS support
        enable_dns_support = values.get("enable_dns_support")

        # Enable classiclink (deprecated)
        enable_classiclink = values.get("enable_classiclink")

        # Enable classiclink DNS support (deprecated)
        enable_classiclink_dns_support = values.get("enable_classiclink_dns_support")

        # Assign generated IPv6 CIDR block
        assign_generated_ipv6_cidr_block = values.get(
            "assign_generated_ipv6_cidr_block"
        )

        # IPv6 CIDR block
        ipv6_cidr_block = values.get("ipv6_cidr_block")

        # IPv6 IPAM pool ID
        ipv6_ipam_pool_id = values.get("ipv6_ipam_pool_id")

        # IPv6 netmask length
        ipv6_netmask_length = values.get("ipv6_netmask_length")

        # Map standard TOSCA Network properties

        # CIDR block
        if cidr_block:
            network_node.with_property("cidr", cidr_block)

        # Determine IP version
        ip_version = 4  # Default
        if ipv6_cidr_block or assign_generated_ipv6_cidr_block:
            # If both IPv4 and IPv6 are present, keep 4 as default
            # but add info to metadata. Otherwise use IPv6 only.
            if cidr_block:
                ip_version = 4  # Dual stack, prefer IPv4
            else:
                ip_version = 6  # IPv6 only

        network_node.with_property("ip_version", ip_version)

        # DHCP is enabled by default in AWS VPCs
        network_node.with_property("dhcp_enabled", True)

        # Add the standard 'link' capability for Network nodes
        network_node.add_capability("link").and_node()

        # Build metadata containing Terraform and AWS information
        metadata = {}

        # Original resource information
        metadata["original_resource_type"] = resource_type
        metadata["original_resource_name"] = clean_name

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # AWS VPC specific information
        if instance_tenancy:
            metadata["aws_instance_tenancy"] = instance_tenancy
        if enable_dns_hostnames is not None:
            metadata["aws_enable_dns_hostnames"] = enable_dns_hostnames
        if enable_dns_support is not None:
            metadata["aws_enable_dns_support"] = enable_dns_support
        if enable_classiclink is not None:
            metadata["aws_enable_classiclink"] = enable_classiclink
        if enable_classiclink_dns_support is not None:
            metadata["aws_enable_classiclink_dns_support"] = (
                enable_classiclink_dns_support
            )
        if assign_generated_ipv6_cidr_block is not None:
            metadata["aws_assign_generated_ipv6_cidr_block"] = (
                assign_generated_ipv6_cidr_block
            )
        if ipv6_cidr_block:
            metadata["aws_ipv6_cidr_block"] = ipv6_cidr_block
        if ipv6_ipam_pool_id:
            metadata["aws_ipv6_ipam_pool_id"] = ipv6_ipam_pool_id
        if ipv6_netmask_length is not None:
            metadata["aws_ipv6_netmask_length"] = ipv6_netmask_length

        # Terraform tags
        tags = values.get("tags", {})
        if tags:
            metadata["terraform_tags"] = tags

        # Extract additional AWS info for extra metadata

        # Tags_all (all tags including provider defaults)
        tags_all = values.get("tags_all", {})
        if tags_all and tags_all != tags:
            metadata["terraform_tags_all"] = tags_all

        # Default security group ID (populated after creation)
        default_security_group_id = values.get("default_security_group_id")
        if default_security_group_id:
            metadata["aws_default_security_group_id"] = default_security_group_id

        # Default network ACL ID (populated after creation)
        default_network_acl_id = values.get("default_network_acl_id")
        if default_network_acl_id:
            metadata["aws_default_network_acl_id"] = default_network_acl_id

        # Default route table ID (populated after creation)
        default_route_table_id = values.get("default_route_table_id")
        if default_route_table_id:
            metadata["aws_default_route_table_id"] = default_route_table_id

        # Main route table ID (populated after creation)
        main_route_table_id = values.get("main_route_table_id")
        if main_route_table_id:
            metadata["aws_main_route_table_id"] = main_route_table_id

        # Owner ID (populated after creation)
        owner_id = values.get("owner_id")
        if owner_id:
            metadata["aws_owner_id"] = owner_id

        # Attach all metadata to the node
        network_node.with_metadata(metadata)

        logger.debug(f"VPC Network node '{node_name}' created successfully.")

        # Log mapped properties for debugging
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Mapped properties for '{node_name}':")
            logger.debug(f"  - CIDR Block: {cidr_block}")
            logger.debug(f"  - IP Version: {ip_version}")
            logger.debug(f"  - Instance Tenancy: {instance_tenancy}")
            logger.debug(f"  - DNS Hostnames: {enable_dns_hostnames}")
            logger.debug(f"  - DNS Support: {enable_dns_support}")
            logger.debug(f"  - IPv6 CIDR: {ipv6_cidr_block}")
            logger.debug(f"  - Tags: {tags}")
