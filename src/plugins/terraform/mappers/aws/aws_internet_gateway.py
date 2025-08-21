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
    """Map a Terraform 'aws_internet_gateway' resource to a TOSCA Root node.

    An Internet Gateway provides internet connectivity to a VPC.
    Since TOSCA doesn't have a specific Gateway type, we use Root with
    appropriate capabilities and metadata.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_internet_gateway'."""
        return resource_type == "aws_internet_gateway"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
    ) -> None:
        """Translate an aws_internet_gateway resource into a TOSCA Root node.

        Args:
            resource_name: resource name (e.g. 'aws_internet_gateway.gw')
            resource_type: resource type (always 'aws_internet_gateway')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
        """
        logger.info("Mapping Internet Gateway resource: '%s'", resource_name)

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
        metadata["aws_component_type"] = "InternetGateway"
        metadata["description"] = "AWS Internet Gateway providing internet connectivity"

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

        # Set Network properties appropriate for an Internet Gateway
        # This represents a public internet connection
        igw_node.with_property("network_name", "INTERNET")
        igw_node.with_property("network_type", "public")

        # Use Name tag if available, otherwise use a descriptive name
        if tags and "Name" in tags:
            igw_node.with_property("network_name", f"IGW-{tags['Name']}")

        # Add the standard 'link' capability for Network nodes
        igw_node.add_capability("link").and_node()

        # Detect VPC dependency using the Terraform reference system
        self._add_vpc_dependency(igw_node, resource_data, node_name)

        logger.debug("Internet Gateway node '%s' created successfully.", node_name)

        # Debug: mapped properties
        logger.debug(
            "Mapped properties for '%s':\n"
            "  - VPC ID: %s\n"
            "  - Region: %s\n"
            "  - Tags: %s",
            node_name,
            vpc_id,
            region,
            tags,
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
