import inspect
import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper
from src.plugins.terraform.mapper import TerraformMapper
from src.plugins.terraform.terraform_mapper_base import TerraformResourceMapperMixin

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder

logger = logging.getLogger(__name__)


class AWSDBSubnetGroupMapper(TerraformResourceMapperMixin, SingleResourceMapper):
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
    ) -> None:
        """Map aws_db_subnet_group resource to a TOSCA Placement policy.

        Args:
            resource_name: resource name (e.g. 'aws_db_subnet_group.default')
            resource_type: resource type (always 'aws_db_subnet_group')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
        """
        logger.info("Mapping DB Subnet Group resource: '%s'", resource_name)

        # Validate input data
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

        # Core DB Subnet Group properties
        subnet_group_name = values.get("name")
        if subnet_group_name:
            metadata["aws_db_subnet_group_name"] = subnet_group_name

        # Description for the subnet group
        description = values.get("description")
        if description:
            metadata["aws_db_subnet_group_description"] = description

        # Subnet IDs (required) - these define the placement constraints
        subnet_ids = values.get("subnet_ids", [])
        if subnet_ids:
            metadata["aws_subnet_ids"] = subnet_ids
            metadata["aws_subnet_count"] = len(subnet_ids)

        # Extract subnet information to get availability zones
        subnet_info = self._extract_subnet_information(resource_data)
        if subnet_info:
            metadata["aws_subnet_details"] = subnet_info
            metadata["aws_availability_zones"] = [
                subnet["availability_zone"]
                for subnet in subnet_info
                if subnet.get("availability_zone")
            ]

        # Name prefix if used instead of explicit name
        name_prefix = values.get("name_prefix")
        if name_prefix:
            metadata["aws_name_prefix"] = name_prefix

        # Region information
        region = values.get("region")
        if region:
            metadata["aws_region"] = region

        # Tags for the subnet group
        tags = values.get("tags", {})
        if tags:
            metadata["aws_tags"] = tags

        # Tags_all (all tags including provider defaults)
        tags_all = values.get("tags_all", {})
        if tags_all and tags_all != tags:
            metadata["aws_tags_all"] = tags_all

        # Computed attributes from AWS
        arn = values.get("arn")
        if arn:
            metadata["aws_arn"] = arn

        db_subnet_group_id = values.get("id")
        if db_subnet_group_id:
            metadata["aws_db_subnet_group_id"] = db_subnet_group_id

        supported_network_types = values.get("supported_network_types", [])
        if supported_network_types:
            metadata["aws_supported_network_types"] = supported_network_types

        vpc_id = values.get("vpc_id")
        if vpc_id:
            metadata["aws_vpc_id"] = vpc_id

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

        # Find and add targets - database nodes that use this subnet group
        target_nodes = self._find_database_targets(subnet_group_name, clean_name)
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

        # Debug: mapped properties
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
            subnet_group_name,
            description,
            subnet_ids,
            region,
            vpc_id,
            tags,
            arn,
        )

    def _extract_subnet_information(
        self, resource_data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Extract detailed information about the subnets referenced by this group.

        Args:
            resource_data: Resource data from Terraform plan

        Returns:
            List of subnet information dictionaries with details like AZ
        """
        subnet_info: list[dict[str, Any]] = []

        # Access the full plan via the TerraformMapper instance
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
            logger.debug("Could not access parsed_data for subnet information")
            return subnet_info

        if not parsed_data:
            return subnet_info

        # Get the resource address to find its configuration
        resource_address = resource_data.get("address")
        if not resource_address:
            return subnet_info

        # Find configuration for this resource to get subnet references
        configuration = parsed_data.get("configuration", {})
        config_root_module = configuration.get("root_module", {})
        config_resources = config_root_module.get("resources", [])

        db_subnet_group_config = None
        for config_res in config_resources:
            if config_res.get("address") == resource_address:
                db_subnet_group_config = config_res
                break

        if not db_subnet_group_config:
            logger.debug("Configuration not found for %s", resource_address)
            return subnet_info

        # Extract subnet references from expressions
        expressions = db_subnet_group_config.get("expressions", {})
        subnet_ids_expr = expressions.get("subnet_ids", {})
        subnet_references = subnet_ids_expr.get("references", [])

        # Get planned values to find subnet resources
        planned_values = parsed_data.get("planned_values", {})
        root_module = planned_values.get("root_module", {})

        # Find subnet resources that match our references
        for resource in root_module.get("resources", []):
            if resource.get("type") == "aws_subnet":
                subnet_address = resource.get("address", "")
                subnet_values = resource.get("values", {})

                # Check if this subnet is referenced by our subnet group
                for subnet_ref in subnet_references:
                    if (
                        isinstance(subnet_ref, str)
                        and subnet_address
                        and (
                            subnet_address in subnet_ref
                            or subnet_ref.startswith(subnet_address)
                        )
                    ):
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
        self, subnet_group_name: str | None, clean_name: str
    ) -> list[str]:
        """Find database nodes that should be targeted by this placement policy.

        Args:
            subnet_group_name: Name of the DB subnet group
            clean_name: Clean resource name as fallback

        Returns:
            List of database node names that should be targeted
        """
        targets: list[str] = []

        # Access the current parsed data to find database instances
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
            logger.debug("Could not access parsed_data for target identification")
            return targets

        if not parsed_data:
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
