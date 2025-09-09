import logging
from typing import TYPE_CHECKING, Any, TypedDict

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext


class SubnetDetail(TypedDict):
    """Typed dictionary for subnet information."""

    subnet_address: str
    cidr_block: str | None
    availability_zone: str | None
    map_public_ip_on_launch: bool
    name: str | None


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
            context: Optional Terraform mapping context for enhanced resolution

        Raises:
            ValueError: If resource_name is empty or resource_type is invalid
            TypeError: If resource_data is not a dictionary
        """
        self._validate_inputs(resource_name, resource_type, resource_data)
        logger.info("Mapping DB Subnet Group resource: '%s'", resource_name)

        try:
            values = self._get_property_values(resource_data, context)
            if not values:
                logger.warning(
                    "Resource '%s' has no 'values' section. Skipping.", resource_name
                )
                return

            policy_name = self._generate_policy_name(resource_name, resource_type)
            clean_name = self._extract_clean_name(resource_name)
            metadata = self._build_metadata(
                resource_data, context, clean_name, resource_type
            )

            policy_builder = self._create_placement_policy(
                builder, policy_name, values, clean_name
            )
            policy_builder.with_metadata(metadata)

            if context:
                self._add_policy_targets(
                    policy_builder, policy_name, values, clean_name, context
                )

            policy_builder.and_service()
            self._log_mapping_success(policy_name, values, metadata)

        except Exception as e:
            logger.error(
                "Failed to map DB Subnet Group resource '%s': %s", resource_name, str(e)
            )
            raise

    def _validate_inputs(
        self, resource_name: str, resource_type: str, resource_data: dict[str, Any]
    ) -> None:
        """Validate input parameters.

        Args:
            resource_name: Name of the resource
            resource_type: Type of the resource
            resource_data: Resource data dictionary

        Raises:
            ValueError: If resource_name is empty or resource_type is invalid
            TypeError: If resource_data is not a dictionary
        """
        if not resource_name or not resource_name.strip():
            raise ValueError("resource_name cannot be empty")

        if resource_type != "aws_db_subnet_group":
            raise ValueError(f"Invalid resource_type: {resource_type}")

        if not isinstance(resource_data, dict):
            raise TypeError("resource_data must be a dictionary")

    def _get_property_values(
        self, resource_data: dict[str, Any], context: "TerraformMappingContext | None"
    ) -> dict[str, Any]:
        """Get resolved property values from resource data.

        Args:
            resource_data: Resource data from Terraform plan
            context: Optional Terraform mapping context

        Returns:
            Dictionary of resolved property values
        """
        if context:
            return context.get_resolved_values(resource_data, "property")
        return resource_data.get("values", {})

    def _get_metadata_values(
        self, resource_data: dict[str, Any], context: "TerraformMappingContext | None"
    ) -> dict[str, Any]:
        """Get resolved metadata values from resource data.

        Args:
            resource_data: Resource data from Terraform plan
            context: Optional Terraform mapping context

        Returns:
            Dictionary of resolved metadata values
        """
        if context:
            return context.get_resolved_values(resource_data, "metadata")
        return resource_data.get("values", {})

    def _generate_policy_name(self, resource_name: str, resource_type: str) -> str:
        """Generate a unique TOSCA policy name.

        Args:
            resource_name: Name of the resource
            resource_type: Type of the resource

        Returns:
            Generated TOSCA policy name
        """
        return BaseResourceMapper.generate_tosca_node_name(resource_name, resource_type)

    def _extract_clean_name(self, resource_name: str) -> str:
        """Extract clean name without type prefix.

        Args:
            resource_name: Full resource name

        Returns:
            Clean resource name without prefix
        """
        _, _, clean_name = resource_name.partition(".")
        return clean_name or resource_name

    def _build_metadata(
        self,
        resource_data: dict[str, Any],
        context: "TerraformMappingContext | None",
        clean_name: str,
        resource_type: str,
    ) -> dict[str, Any]:
        """Build comprehensive metadata dictionary.

        Args:
            resource_data: Resource data from Terraform plan
            context: Optional Terraform mapping context
            clean_name: Clean resource name
            resource_type: Type of the resource

        Returns:
            Comprehensive metadata dictionary
        """
        metadata_values = self._get_metadata_values(resource_data, context)
        metadata = self._get_base_metadata(resource_data, clean_name, resource_type)
        metadata.update(self._get_aws_metadata(metadata_values))

        if context:
            metadata.update(self._get_context_metadata(resource_data, context))

        return metadata

    def _get_base_metadata(
        self, resource_data: dict[str, Any], clean_name: str, resource_type: str
    ) -> dict[str, Any]:
        """Get base metadata information.

        Args:
            resource_data: Resource data from Terraform plan
            clean_name: Clean resource name
            resource_type: Type of the resource

        Returns:
            Base metadata dictionary
        """
        metadata = {
            "original_resource_type": resource_type,
            "original_resource_name": clean_name,
            "aws_component_type": "DBSubnetGroup",
            "description": (
                "AWS RDS DB Subnet Group for database placement within VPC subnets"
            ),
        }

        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["terraform_provider"] = provider_name

        return metadata

    def _get_aws_metadata(self, metadata_values: dict[str, Any]) -> dict[str, Any]:
        """Get AWS-specific metadata using optimized pattern.

        Args:
            metadata_values: Dictionary of metadata values

        Returns:
            AWS-specific metadata dictionary
        """
        metadata_mappings = {
            "aws_db_subnet_group_name": "name",
            "aws_db_subnet_group_description": "description",
            "aws_name_prefix": "name_prefix",
            "aws_region": "region",
            "aws_arn": "arn",
            "aws_db_subnet_group_id": "id",
            "aws_vpc_id": "vpc_id",
        }

        metadata = {
            target_key: metadata_values[source_key]
            for target_key, source_key in metadata_mappings.items()
            if source_key in metadata_values and metadata_values[source_key]
        }

        # Handle special cases
        subnet_ids = metadata_values.get("subnet_ids", [])
        if subnet_ids:
            metadata["aws_subnet_ids"] = subnet_ids
            metadata["aws_subnet_count"] = len(subnet_ids)

        tags = metadata_values.get("tags", {})
        if tags:
            metadata["aws_tags"] = tags

        tags_all = metadata_values.get("tags_all", {})
        if tags_all and tags_all != tags:
            metadata["aws_tags_all"] = tags_all

        supported_network_types = metadata_values.get("supported_network_types", [])
        if supported_network_types:
            metadata["aws_supported_network_types"] = supported_network_types

        return metadata

    def _get_context_metadata(
        self, resource_data: dict[str, Any], context: "TerraformMappingContext"
    ) -> dict[str, Any]:
        """Get context-specific metadata including subnet information.

        Args:
            resource_data: Resource data from Terraform plan
            context: Terraform mapping context

        Returns:
            Context-specific metadata dictionary
        """
        metadata = {}

        try:
            subnet_info = self._extract_subnet_information(resource_data, context)
            if subnet_info:
                metadata["aws_subnet_details"] = subnet_info
                # Extract availability zones from subnet information
                az_strings = []
                for subnet_data in subnet_info:
                    zone = subnet_data.get("availability_zone")
                    if zone is not None:
                        az_strings.append(str(zone))
                if az_strings:
                    metadata["aws_availability_zones"] = az_strings  # type: ignore[assignment]
        except Exception as e:
            logger.warning("Failed to extract subnet information: %s", str(e))

        return metadata

    def _create_placement_policy(
        self,
        builder: "ServiceTemplateBuilder",
        policy_name: str,
        values: dict[str, Any],
        clean_name: str,
    ):
        """Create the Placement policy with properties.

        Args:
            builder: ServiceTemplateBuilder instance
            policy_name: Name of the policy
            values: Property values dictionary
            clean_name: Clean resource name

        Returns:
            Policy builder instance
        """
        policy_builder = builder.add_policy(policy_name, "Placement")

        subnet_ids = values.get("subnet_ids", [])
        if subnet_ids:
            subnet_group_name = values.get("name")
            policy_builder.with_property("placement_zone", "subnet_group")
            policy_builder.with_property(
                "subnet_group_name", subnet_group_name or clean_name
            )
            policy_builder.with_property("availability_zones", len(subnet_ids))

        return policy_builder

    def _add_policy_targets(
        self,
        policy_builder,
        policy_name: str,
        values: dict[str, Any],
        clean_name: str,
        context: "TerraformMappingContext",
    ) -> None:
        """Add targets to the policy if available.

        Args:
            policy_builder: Policy builder instance
            policy_name: Name of the policy
            values: Property values dictionary
            clean_name: Clean resource name
            context: Terraform mapping context
        """
        subnet_group_name = values.get("name")
        target_nodes = self._find_database_targets(
            subnet_group_name, clean_name, context
        )
        if target_nodes:
            policy_builder.with_targets(*target_nodes)
            logger.info(
                "Policy '%s' will target %d database nodes: %s",
                policy_name,
                len(target_nodes),
                target_nodes,
            )

    def _log_mapping_success(
        self, policy_name: str, values: dict[str, Any], metadata: dict[str, Any]
    ) -> None:
        """Log successful mapping with details.

        Args:
            policy_name: Name of the created policy
            values: Property values dictionary
            metadata: Metadata dictionary
        """
        subnet_ids = values.get("subnet_ids", [])
        logger.info(
            "Successfully created Placement policy '%s' for DB Subnet Group "
            "with %d subnets",
            policy_name,
            len(subnet_ids),
        )

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
            metadata.get("aws_db_subnet_group_name"),
            metadata.get("aws_db_subnet_group_description"),
            metadata.get("aws_subnet_ids"),
            metadata.get("aws_region"),
            metadata.get("aws_vpc_id"),
            metadata.get("aws_tags"),
            metadata.get("aws_arn"),
        )

    def _extract_subnet_information(
        self, resource_data: dict[str, Any], context: "TerraformMappingContext"
    ) -> list[SubnetDetail]:
        """Extract detailed information about the subnets referenced by this group.

        Args:
            resource_data: Resource data from Terraform plan
            context: TerraformMappingContext containing parsed data

        Returns:
            List of subnet information with details like availability zone

        Raises:
            Exception: If unable to parse subnet information from context
        """
        subnet_info: list[SubnetDetail] = []

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
                        subnet_detail: SubnetDetail = {
                            "subnet_address": subnet_address,
                            "cidr_block": subnet_values.get("cidr_block"),
                            "availability_zone": subnet_values.get("availability_zone"),
                            "map_public_ip_on_launch": subnet_values.get(
                                "map_public_ip_on_launch", False
                            ),
                            "name": subnet_values.get("tags", {}).get("Name"),
                        }
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

        Searches through parsed Terraform data to identify AWS RDS instances
        that reference this subnet group, returning their TOSCA node names.

        Args:
            subnet_group_name: Name of the DB subnet group
            clean_name: Clean resource name as fallback
            context: TerraformMappingContext containing parsed data

        Returns:
            List of TOSCA node names for database instances using this subnet group.
            Names follow the pattern: "aws_db_instance_{resource_name}_dbms"

        Raises:
            Exception: If context contains invalid parsed data
        """
        targets: list[str] = []

        try:
            # Get parsed data from context to find database instances
            parsed_data = context.parsed_data
            if not parsed_data:
                logger.debug("No parsed_data available for target identification")
                return targets
        except (AttributeError, TypeError) as e:
            logger.warning("Failed to access parsed_data from context: %s", str(e))
            return targets

        try:
            # Look for database instances that reference this subnet group
            # Try different paths where resources might be stored
            planned_values = parsed_data.get("planned_values", {})
            if not planned_values and "plan" in parsed_data:
                planned_values = parsed_data["plan"].get("planned_values", {})

            root_module = planned_values.get("root_module", {})
        except (KeyError, TypeError) as e:
            logger.warning(
                "Failed to access planned_values from parsed_data: %s", str(e)
            )
            return targets

        target_subnet_group = subnet_group_name or clean_name
        logger.debug(
            "Looking for database targets using subnet group: %s", target_subnet_group
        )

        try:
            resources_found = 0
            for resource in root_module.get("resources", []):
                if resource.get("type") == "aws_db_instance":
                    resources_found += 1
                    db_values = resource.get("values", {})
                    db_subnet_group = db_values.get("db_subnet_group_name")
                    db_address = resource.get("address", "")

                    logger.debug(
                        "Found DB instance '%s' with db_subnet_group_name: %s",
                        db_address,
                        db_subnet_group,
                    )

                    # Check if this database uses our subnet group
                    if db_subnet_group == target_subnet_group:
                        logger.debug(
                            "MATCH! DB instance '%s' uses target subnet group '%s'",
                            db_address,
                            target_subnet_group,
                        )
                        if db_address:
                            # Generate the TOSCA node name for DBMS only
                            dbms_node_name = (
                                BaseResourceMapper.generate_tosca_node_name(
                                    db_address + "_dbms", "aws_db_instance"
                                )
                            )

                            targets.append(dbms_node_name)

                            logger.debug(
                                "Found database instance '%s' using subnet group "
                                "'%s' - added DBMS target: %s",
                                db_address,
                                target_subnet_group,
                                dbms_node_name,
                            )
                    else:
                        logger.debug(
                            "No match: '%s' != '%s'",
                            db_subnet_group,
                            target_subnet_group,
                        )
        except (KeyError, TypeError, AttributeError) as e:
            logger.warning("Error processing database resources: %s", str(e))

            logger.debug(
                "Total DB instances found: %d, targets found: %d",
                resources_found,
                len(targets),
            )
        except NameError:
            # resources_found was not defined due to earlier exception
            logger.debug("Targets found: %d", len(targets))

        return targets
