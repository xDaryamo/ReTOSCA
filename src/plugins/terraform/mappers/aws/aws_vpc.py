import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

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
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Perform translation from aws_vpc to tosca.nodes.Network.

        Args:
            resource_name: The name/identifier of the resource
            resource_type: The type/kind of resource (e.g., 'aws_vpc')
            resource_data: The resource configuration data
            builder: The ServiceTemplateBuilder to populate with TOSCA resources
            context: TerraformMappingContext containing dependencies for reference
                extraction
        """
        logger.info(f"Mapping AWS VPC resource: '{resource_name}'")

        # Get resolved values using the context for properties
        if context:
            values = context.get_resolved_values(resource_data, "property")
        else:
            # Fallback to original values if no context available
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
        values.get("enable_classiclink")

        # Enable classiclink DNS support (deprecated)
        values.get("enable_classiclink_dns_support")

        # Assign generated IPv6 CIDR block
        assign_generated_ipv6_cidr_block = values.get(
            "assign_generated_ipv6_cidr_block"
        )

        # IPv6 CIDR block
        ipv6_cidr_block = values.get("ipv6_cidr_block")

        # IPv6 IPAM pool ID
        values.get("ipv6_ipam_pool_id")

        # IPv6 netmask length
        values.get("ipv6_netmask_length")

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

        # AWS VPC specific information - use metadata_values to ensure concrete values
        metadata_instance_tenancy = metadata_values.get("instance_tenancy")
        if metadata_instance_tenancy:
            metadata["aws_instance_tenancy"] = metadata_instance_tenancy

        metadata_enable_dns_hostnames = metadata_values.get("enable_dns_hostnames")
        if metadata_enable_dns_hostnames is not None:
            metadata["aws_enable_dns_hostnames"] = metadata_enable_dns_hostnames

        metadata_enable_dns_support = metadata_values.get("enable_dns_support")
        if metadata_enable_dns_support is not None:
            metadata["aws_enable_dns_support"] = metadata_enable_dns_support

        metadata_enable_classiclink = metadata_values.get("enable_classiclink")
        if metadata_enable_classiclink is not None:
            metadata["aws_enable_classiclink"] = metadata_enable_classiclink

        metadata_enable_classiclink_dns_support = metadata_values.get(
            "enable_classiclink_dns_support"
        )
        if metadata_enable_classiclink_dns_support is not None:
            metadata["aws_enable_classiclink_dns_support"] = (
                metadata_enable_classiclink_dns_support
            )

        metadata_assign_generated_ipv6_cidr_block = metadata_values.get(
            "assign_generated_ipv6_cidr_block"
        )
        if metadata_assign_generated_ipv6_cidr_block is not None:
            metadata["aws_assign_generated_ipv6_cidr_block"] = (
                metadata_assign_generated_ipv6_cidr_block
            )

        metadata_ipv6_cidr_block = metadata_values.get("ipv6_cidr_block")
        if metadata_ipv6_cidr_block:
            metadata["aws_ipv6_cidr_block"] = metadata_ipv6_cidr_block

        metadata_ipv6_ipam_pool_id = metadata_values.get("ipv6_ipam_pool_id")
        if metadata_ipv6_ipam_pool_id:
            metadata["aws_ipv6_ipam_pool_id"] = metadata_ipv6_ipam_pool_id

        metadata_ipv6_netmask_length = metadata_values.get("ipv6_netmask_length")
        if metadata_ipv6_netmask_length is not None:
            metadata["aws_ipv6_netmask_length"] = metadata_ipv6_netmask_length

        # AWS VPC tags - use concrete metadata values
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        # Extract additional AWS info for extra metadata

        # Tags_all (all tags including provider defaults)
        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

        # Default security group ID (populated after creation)
        metadata_default_security_group_id = metadata_values.get(
            "default_security_group_id"
        )
        if metadata_default_security_group_id:
            metadata["aws_default_security_group_id"] = (
                metadata_default_security_group_id
            )

        # Default network ACL ID (populated after creation)
        metadata_default_network_acl_id = metadata_values.get("default_network_acl_id")
        if metadata_default_network_acl_id:
            metadata["aws_default_network_acl_id"] = metadata_default_network_acl_id

        # Default route table ID (populated after creation)
        metadata_default_route_table_id = metadata_values.get("default_route_table_id")
        if metadata_default_route_table_id:
            metadata["aws_default_route_table_id"] = metadata_default_route_table_id

        # Main route table ID (populated after creation)
        metadata_main_route_table_id = metadata_values.get("main_route_table_id")
        if metadata_main_route_table_id:
            metadata["aws_main_route_table_id"] = metadata_main_route_table_id

        # Owner ID (populated after creation)
        metadata_owner_id = metadata_values.get("owner_id")
        if metadata_owner_id:
            metadata["aws_owner_id"] = metadata_owner_id

        # Attach all metadata to the node
        network_node.with_metadata(metadata)

        # Add dependencies using injected context (VPCs rarely have dependencies)
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
                    # target_ref is like "aws_internet_gateway.main"
                    target_resource_type = target_ref.split(".", 1)[0]
                    target_node_name = BaseResourceMapper.generate_tosca_node_name(
                        target_ref, target_resource_type
                    )

                    # Add requirement with the property name as the requirement name
                    requirement_name = (
                        prop_name if prop_name not in ["dependency"] else "dependency"
                    )

                    (
                        network_node.add_requirement(requirement_name)
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
            logger.debug(f"  - Tags: {metadata_tags}")
