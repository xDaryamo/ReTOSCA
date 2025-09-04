import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSEIPMapper(SingleResourceMapper):
    """Map a Terraform 'aws_eip' resource to a TOSCA Network node.

    Elastic IP addresses are static, public IPv4 addresses designed for
    dynamic cloud computing. They are mapped as Network nodes to represent
    their network-level IP addressing functionality.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_eip'."""
        return resource_type == "aws_eip"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Translate aws_eip into a TOSCA Network node.

        Args:
            resource_name: resource name (e.g. 'aws_eip.nat_gateway')
            resource_type: resource type (always 'aws_eip')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for variable resolution
        """
        logger.info("Mapping Elastic IP resource: '%s'", resource_name)

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

        # Create the Elastic IP node as a Network node
        eip_node = builder.add_node(name=node_name, node_type="Network")

        # Extract AWS EIP properties and map them to TOSCA Network properties
        values.get("domain")
        values.get("vpc")
        values.get("instance")
        values.get("network_interface")
        values.get("associate_with_private_ip")
        values.get("customer_owned_ipv4_pool")
        tags = values.get("tags", {})

        # Map properties to TOSCA Network
        # Set network type as public since EIPs are public IP addresses
        eip_node.with_property("network_type", "public")
        eip_node.with_property("ip_version", 4)  # EIPs are IPv4

        # Use Name tag if available, otherwise generate descriptive name
        if tags and "Name" in tags:
            eip_node.with_property("network_name", f"EIP-{tags['Name']}")
        else:
            eip_node.with_property("network_name", f"EIP-{clean_name}")

        # Add the standard 'link' capability for Network nodes
        eip_node.add_capability("link").and_node()

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
        metadata["aws_component_type"] = "ElasticIP"
        metadata["description"] = (
            "AWS Elastic IP address for static public IP addressing"
        )

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # AWS EIP specific properties - use metadata_values for concrete values
        metadata_domain = metadata_values.get("domain")
        if metadata_domain:
            metadata["aws_domain"] = metadata_domain

        metadata_vpc = metadata_values.get("vpc")
        if metadata_vpc is not None:  # Can be boolean
            metadata["aws_vpc"] = metadata_vpc

        metadata_instance = metadata_values.get("instance")
        if metadata_instance:
            metadata["aws_instance"] = metadata_instance

        metadata_network_interface = metadata_values.get("network_interface")
        if metadata_network_interface:
            metadata["aws_network_interface"] = metadata_network_interface

        metadata_private_ip = metadata_values.get("associate_with_private_ip")
        if metadata_private_ip:
            metadata["aws_associate_with_private_ip"] = metadata_private_ip

        metadata_customer_pool = metadata_values.get("customer_owned_ipv4_pool")
        if metadata_customer_pool:
            metadata["aws_customer_owned_ipv4_pool"] = metadata_customer_pool

        # Computed attributes
        metadata_allocation_id = metadata_values.get("allocation_id")
        if metadata_allocation_id:
            metadata["aws_allocation_id"] = metadata_allocation_id

        metadata_public_ip = metadata_values.get("public_ip")
        if metadata_public_ip:
            metadata["aws_public_ip"] = metadata_public_ip

        metadata_private_ip_computed = metadata_values.get("private_ip")
        if metadata_private_ip_computed:
            metadata["aws_private_ip"] = metadata_private_ip_computed

        metadata_public_dns = metadata_values.get("public_dns")
        if metadata_public_dns:
            metadata["aws_public_dns"] = metadata_public_dns

        metadata_private_dns = metadata_values.get("private_dns")
        if metadata_private_dns:
            metadata["aws_private_dns"] = metadata_private_dns

        # Address (same as public_ip but separate field)
        metadata_address = metadata_values.get("address")
        if metadata_address:
            metadata["aws_address"] = metadata_address

        # ID
        metadata_id = metadata_values.get("id")
        if metadata_id:
            metadata["aws_id"] = metadata_id

        # Tags for the EIP - use metadata values for concrete resolution
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        # Tags_all (all tags including provider defaults)
        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

        # Attach collected metadata to the node
        eip_node.with_metadata(metadata)

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
                    # target_ref is like "aws_instance.web" or "aws_vpc.main"
                    target_resource_type = target_ref.split(".", 1)[0]
                    target_node_name = BaseResourceMapper.generate_tosca_node_name(
                        target_ref, target_resource_type
                    )

                    # Add requirement with the property name as the requirement name
                    requirement_name = (
                        prop_name if prop_name not in ["dependency"] else "dependency"
                    )

                    (
                        eip_node.add_requirement(requirement_name)
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

        logger.debug("Elastic IP node '%s' created successfully.", node_name)

        # Debug: mapped properties - use metadata values for concrete display
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Mapped properties for '%s':", node_name)
            logger.debug("  - Domain: %s", metadata_domain)
            logger.debug("  - VPC: %s", metadata_vpc)
            logger.debug("  - Public IP: %s", metadata_public_ip)
            logger.debug("  - Allocation ID: %s", metadata_allocation_id)
            logger.debug("  - Instance: %s", metadata_instance)
            logger.debug("  - Network Interface: %s", metadata_network_interface)
            logger.debug("  - Tags: %s", metadata_tags)
