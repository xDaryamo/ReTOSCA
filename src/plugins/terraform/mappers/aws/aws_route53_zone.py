import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSRoute53ZoneMapper(SingleResourceMapper):
    """Map a Terraform 'aws_route53_zone' resource to a TOSCA Network node.

    AWS Route53 Hosted Zone represents a DNS network service that manages DNS records
    for a particular domain. It's mapped to a Network as it provides network-level
    domain name resolution services and logical network organization.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_route53_zone'."""
        _ = resource_data  # Parameter required by protocol but not used
        return resource_type == "aws_route53_zone"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Map aws_route53_zone resource to TOSCA Network node.

        Args:
            resource_name: resource name (e.g. 'aws_route53_zone.primary')
            resource_type: resource type (always 'aws_route53_zone')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for variable resolution and
                dependency analysis
        """
        logger.info("Mapping Route53 Hosted Zone resource: '%s'", resource_name)

        # Debug: Log the raw resource data
        logger.debug("Raw resource_data: %s", resource_data)

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

        # Get resolved values specifically for metadata (always concrete values)
        if context:
            metadata_values = context.get_resolved_values(resource_data, "metadata")
        else:
            metadata_values = resource_data.get("values", {})

        # Create the Network node for the Route53 Hosted Zone
        zone_node = builder.add_node(
            name=node_name,
            node_type="Network",
        )

        # Map Route53 Zone properties to TOSCA Network properties
        # Domain name is the primary identifier for the DNS network
        domain_name = values.get("name")

        # Set Network properties that make sense for a DNS zone
        network_properties = {}

        # Use the domain name as the network_name
        if domain_name:
            network_properties["network_name"] = domain_name

        # Check if this is a private hosted zone (has VPC associations)
        vpc_associations = values.get("vpc", [])
        if vpc_associations:
            # For private zones, we can infer some network properties
            network_properties["network_type"] = "private"
            # Typically true for private zones
            network_properties["dhcp_enabled"] = True
        else:
            # Public hosted zone
            network_properties["network_type"] = "public"
            # Not applicable for public DNS
            network_properties["dhcp_enabled"] = False

        # Set the Network properties
        if network_properties:
            zone_node.with_properties(network_properties)

        # Build comprehensive metadata with Terraform and AWS information
        metadata: dict[str, Any] = {}

        # Original resource information
        metadata["original_resource_type"] = resource_type
        metadata["original_resource_name"] = clean_name
        metadata["aws_component_type"] = "Route53HostedZone"
        metadata["description"] = (
            "AWS Route53 Hosted Zone for DNS management of domain: "
            f"{domain_name or 'unknown'}"
        )

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["terraform_provider"] = provider_name

        # Core Route53 Hosted Zone properties - use metadata values for
        # concrete resolution and put in metadata (not properties)
        metadata_domain_name = metadata_values.get("name")
        if metadata_domain_name:
            metadata["aws_domain_name"] = metadata_domain_name

        # Comment/description for the hosted zone
        metadata_comment = metadata_values.get("comment")
        if metadata_comment:
            metadata["aws_zone_comment"] = metadata_comment

        # Hosted zone type (public/private)
        metadata_zone_type = "public"  # Default type
        force_destroy = metadata_values.get("force_destroy")
        if force_destroy is not None:
            metadata["aws_force_destroy"] = force_destroy

        # VPC associations for private hosted zones
        vpc_associations = metadata_values.get("vpc", [])
        if vpc_associations:
            metadata["aws_vpc_associations"] = vpc_associations
            metadata["aws_zone_type"] = "private"
        else:
            metadata["aws_zone_type"] = metadata_zone_type

        # Delegation set ID
        metadata_delegation_set_id = metadata_values.get("delegation_set_id")
        if metadata_delegation_set_id:
            metadata["aws_delegation_set_id"] = metadata_delegation_set_id

        # Region information
        metadata_region = metadata_values.get("region")
        if metadata_region:
            metadata["aws_region"] = metadata_region

        # Tags for the hosted zone
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        # Tags_all (all tags including provider defaults)
        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

        # Computed attributes from AWS (available after creation)
        metadata_arn = metadata_values.get("arn")
        if metadata_arn:
            metadata["aws_arn"] = metadata_arn

        metadata_zone_id = metadata_values.get("zone_id")
        if metadata_zone_id:
            metadata["aws_zone_id"] = metadata_zone_id

        metadata_name_servers = metadata_values.get("name_servers", [])
        if metadata_name_servers:
            metadata["aws_name_servers"] = metadata_name_servers

        metadata_primary_name_server = metadata_values.get("primary_name_server")
        if metadata_primary_name_server:
            metadata["aws_primary_name_server"] = metadata_primary_name_server

        # Hosted zone ID (same as zone_id but sometimes separate attribute)
        metadata_hosted_zone_id = metadata_values.get("id")
        if metadata_hosted_zone_id:
            metadata["aws_hosted_zone_id"] = metadata_hosted_zone_id

        # Attach all metadata to the node
        zone_node.with_metadata(metadata)

        # Add dependencies using injected context
        if context:
            terraform_refs = context.extract_terraform_references(resource_data)
            logger.debug(
                "Found %d terraform references for %s",
                len(terraform_refs),
                resource_name,
            )

            for prop_name, target_ref, relationship_type in terraform_refs:
                logger.debug(
                    "Processing reference: %s -> %s (%s)",
                    prop_name,
                    target_ref,
                    relationship_type,
                )

                if "." in target_ref:
                    target_resource_type = target_ref.split(".", 1)[0]
                    target_node_name = BaseResourceMapper.generate_tosca_node_name(
                        target_ref, target_resource_type
                    )

                    # Add requirement with the property name as the requirement name
                    requirement_name = (
                        prop_name if prop_name not in ["dependency"] else "dependency"
                    )

                    (
                        zone_node.add_requirement(requirement_name)
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

        logger.info(
            "Successfully created Network node '%s' for Route53 Hosted Zone '%s'",
            node_name,
            metadata_domain_name or domain_name,
        )

        # Debug: mapped properties - use metadata values for concrete display
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Mapped Route53 Hosted Zone properties for '%s':", node_name)
            logger.debug("  - Domain name: %s", metadata_domain_name)
            logger.debug("  - Zone type: %s", metadata.get("aws_zone_type"))
            logger.debug("  - Comment: %s", metadata_comment)
            logger.debug("  - Region: %s", metadata_region)
            logger.debug("  - VPC associations: %s", vpc_associations)
            logger.debug("  - Tags: %s", metadata_tags)
            logger.debug("  - Zone ID: %s", metadata_zone_id)
            logger.debug("  - Name servers: %s", metadata_name_servers)
            logger.debug("  - ARN: %s", metadata_arn)
