import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSElastiCacheSubnetGroupMapper(SingleResourceMapper):
    """Map a Terraform 'aws_elasticache_subnet_group' to TOSCA policy.

    This mapper creates a Placement policy that governs the placement of
    ElastiCache nodes within specific subnets. The policy targets ElastiCache
    clusters and ensures they are placed within the appropriate subnet group
    for network connectivity and availability.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_elasticache_subnet_group'."""
        _ = resource_data  # Parameter required by protocol but not used
        return resource_type == "aws_elasticache_subnet_group"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Map aws_elasticache_subnet_group resource to TOSCA Placement policy.

        Args:
            resource_name: resource name (e.g. 'aws_elasticache_subnet_group.bar')
            resource_type: resource type (always 'aws_elasticache_subnet_group')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for variable resolution and
                dependency analysis
        """
        logger.info("Mapping ElastiCache Subnet Group resource: '%s'", resource_name)

        # Debug: Log the raw resource data
        logger.debug("Raw resource_data: %s", resource_data)

        # Get resolved values using the context for properties
        if context:
            values = context.get_resolved_values(resource_data, "property")
            logger.debug("Resolved values: %s", values)
        else:
            # Fallback to original values if no context available
            values = resource_data.get("values", {})
            logger.debug("Original values (no context): %s", values)

        if not values:
            logger.warning(
                "Resource '%s' has no 'values' section. Skipping.", resource_name
            )
            return

        # Check for subnet_ids in values or configuration expressions
        subnet_ids = values.get("subnet_ids", [])
        has_subnet_references = False

        # If no direct subnet_ids, check for Terraform references in configuration
        if not subnet_ids and context:
            terraform_refs = context.extract_terraform_references(resource_data)
            logger.debug(
                "Found %d terraform references for %s: %s",
                len(terraform_refs),
                resource_name,
                terraform_refs,
            )
            # Debug: print the parsed_data structure to see configuration
            logger.debug("Context parsed_data keys: %s", context.parsed_data.keys())
            if "plan" in context.parsed_data:
                plan_config = context.parsed_data["plan"].get("configuration", {})
                logger.debug("Plan configuration keys: %s", plan_config.keys())
            for prop_name, _, _ in terraform_refs:
                if prop_name == "subnet_ids":
                    has_subnet_references = True
                    break

        # Validate that we have either concrete subnet_ids or references
        if not subnet_ids and not has_subnet_references:
            logger.error(
                "Resource '%s' missing required field 'subnet_ids' and no "
                "subnet references found. Skipping.",
                resource_name,
            )
            return

        # Generate a unique TOSCA policy name using the utility function
        policy_name = BaseResourceMapper.generate_tosca_node_name(
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

        # Build comprehensive metadata with Terraform and AWS information
        metadata: dict[str, Any] = {}

        # Original resource information
        metadata["original_resource_type"] = resource_type
        metadata["original_resource_name"] = clean_name
        metadata["aws_component_type"] = "ElastiCacheSubnetGroup"
        metadata["description"] = (
            "AWS ElastiCache Subnet Group for cache placement within VPC subnets"
        )

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["terraform_provider"] = provider_name

        # Core ElastiCache Subnet Group properties - use metadata values for
        # concrete resolution and put in metadata (not properties)
        subnet_group_name = values.get("name")
        metadata_subnet_group_name = metadata_values.get("name")
        if metadata_subnet_group_name:
            metadata["aws_cache_subnet_group_name"] = metadata_subnet_group_name

        # Description for the subnet group
        metadata_description = metadata_values.get("description")
        if metadata_description:
            metadata["aws_cache_subnet_group_description"] = metadata_description

        # Subnet IDs (already validated above) - define placement constraints
        metadata_subnet_ids = metadata_values.get("subnet_ids", [])
        if metadata_subnet_ids:
            metadata["aws_subnet_ids"] = metadata_subnet_ids
            metadata["aws_subnet_count"] = len(metadata_subnet_ids)

        # Add placement-specific metadata
        if subnet_ids or has_subnet_references:
            metadata["placement_zone"] = "cache_subnet_group"
            metadata["subnet_group_name"] = subnet_group_name or clean_name
            # Use subnet count if available, otherwise indicate reference-based
            if subnet_ids:
                metadata["availability_zones_count"] = len(subnet_ids)
            else:
                metadata["availability_zones"] = "referenced"

        # Extract subnet information to get availability zones (if context available)
        if context:
            subnet_info = self._extract_subnet_information(resource_data, context)
            if subnet_info:
                metadata["aws_subnet_details"] = subnet_info
                metadata["aws_availability_zones"] = [
                    subnet["availability_zone"]
                    for subnet in subnet_info
                    if subnet.get("availability_zone")
                ]

        # Region information
        metadata_region = metadata_values.get("region")
        if metadata_region:
            metadata["aws_region"] = metadata_region

        # Tags for the subnet group
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        # Tags_all (all tags including provider defaults)
        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

        # Computed attributes from AWS
        metadata_arn = metadata_values.get("arn")
        if metadata_arn:
            metadata["aws_arn"] = metadata_arn

        metadata_cache_subnet_group_id = metadata_values.get("id")
        if metadata_cache_subnet_group_id:
            metadata["aws_cache_subnet_group_id"] = metadata_cache_subnet_group_id

        metadata_vpc_id = metadata_values.get("vpc_id")
        if metadata_vpc_id:
            metadata["aws_vpc_id"] = metadata_vpc_id

        # Create the Placement policy
        policy_builder = builder.add_policy(policy_name, "Placement")

        # Add metadata to the policy (no properties for Placement type)
        policy_builder.with_metadata(metadata)

        # Find and add targets - ElastiCache nodes that use this subnet group
        targets_added = False
        if context:
            target_nodes = self._find_elasticache_targets(
                metadata_subnet_group_name or subnet_group_name, clean_name, context
            )
            if target_nodes:
                policy_builder.with_targets(*target_nodes)
                targets_added = True
                logger.info(
                    "Policy '%s' will target %d ElastiCache nodes: %s",
                    policy_name,
                    len(target_nodes),
                    target_nodes,
                )

        # If no ElastiCache targets found, this policy could target any
        # future ElastiCache nodes that might reference this subnet group
        if not targets_added:
            logger.info(
                "Policy '%s' has no specific targets - it will govern "
                "placement for any ElastiCache resources using subnet group '%s'",
                policy_name,
                subnet_group_name or clean_name,
            )

        policy_builder.and_service()

        # Log success with appropriate subnet count information
        if subnet_ids:
            subnet_count_msg = f"with {len(subnet_ids)} subnets"
        elif has_subnet_references:
            subnet_count_msg = "with referenced subnets"
        else:
            subnet_count_msg = "with unknown subnet count"

        logger.info(
            "Successfully created Placement policy '%s' for ElastiCache Subnet "
            "Group %s",
            policy_name,
            subnet_count_msg,
        )

        # Debug: mapped metadata - use metadata values for concrete display
        logger.debug(
            "Mapped ElastiCache Subnet Group metadata for '%s':\n"
            "  - Name: %s\n"
            "  - Description: %s\n"
            "  - Subnet IDs: %s\n"
            "  - Region: %s\n"
            "  - VPC ID: %s\n"
            "  - Tags: %s\n"
            "  - ARN: %s\n"
            "  - Placement Zone: %s\n"
            "  - Targets Added: %s",
            policy_name,
            metadata_subnet_group_name,
            metadata_description,
            metadata_subnet_ids,
            metadata_region,
            metadata_vpc_id,
            metadata_tags,
            metadata_arn,
            metadata.get("placement_zone", "N/A"),
            targets_added,
        )

    def _extract_subnet_information(
        self, resource_data: dict[str, Any], context: "TerraformMappingContext"
    ) -> list[dict[str, Any]]:
        """Extract detailed information about subnets referenced by this group.

        Args:
            resource_data: Resource data from Terraform plan
            context: TerraformMappingContext containing parsed data

        Returns:
            List of subnet information dictionaries with details like AZ
        """
        subnet_info: list[dict[str, Any]] = []

        # Extract Terraform references using context to find subnet references
        terraform_refs = context.extract_terraform_references(resource_data)

        # Get planned values from context to find subnet resources
        parsed_data = context.parsed_data
        if not parsed_data:
            logger.debug("Could not access parsed_data for subnet information")
            return subnet_info

        planned_values = parsed_data.get("planned_values", {})
        root_module = planned_values.get("root_module", {})

        # Find subnet resources that match our references
        subnet_references = []
        for prop_name, target_ref, _ in terraform_refs:
            if prop_name == "subnet_ids" and "aws_subnet" in target_ref:
                subnet_references.append(target_ref)

        for resource in root_module.get("resources", []):
            if resource.get("type") == "aws_subnet":
                subnet_address = resource.get("address", "")
                subnet_values = resource.get("values", {})

                # Check if this subnet is referenced by our subnet group
                for subnet_ref in subnet_references:
                    if subnet_address == subnet_ref:
                        subnet_detail = {
                            "subnet_address": subnet_address,
                            "cidr_block": subnet_values.get("cidr_block"),
                            "availability_zone": subnet_values.get("availability_zone"),
                            "map_public_ip_on_launch": subnet_values.get(
                                "map_public_ip_on_launch", False
                            ),
                        }
                        subnet_name = subnet_values.get("tags", {}).get("Name")
                        if subnet_name:
                            subnet_detail["name"] = subnet_name

                        subnet_info.append(subnet_detail)
                        break

        logger.debug("Extracted subnet information: %d subnets found", len(subnet_info))
        return subnet_info

    def _find_elasticache_targets(
        self,
        subnet_group_name: str | None,
        clean_name: str,
        context: "TerraformMappingContext",
    ) -> list[str]:
        """Find ElastiCache nodes targeted by this placement policy.

        Args:
            subnet_group_name: Name of the ElastiCache subnet group
            clean_name: Clean resource name as fallback
            context: TerraformMappingContext containing parsed data

        Returns:
            List of ElastiCache node names that should be targeted
        """
        targets: list[str] = []

        # Get parsed data from context to find ElastiCache resources
        parsed_data = context.parsed_data
        if not parsed_data:
            logger.debug("Could not access parsed_data for target identification")
            return targets

        # Look for ElastiCache resources that reference this subnet group
        planned_values = parsed_data.get("planned_values", {})
        root_module = planned_values.get("root_module", {})

        target_subnet_group = subnet_group_name or clean_name

        # Check both cluster and replication group resources
        elasticache_resource_types = [
            "aws_elasticache_cluster",
            "aws_elasticache_replication_group",
        ]

        for resource in root_module.get("resources", []):
            resource_type = resource.get("type")
            if resource_type in elasticache_resource_types:
                elasticache_values = resource.get("values", {})
                elasticache_subnet_group = elasticache_values.get("subnet_group_name")

                # Check if this ElastiCache resource uses our subnet group
                if elasticache_subnet_group == target_subnet_group:
                    elasticache_address = resource.get("address", "")
                    if elasticache_address:
                        # Generate the TOSCA node name for the ElastiCache resource
                        cache_node_name = BaseResourceMapper.generate_tosca_node_name(
                            elasticache_address, resource_type
                        )
                        targets.append(cache_node_name)

                        logger.debug(
                            "Found ElastiCache resource '%s' using subnet group '%s'",
                            elasticache_address,
                            target_subnet_group,
                        )

        return targets
