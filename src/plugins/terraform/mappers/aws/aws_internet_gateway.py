import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSInternetGatewayMapper(SingleResourceMapper):
    """Map Terraform Internet Gateway resources to TOSCA Network nodes.

    Supports both:
    - aws_internet_gateway: Provides bidirectional internet connectivity to a VPC
    - aws_egress_only_internet_gateway: Provides IPv6 egress-only connectivity

    Both are mapped to Network nodes with specific metadata to distinguish
    their capabilities.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for Internet Gateway resource types."""
        return resource_type in [
            "aws_internet_gateway",
            "aws_egress_only_internet_gateway",
        ]

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Translate Internet Gateway resources into TOSCA Network nodes.

        Args:
            resource_name: resource name (e.g. 'aws_internet_gateway.gw')
            resource_type: resource type ('aws_internet_gateway' or
                          'aws_egress_only_internet_gateway')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for variable resolution
        """
        # Determine gateway type for logging
        is_egress_only = resource_type == "aws_egress_only_internet_gateway"
        gateway_type = (
            "Egress-only Internet Gateway" if is_egress_only else "Internet Gateway"
        )

        logger.info("Mapping %s resource: '%s'", gateway_type, resource_name)

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

        # Create the Internet Gateway node as a Network node
        igw_node = builder.add_node(name=node_name, node_type="Network")

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

        # Specific metadata based on gateway type
        if is_egress_only:
            metadata["aws_component_type"] = "EgressOnlyInternetGateway"
            metadata["description"] = (
                "AWS Egress-only Internet Gateway providing IPv6 outbound connectivity"
            )
            metadata["aws_gateway_type"] = "egress_only"
            metadata["aws_traffic_direction"] = "outbound_only"
            metadata["aws_ip_version_support"] = "ipv6_only"
        else:
            metadata["aws_component_type"] = "InternetGateway"
            metadata["description"] = (
                "AWS Internet Gateway providing bidirectional internet connectivity"
            )
            metadata["aws_gateway_type"] = "standard"
            metadata["aws_traffic_direction"] = "bidirectional"
            metadata["aws_ip_version_support"] = "ipv4_ipv6"

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # VPC ID (stored in metadata, used later for requirements)
        # Use metadata values for concrete resolution
        metadata_vpc_id = metadata_values.get("vpc_id")
        if metadata_vpc_id:
            metadata["aws_vpc_id"] = metadata_vpc_id

        # Tags for the Internet Gateway - use metadata values for concrete resolution
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags
            # Use Name tag if available
            if "Name" in metadata_tags:
                metadata["aws_name"] = metadata_tags["Name"]

        # Tags_all (all tags including provider defaults)
        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

        # Additional AWS properties that might be available
        metadata_region = metadata_values.get("region")
        if metadata_region:
            metadata["aws_region"] = metadata_region

        # Attach collected metadata to the node
        igw_node.with_metadata(metadata)

        # Set Network properties based on gateway type
        if is_egress_only:
            # Egress-only gateway is for IPv6 outbound traffic only
            igw_node.with_property("network_type", "egress_only")
            igw_node.with_property("ip_version", 6)  # IPv6 only
            base_name = "EIGW"
        else:
            # Standard Internet Gateway for bidirectional traffic
            igw_node.with_property("network_type", "public")
            igw_node.with_property("ip_version", 4)  # Primary IPv4 support
            base_name = "IGW"

        # Use Name tag if available, otherwise use a descriptive name
        if metadata_tags and "Name" in metadata_tags:
            igw_node.with_property(
                "network_name", f"{base_name}-{metadata_tags['Name']}"
            )
        else:
            igw_node.with_property("network_name", f"{base_name}-{clean_name}")

        # Add the standard 'link' capability for Network nodes
        igw_node.add_capability("link").and_node()

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
                        igw_node.add_requirement(requirement_name)
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

        logger.debug("%s node '%s' created successfully.", gateway_type, node_name)

        # Debug: mapped properties - use metadata values for concrete display
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Mapped properties for '%s':", node_name)
            logger.debug(
                "  - Gateway Type: %s", metadata.get("aws_gateway_type", "unknown")
            )
            logger.debug("  - VPC ID: %s", metadata_vpc_id)
            logger.debug("  - Region: %s", metadata_region)
            logger.debug("  - Tags: %s", metadata_tags)
            logger.debug(
                "  - Traffic Direction: %s",
                metadata.get("aws_traffic_direction", "unknown"),
            )
            logger.debug(
                "  - IP Version Support: %s",
                metadata.get("aws_ip_version_support", "unknown"),
            )
