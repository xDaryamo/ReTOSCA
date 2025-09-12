import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.provisioning.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSVPCIpv4CidrBlockAssociationMapper(SingleResourceMapper):
    """Map a Terraform
        'aws_vpc_ipv4_cidr_block_association' resource to a TOSCA Network node.

    This mapper creates a Network node for each additional IPv4 CIDR block associated
    with a VPC, establishing a relationship with the parent VPC.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_vpc_ipv4_cidr_block_association'."""
        return resource_type == "aws_vpc_ipv4_cidr_block_association"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Translate an aws_vpc_ipv4_cidr_block_association into a TOSCA Network node.

        Args:
            resource_name: resource name
                (e.g. 'aws_vpc_ipv4_cidr_block_association.example')
            resource_type: resource type (always 'aws_vpc_ipv4_cidr_block_association')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for variable resolution
        """
        logger.info(
            "Mapping VPC IPv4 CIDR Block Association resource: '%s'", resource_name
        )

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
            _, clean_name = resource_name.split(".", 1)
        else:
            clean_name = resource_name

        # Create the Network node for the additional CIDR block
        cidr_network_node = builder.add_node(name=node_name, node_type="Network")

        # Extract AWS VPC CIDR Association properties and map them to
        # TOSCA Network properties

        # CIDR block - the additional IPv4 CIDR block
        cidr_block = values.get("cidr_block")

        # VPC ID - reference to the parent VPC
        vpc_id = values.get("vpc_id")

        # Map standard TOSCA Network properties

        # Set CIDR block as the main network property
        if cidr_block:
            cidr_network_node.with_property("cidr", cidr_block)

        # Set network name based on CIDR block
        if cidr_block:
            cidr_network_node.with_property(
                "network_name",
                f"additional_cidr_{cidr_block.replace('/', '_').replace('.', '_')}",
            )
        else:
            cidr_network_node.with_property("network_name", clean_name)

        # Set network type to indicate this is an additional CIDR block
        cidr_network_node.with_property("network_type", "additional_cidr")

        # IPv4 network
        cidr_network_node.with_property("ip_version", 4)

        # DHCP is enabled by default in AWS VPCs
        cidr_network_node.with_property("dhcp_enabled", True)

        # Add the standard 'link' capability for Network nodes
        cidr_network_node.add_capability("link").and_node()

        # Get resolved values specifically for metadata (always concrete values)
        if context:
            metadata_values = context.get_resolved_values(resource_data, "metadata")
        else:
            metadata_values = resource_data.get("values", {})

        # Build metadata containing Terraform and AWS information
        metadata: dict[str, Any] = {}

        # Original resource information
        metadata["original_resource_type"] = resource_type
        metadata["original_resource_name"] = clean_name
        metadata["aws_component_type"] = "VPCIpv4CidrBlockAssociation"
        metadata["description"] = "Additional IPv4 CIDR block associated with a VPC"

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # AWS VPC CIDR Association specific information - use
        # metadata_values for concrete values
        metadata_cidr_block = metadata_values.get("cidr_block")
        if metadata_cidr_block:
            metadata["aws_cidr_block"] = metadata_cidr_block

        metadata_vpc_id = metadata_values.get("vpc_id")
        if metadata_vpc_id:
            metadata["aws_vpc_id"] = metadata_vpc_id

        # Association ID (populated after creation)
        metadata_association_id = metadata_values.get("id")
        if metadata_association_id:
            metadata["aws_association_id"] = metadata_association_id

        # Region information
        metadata_region = metadata_values.get("region")
        if metadata_region:
            metadata["aws_region"] = metadata_region

        # Timeouts configuration
        metadata_timeouts = metadata_values.get("timeouts")
        if metadata_timeouts:
            metadata["terraform_timeouts"] = metadata_timeouts

        # Attach all metadata to the node
        cidr_network_node.with_metadata(metadata)

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

                # target_ref is now already resolved to TOSCA node name by context
                target_node_name = target_ref

                # Add requirement with the property name as the requirement name
                requirement_name = (
                    prop_name if prop_name not in ["dependency"] else "dependency"
                )

                (
                    cidr_network_node.add_requirement(requirement_name)
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

            # If no automatic reference was found to the VPC, try to find it manually
            if not terraform_refs and vpc_id:
                vpc_node_name = self._find_vpc_node_name(context, vpc_id, builder)
                if vpc_node_name:
                    (
                        cidr_network_node.add_requirement("vpc_dependency")
                        .to_node(vpc_node_name)
                        .with_relationship("DependsOn")
                        .and_node()
                    )
                    logger.info(
                        "Added VPC dependency requirement: %s -> %s",
                        node_name,
                        vpc_node_name,
                    )
                else:
                    logger.warning(
                        "Could not find VPC node for CIDR association '%s' "
                        "with vpc_id '%s'",
                        resource_name,
                        vpc_id,
                    )
        else:
            logger.warning(
                "No context provided to detect dependencies for resource '%s'",
                resource_name,
            )

        logger.debug(
            "VPC CIDR Association Network node '%s' created successfully.", node_name
        )

        # Log mapped properties for debugging
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Mapped properties for '%s':", node_name)
            logger.debug("  - CIDR Block: %s", metadata_cidr_block)
            logger.debug("  - VPC ID: %s", metadata_vpc_id)
            logger.debug("  - Association ID: %s", metadata_association_id)
            logger.debug("  - Region: %s", metadata_region)

    def _find_vpc_node_name(
        self,
        context: "TerraformMappingContext | None",
        vpc_id: str,
        builder: "ServiceTemplateBuilder",
    ) -> str | None:
        """Find the TOSCA node name for a VPC by its AWS ID.

        Args:
            context: TerraformMappingContext containing parsed data
            vpc_id: AWS VPC ID to search for
            builder: ServiceTemplateBuilder to search existing nodes

        Returns:
            TOSCA node name if found, None otherwise
        """
        if not context:
            return None

        # Look for VPC resource with matching ID
        vpc_address = self._find_terraform_address_by_aws_id(context, vpc_id, "aws_vpc")
        if vpc_address:
            # Generate the TOSCA node name for this VPC
            return context.generate_tosca_node_name_from_address(vpc_address, "aws_vpc")

        return None

    def _find_terraform_address_by_aws_id(
        self,
        context: "TerraformMappingContext",
        aws_resource_id: str,
        resource_type: str,
    ) -> str | None:
        """Find Terraform address by AWS resource ID.

        Args:
            context: TerraformMappingContext containing parsed data
            aws_resource_id: AWS resource ID (e.g., 'vpc-123abc')
            resource_type: Terraform resource type (e.g., 'aws_vpc')

        Returns:
            Terraform address (e.g., 'aws_vpc.main') or None if not found
        """
        # Look in state data for resources with matching AWS ID
        state_data = context.parsed_data.get("state", {})
        values = state_data.get("values", {})
        if values:
            root_module = values.get("root_module", {})
            resources = root_module.get("resources", [])

            for resource in resources:
                if (
                    resource.get("type") == resource_type
                    and resource.get("values", {}).get("id") == aws_resource_id
                ):
                    return resource.get("address")

        # Also check in planned_values (for plan JSON)
        planned_values = context.parsed_data.get("planned_values", {})
        if planned_values:
            root_module = planned_values.get("root_module", {})
            resources = root_module.get("resources", [])

            for resource in resources:
                if (
                    resource.get("type") == resource_type
                    and resource.get("values", {}).get("id") == aws_resource_id
                ):
                    return resource.get("address")

        return None
