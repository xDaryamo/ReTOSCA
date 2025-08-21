import inspect
import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper
from src.plugins.terraform.mapper import TerraformMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder

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
    ) -> None:
        """Translate Internet Gateway resources into TOSCA Network nodes.

        Args:
            resource_name: resource name (e.g. 'aws_internet_gateway.gw')
            resource_type: resource type ('aws_internet_gateway' or
                          'aws_egress_only_internet_gateway')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
        """
        # Determine gateway type for logging
        is_egress_only = resource_type == "aws_egress_only_internet_gateway"
        gateway_type = (
            "Egress-only Internet Gateway" if is_egress_only else "Internet Gateway"
        )

        logger.info("Mapping %s resource: '%s'", gateway_type, resource_name)

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

        # Create the Internet Gateway node as a Network node
        igw_node = builder.add_node(name=node_name, node_type="Network")

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
        vpc_id = values.get("vpc_id")
        if vpc_id:
            metadata["aws_vpc_id"] = vpc_id

        # Tags for the Internet Gateway
        tags = values.get("tags", {})
        if tags:
            metadata["aws_tags"] = tags
            # Use Name tag if available
            if "Name" in tags:
                metadata["aws_name"] = tags["Name"]

        # Additional AWS properties that might be available
        region = values.get("region")
        if region:
            metadata["aws_region"] = region

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
        if tags and "Name" in tags:
            igw_node.with_property("network_name", f"{base_name}-{tags['Name']}")
        else:
            igw_node.with_property("network_name", f"{base_name}-{clean_name}")

        # Add the standard 'link' capability for Network nodes
        igw_node.add_capability("link").and_node()

        # Detect VPC dependency using the Terraform reference system
        self._add_vpc_dependency(igw_node, resource_data, node_name)

        logger.debug("%s node '%s' created successfully.", gateway_type, node_name)

        # Debug: mapped properties
        logger.debug(
            "Mapped properties for '%s':\n"
            "  - Gateway Type: %s\n"
            "  - VPC ID: %s\n"
            "  - Region: %s\n"
            "  - Tags: %s\n"
            "  - Traffic Direction: %s\n"
            "  - IP Version Support: %s",
            node_name,
            metadata.get("aws_gateway_type", "unknown"),
            vpc_id,
            region,
            tags,
            metadata.get("aws_traffic_direction", "unknown"),
            metadata.get("aws_ip_version_support", "unknown"),
        )

    def _add_vpc_dependency(
        self,
        igw_node,
        resource_data: dict[str, Any],
        node_name: str,
    ) -> None:
        """Add dependency relationship to the VPC if detected."""
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
                "Unable to access Terraform plan data to detect VPC dependency for "
                "'%s'",
                node_name,
            )
            return

        # Find VPC dependency
        vpc_dependency_added = False
        if parsed_data:
            terraform_refs = TerraformMapper.extract_terraform_references(
                resource_data, parsed_data
            )
            for prop_name, target_ref, _relationship_type in terraform_refs:
                if prop_name == "vpc_id" and not vpc_dependency_added:
                    if "." in target_ref:
                        # target_ref is like "aws_vpc.main"
                        target_resource_type = target_ref.split(".", 1)[0]
                        target_node_name = BaseResourceMapper.generate_tosca_node_name(
                            target_ref, target_resource_type
                        )
                        # Internet Gateway depends on VPC
                        igw_node.add_requirement("dependency").to_node(
                            target_node_name
                        ).with_relationship("DependsOn").and_node()

                        vpc_dependency_added = True
                        logger.info(
                            "Added dependency DependsOn from '%s' to VPC '%s'",
                            node_name,
                            target_node_name,
                        )
                        break

        if not vpc_dependency_added:
            logger.debug(
                "No VPC dependency detected for Internet Gateway '%s'", node_name
            )
