import inspect
import logging
from typing import TYPE_CHECKING, Any

from core.common.base_mapper import BaseResourceMapper
from core.protocols import SingleResourceMapper
from plugins.terraform.mapper import TerraformMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder

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
    ) -> None:
        """Translate an aws_subnet resource into a TOSCA Network node.

        Args:
            resource_name: resource name (e.g. 'aws_subnet.subnet')
            resource_type: resource type (always 'aws_subnet')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
        """
        logger.info("Mapping Subnet resource: '%s'", resource_name)

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

        # Create the Network node representing the subnet
        subnet_node = builder.add_node(name=node_name, node_type="Network")

        # Build metadata with Terraform and AWS information
        metadata: dict[str, Any] = {}

        # Original resource information (name without the aws_subnet prefix)
        metadata["original_resource_type"] = resource_type
        metadata["original_resource_name"] = clean_name

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # Extract subnet properties and map them to Network node properties
        # CIDR block of the subnet
        cidr_block = values.get("cidr_block")
        if cidr_block:
            subnet_node.with_property("cidr", cidr_block)

        # Availability Zone -> mapped to network_name for identification
        availability_zone = values.get("availability_zone")
        if availability_zone:
            subnet_node.with_property("network_name", f"subnet-{availability_zone}")
            metadata["aws_availability_zone"] = availability_zone

        # IPv6 CIDR block
        ipv6_cidr_block = values.get("ipv6_cidr_block")
        if ipv6_cidr_block:
            subnet_node.with_property("ipv6_cidr", ipv6_cidr_block)
            metadata["aws_ipv6_cidr_block"] = ipv6_cidr_block

        # Public IP assignment behavior
        map_public_ip_on_launch = values.get("map_public_ip_on_launch")
        if map_public_ip_on_launch is not None:
            metadata["aws_map_public_ip_on_launch"] = map_public_ip_on_launch

        # VPC ID (stored in metadata, used later for requirements)
        vpc_id = values.get("vpc_id")
        if vpc_id:
            metadata["aws_vpc_id"] = vpc_id

        # Tags for the subnet
        tags = values.get("tags", {})
        if tags:
            if "Name" in tags:
                subnet_node.with_property("network_name", tags["Name"])
            metadata["aws_tags"] = tags

        # Customer-owned IP pool (only for Outpost subnets)
        customer_owned_ipv4_pool = values.get("customer_owned_ipv4_pool")
        if customer_owned_ipv4_pool:
            metadata["aws_customer_owned_ipv4_pool"] = customer_owned_ipv4_pool

        # Map public IP on customer-owned pool
        map_customer_owned_ip_on_launch = values.get("map_customer_owned_ip_on_launch")
        if map_customer_owned_ip_on_launch is not None:
            metadata["aws_map_customer_owned_ip_on_launch"] = (
                map_customer_owned_ip_on_launch
            )

        # Outpost ARN (present for Outpost subnets)
        outpost_arn = values.get("outpost_arn")
        if outpost_arn:
            metadata["aws_outpost_arn"] = outpost_arn

        # Attach collected metadata to the node
        subnet_node.with_metadata(metadata)

        # Add the standard 'link' capability for Network nodes
        subnet_node.add_capability("link").and_node()

        # Simple detection of the VPC dependency
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
                "Unable to access Terraform plan data to detect requirements"
            )

        # Find only the VPC dependency
        vpc_dependency_added = False
        if parsed_data:
            terraform_refs = TerraformMapper.extract_terraform_references(
                resource_data, parsed_data
            )
            for prop_name, target_ref, relationship_type in terraform_refs:
                if prop_name == "vpc_id" and not vpc_dependency_added:
                    if "." in target_ref:
                        # target_ref è del tipo "aws_vpc.main"
                        # target_ref is like "aws_vpc.main"
                        target_resource_type = target_ref.split(".", 1)[0]
                        target_node_name = BaseResourceMapper.generate_tosca_node_name(
                            target_ref, target_resource_type
                        )
                        (
                            subnet_node.add_requirement("dependency")
                            .to_node(target_node_name)
                            .with_relationship(relationship_type)
                            .and_node()
                        )
                        vpc_dependency_added = True
                        logger.info(
                            "Added dependency %s to '%s' for VPC",
                            relationship_type,
                            target_node_name,
                        )
                        break  # Solo una dipendenza VPC

        logger.debug("Network Subnet node '%s' created successfully.", node_name)

        # Debug: mapped properties (single log)
        ingress_launch = map_public_ip_on_launch
        customer_launch = map_customer_owned_ip_on_launch
        logger.debug(
            "Mapped properties for '%s':\n"
            "  - CIDR Block: %s\n"
            "  - Availability Zone: %s\n"
            "  - IPv6 CIDR: %s\n"
            "  - Public IP on Launch: %s\n"
            "  - VPC ID: %s\n"
            "  - Tags: %s\n"
            "  - Customer-owned IP on Launch: %s",
            node_name,
            cidr_block,
            availability_zone,
            ipv6_cidr_block,
            ingress_launch,
            vpc_id,
            tags,
            customer_launch,
        )
