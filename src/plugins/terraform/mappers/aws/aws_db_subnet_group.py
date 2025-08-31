import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSDBSubnetGroupMapper(SingleResourceMapper):
    """Map a Terraform 'aws_db_subnet_group' resource to a TOSCA Placement policy.

    This mapper creates a Placement policy that governs the placement of
    database nodes within specific subnets. The policy targets database
    nodes and ensures they are placed within the appropriate subnet group
    for network connectivity and availability.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_db_subnet_group'."""
        return resource_type == "aws_db_subnet_group"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Map aws_db_subnet_group resource to a TOSCA Placement policy.

        Args:
            resource_name: resource name (e.g. 'aws_db_subnet_group.default')
            resource_type: resource type (always 'aws_db_subnet_group')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
        """
        logger.info("Mapping DB Subnet Group resource: '%s'", resource_name)

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
        metadata["aws_component_type"] = "DBSubnetGroup"
        metadata["description"] = (
            "AWS RDS DB Subnet Group for database placement within VPC subnets"
        )

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["terraform_provider"] = provider_name

        # Core DB Subnet Group properties - use metadata values for concrete resolution
        subnet_group_name = values.get("name")
        metadata_subnet_group_name = metadata_values.get("name")
        if metadata_subnet_group_name:
            metadata["aws_db_subnet_group_name"] = metadata_subnet_group_name

        # Description for the subnet group
        metadata_description = metadata_values.get("description")
        if metadata_description:
            metadata["aws_db_subnet_group_description"] = metadata_description

        # Subnet IDs (required) - these define the placement constraints
        subnet_ids = values.get("subnet_ids", [])
        metadata_subnet_ids = metadata_values.get("subnet_ids", [])
        if metadata_subnet_ids:
            metadata["aws_subnet_ids"] = metadata_subnet_ids
            metadata["aws_subnet_count"] = len(metadata_subnet_ids)

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

        # Name prefix if used instead of explicit name
        metadata_name_prefix = metadata_values.get("name_prefix")
        if metadata_name_prefix:
            metadata["aws_name_prefix"] = metadata_name_prefix

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

        metadata_db_subnet_group_id = metadata_values.get("id")
        if metadata_db_subnet_group_id:
            metadata["aws_db_subnet_group_id"] = metadata_db_subnet_group_id

        metadata_supported_network_types = metadata_values.get(
            "supported_network_types", []
        )
        if metadata_supported_network_types:
            metadata["aws_supported_network_types"] = metadata_supported_network_types

        metadata_vpc_id = metadata_values.get("vpc_id")
        if metadata_vpc_id:
            metadata["aws_vpc_id"] = metadata_vpc_id

        # Create the Placement policy
        policy_builder = builder.add_policy(policy_name, "Placement")

        # Set policy properties based on subnet configuration
        if subnet_ids:
            # Define placement properties based on subnet configuration
            policy_builder.with_property("placement_zone", "subnet_group")
            policy_builder.with_property(
                "subnet_group_name", subnet_group_name or clean_name
            )
            policy_builder.with_property("availability_zones", len(subnet_ids))

        # Add metadata to the policy
        policy_builder.with_metadata(metadata)

        # Find and add targets - database nodes that use this subnet group (if
        # context available)
        if context:
            target_nodes = self._find_database_targets(
                metadata_subnet_group_name or subnet_group_name, clean_name, context
            )
            if target_nodes:
                policy_builder.with_targets(*target_nodes)
                logger.info(
                    "Policy '%s' will target %d database nodes: %s",
                    policy_name,
                    len(target_nodes),
                    target_nodes,
                )

        # Determine targets - look for database nodes that should be affected
        # by this policy. For now, we'll set an empty targets list and let
        # other mappers reference this policy. In a complete implementation,
        # we could scan for database nodes and auto-target them

        policy_builder.and_service()

        logger.info(
            "Successfully created Placement policy '%s' for DB Subnet Group "
            "with %d subnets",
            policy_name,
            len(subnet_ids),
        )

        # Debug: mapped properties - use metadata values for concrete display
        logger.debug(
            "Mapped DB Subnet Group properties for '%s':\n"
            "  - Name: %s\n"
            "  - Description: %s\n"
            "  - Subnet IDs: %s\n"
            "  - Region: %s\n"
            "  - VPC ID: %s\n"
            "  - Tags: %s\n"
            "  - ARN: %s",
            policy_name,
            metadata_subnet_group_name,
            metadata_description,
            metadata_subnet_ids,
            metadata_region,
            metadata_vpc_id,
            metadata_tags,
            metadata_arn,
        )

    def _extract_subnet_information(
        self, resource_data: dict[str, Any], context: "TerraformMappingContext"
    ) -> list[dict[str, Any]]:
        """Extract detailed information about the subnets referenced by this group.

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
        for prop_name, target_ref, _relationship_type in terraform_refs:
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

    def _find_database_targets(
        self,
        subnet_group_name: str | None,
        clean_name: str,
        context: "TerraformMappingContext",
    ) -> list[str]:
        """Find database nodes that should be targeted by this placement policy.

        Args:
            subnet_group_name: Name of the DB subnet group
            clean_name: Clean resource name as fallback
            context: TerraformMappingContext containing parsed data

        Returns:
            List of database node names that should be targeted
        """
        targets: list[str] = []

        # Get parsed data from context to find database instances
        parsed_data = context.parsed_data
        if not parsed_data:
            logger.debug("Could not access parsed_data for target identification")
            return targets

        # Look for database instances that reference this subnet group
        planned_values = parsed_data.get("planned_values", {})
        root_module = planned_values.get("root_module", {})

        target_subnet_group = subnet_group_name or clean_name

        for resource in root_module.get("resources", []):
            if resource.get("type") == "aws_db_instance":
                db_values = resource.get("values", {})
                db_subnet_group = db_values.get("db_subnet_group_name")

                # Check if this database uses our subnet group
                if db_subnet_group == target_subnet_group:
                    db_address = resource.get("address", "")
                    if db_address:
                        # Generate the TOSCA node names for both DBMS and Database
                        dbms_node_name = BaseResourceMapper.generate_tosca_node_name(
                            db_address + "_dbms", "aws_db_instance"
                        )
                        database_node_name = (
                            BaseResourceMapper.generate_tosca_node_name(
                                db_address + "_database", "aws_db_instance"
                            )
                        )

                        targets.extend([dbms_node_name, database_node_name])

                        logger.debug(
                            "Found database instance '%s' using subnet group '%s'",
                            db_address,
                            target_subnet_group,
                        )

        return targets
