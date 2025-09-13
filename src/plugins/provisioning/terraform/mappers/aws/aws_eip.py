import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper
from src.plugins.provisioning.terraform.context import DependencyFilter
from src.plugins.provisioning.terraform.exceptions import ResourceMappingError

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.provisioning.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSEIPMapper(SingleResourceMapper):
    """Map a Terraform 'aws_eip' resource to a TOSCA Network node.

    Elastic IP addresses are static, public IPv4 addresses designed for
    dynamic cloud computing. They are mapped as Network nodes to represent
    their network-level IP addressing functionality.
    """

    def _extract_metadata_fields(
        self, metadata_values: dict[str, Any]
    ) -> dict[str, Any]:
        """Extract metadata fields from AWS EIP resource values.

        Args:
            metadata_values: Dictionary of resource values to extract from

        Returns:
            Dictionary of metadata fields with aws_ prefix
        """
        metadata = {}

        # Define fields to extract with their conditions
        field_mappings = {
            "domain": "aws_domain",
            "vpc": "aws_vpc",
            "instance": "aws_instance",
            "network_interface": "aws_network_interface",
            "associate_with_private_ip": "aws_associate_with_private_ip",
            "customer_owned_ipv4_pool": "aws_customer_owned_ipv4_pool",
            "allocation_id": "aws_allocation_id",
            "public_ip": "aws_public_ip",
            "private_ip": "aws_private_ip",
            "public_dns": "aws_public_dns",
            "private_dns": "aws_private_dns",
            "address": "aws_address",
            "id": "aws_id",
        }

        for source_field, metadata_key in field_mappings.items():
            value = metadata_values.get(source_field)
            if value is not None:
                metadata[metadata_key] = value

        # Handle special cases for tags
        tags = metadata_values.get("tags", {})
        if tags:
            metadata["aws_tags"] = tags

        tags_all = metadata_values.get("tags_all", {})
        if tags_all and tags_all != tags:
            metadata["aws_tags_all"] = tags_all

        return metadata

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

        # Generate a unique TOSCA node name using array-aware logic
        if context:
            node_name = context.generate_tosca_node_name_from_address(
                resource_name, resource_type
            )
        else:
            # Fallback to base mapper logic
            node_name = BaseResourceMapper.generate_tosca_node_name(
                resource_name, resource_type
            )

        # Extract the clean name for metadata (without the type prefix)
        if "." in resource_name:
            clean_name = resource_name.split(".", 1)[1]
        else:
            clean_name = resource_name

        # Create the Elastic IP node as a Network node
        try:
            eip_node = builder.add_node(name=node_name, node_type="Network")
        except Exception as e:
            raise ResourceMappingError(
                f"Failed to create TOSCA Network node: {e}",
                resource_name=resource_name,
                resource_type=resource_type,
                mapping_phase="node_creation",
            ) from e

        # Extract tags for node properties
        tags = values.get("tags", {})

        # Map properties to TOSCA Network
        # Set network type as public since EIPs are public IP addresses
        eip_node.with_property("network_type", "public")
        eip_node.with_property("ip_version", 4)  # EIPs are IPv4

        # Use Name tag if available, otherwise generate descriptive name
        name_tag = tags.get("Name")
        network_name = f"EIP-{name_tag}" if name_tag else f"EIP-{clean_name}"
        eip_node.with_property("network_name", network_name)

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

        # Extract AWS EIP specific metadata using helper method
        aws_metadata = self._extract_metadata_fields(metadata_values)
        metadata.update(aws_metadata)

        # Attach collected metadata to the node
        eip_node.with_metadata(metadata)

        # Add dependencies using injected context with intelligent filtering
        if context:
            # Create filter to exclude problematic dependencies
            dependency_filter = DependencyFilter(
                exclude_target_types={"aws_internet_gateway", "aws_vpc"}
            )

            terraform_refs = context.extract_filtered_terraform_references(
                resource_data, dependency_filter
            )
            logger.debug(
                f"Found {len(terraform_refs)} filtered terraform references "
                f"for {resource_name}"
            )

            for prop_name, target_ref, relationship_type in terraform_refs:
                logger.debug(
                    "Processing reference: %s -> %s (%s)",
                    prop_name,
                    target_ref,
                    relationship_type,
                )

                # target_ref is now already resolved to TOSCA node name by context
                target_node_name = target_ref

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
            logger.debug("  - Domain: %s", aws_metadata.get("aws_domain"))
            logger.debug("  - VPC: %s", aws_metadata.get("aws_vpc"))
            logger.debug("  - Public IP: %s", aws_metadata.get("aws_public_ip"))
            logger.debug("  - Allocation ID: %s", aws_metadata.get("aws_allocation_id"))
            logger.debug("  - Instance: %s", aws_metadata.get("aws_instance"))
            logger.debug(
                "  - Network Interface: %s", aws_metadata.get("aws_network_interface")
            )
            logger.debug("  - Tags: %s", aws_metadata.get("aws_tags"))
