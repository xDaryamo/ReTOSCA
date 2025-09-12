import logging
from typing import TYPE_CHECKING, Any, TypedDict

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper
from src.plugins.provisioning.terraform.exceptions import (
    ResourceMappingError,
    TerraformDataError,
)

if TYPE_CHECKING:
    from src.models.v2_0.builder import PolicyBuilder, ServiceTemplateBuilder
    from src.plugins.provisioning.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class ElastiCacheSubnetGroupData(TypedDict, total=False):
    """Typed structure for ElastiCache subnet group data."""

    resource_name: str
    resource_type: str
    clean_name: str
    values: dict[str, Any]
    metadata_values: dict[str, Any]
    subnet_ids: list[str]
    has_subnet_references: bool
    provider_name: str | None


class AWSElastiCacheSubnetGroupMapper(SingleResourceMapper):
    """Map a Terraform 'aws_elasticache_subnet_group' to TOSCA policy.

    This mapper creates a Placement policy that governs the placement of
    ElastiCache nodes within specific subnets. The policy targets ElastiCache
    clusters and ensures they are placed within the appropriate subnet group
    for network connectivity and availability.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_elasticache_subnet_group'."""
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
        logger.info(f"Mapping ElastiCache Subnet Group resource: '{resource_name}'")

        # Early guard: check if resource has values
        if context:
            values = context.get_resolved_values(resource_data, "property")
        else:
            values = resource_data.get("values", {})

        if not values:
            logger.warning(
                "Resource '%s' has no 'values' section. Skipping.", resource_name
            )
            return

        try:
            # Prepare and validate all mapping data
            mapping_data = self._prepare_mapping_data(
                resource_name, resource_type, resource_data, context
            )

            # Create the TOSCA placement policy with metadata
            policy_builder = self._create_placement_policy(
                mapping_data, builder, context
            )

            # Add ElastiCache targets if available
            targets_added = self._add_elasticache_targets(
                policy_builder, mapping_data, context
            )

            # Finalize and log success
            self._finalize_and_log_success(policy_builder, mapping_data, targets_added)

        except TerraformDataError as e:
            # Handle validation errors gracefully by logging and skipping
            if "Missing required field" in str(e) and "subnet_ids" in str(e):
                logger.error(
                    "Resource '%s' missing required field 'subnet_ids' and no "
                    "subnet references found. Skipping.",
                    resource_name,
                )
                return
            else:
                # Re-raise other TerraformDataErrors
                raise
        except ResourceMappingError:
            raise
        except Exception as e:
            raise ResourceMappingError(
                "Unexpected error mapping ElastiCache subnet group",
                resource_name=resource_name,
                resource_type=resource_type,
                mapping_phase="policy_creation",
            ) from e

    def _prepare_mapping_data(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        context: "TerraformMappingContext | None",
    ) -> ElastiCacheSubnetGroupData:
        """Prepare and validate all data needed for mapping.
        Args:
            resource_name: Name of the Terraform resource
            resource_type: Type of the Terraform resource
            resource_data: Raw resource data from Terraform plan
            context: Optional mapping context for resolution

        Returns:
            Validated and structured mapping data
        Raises:
            TerraformDataError: If required data is missing or invalid
        """
        logger.debug(f"Raw resource_data: {resource_data}")

        # Get resolved values using cached context resolution
        values = self._get_resolved_values(resource_data, context, "property")
        metadata_values = self._get_resolved_values(resource_data, context, "metadata")

        if not values:
            raise TerraformDataError(
                "Resource has no 'values' section",
                resource_name=resource_name,
                missing_field="values",
            )

        # Analyze subnet configuration
        subnet_ids = values.get("subnet_ids", [])
        has_subnet_references = self._check_subnet_references(resource_data, context)

        # Validate subnet configuration
        if not subnet_ids and not has_subnet_references:
            raise TerraformDataError(
                "Missing required field 'subnet_ids' and no subnet references found",
                resource_name=resource_name,
                missing_field="subnet_ids",
            )

        # Extract clean name
        clean_name = (
            resource_name.split(".", 1)[1] if "." in resource_name else resource_name
        )

        return ElastiCacheSubnetGroupData(
            resource_name=resource_name,
            resource_type=resource_type,
            clean_name=clean_name,
            values=values,
            metadata_values=metadata_values,
            subnet_ids=subnet_ids,
            has_subnet_references=has_subnet_references,
            provider_name=resource_data.get("provider_name"),
        )

    def _get_resolved_values(
        self,
        resource_data: dict[str, Any],
        context: "TerraformMappingContext | None",
        value_type: str,
    ) -> dict[str, Any]:
        """Get resolved values from context or fallback to original values."""
        if context:
            values = context.get_resolved_values(resource_data, value_type)
            logger.debug(f"Resolved {value_type} values: {values}")
            return values
        else:
            values = resource_data.get("values", {})
            logger.debug(f"Original {value_type} values (no context): {values}")
            return values

    def _check_subnet_references(
        self, resource_data: dict[str, Any], context: "TerraformMappingContext | None"
    ) -> bool:
        """Check if resource has Terraform references to subnets."""
        if not context:
            return False

        terraform_refs = context.extract_terraform_references(resource_data)
        logger.debug(
            f"Found {len(terraform_refs)} terraform references: {terraform_refs}"
        )

        # Debug context structure
        if context.parsed_data:
            logger.debug(f"Context parsed_data keys: {context.parsed_data.keys()}")
            if "plan" in context.parsed_data:
                plan_config = context.parsed_data["plan"].get("configuration", {})
                logger.debug(f"Plan configuration keys: {plan_config.keys()}")

        return any(prop_name == "subnet_ids" for prop_name, _, _ in terraform_refs)

    def _create_placement_policy(
        self,
        mapping_data: ElastiCacheSubnetGroupData,
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> "PolicyBuilder":
        """Create TOSCA placement policy with comprehensive metadata."""
        policy_name = BaseResourceMapper.generate_tosca_node_name(
            mapping_data["resource_name"], mapping_data["resource_type"]
        )

        metadata = self._build_comprehensive_metadata(mapping_data, context)

        # Create the Placement policy
        policy_builder = builder.add_policy(policy_name, "Placement")
        policy_builder.with_metadata(metadata)

        return policy_builder

    def _build_comprehensive_metadata(
        self,
        mapping_data: ElastiCacheSubnetGroupData,
        context: "TerraformMappingContext | None" = None,
    ) -> dict[str, Any]:
        """Build comprehensive metadata dictionary."""
        values = mapping_data["values"]
        metadata_values = mapping_data["metadata_values"]

        # Base metadata
        metadata = {
            "original_resource_type": mapping_data["resource_type"],
            "original_resource_name": mapping_data["clean_name"],
            "aws_component_type": "ElastiCacheSubnetGroup",
            "description": (
                "AWS ElastiCache Subnet Group for cache placement within VPC subnets"
            ),
        }

        # Add provider information if available
        if mapping_data["provider_name"]:
            metadata["terraform_provider"] = mapping_data["provider_name"]

        # Core properties
        self._add_core_metadata(metadata, values, metadata_values)

        # Placement-specific metadata
        self._add_placement_metadata(metadata, mapping_data)

        # AWS computed attributes
        self._add_aws_attributes(metadata, metadata_values)

        # Add subnet details if context is available
        self._add_subnet_details(metadata, mapping_data, context)

        return metadata

    def _add_subnet_details(
        self,
        metadata: dict[str, Any],
        mapping_data: ElastiCacheSubnetGroupData,
        context: "TerraformMappingContext | None",
    ) -> None:
        """Add detailed subnet information to metadata if available."""
        if not context:
            return

        # Extract subnet details from parsed data if subnet references exist
        if mapping_data["has_subnet_references"]:
            parsed_data = context.parsed_data
            if parsed_data:
                subnet_details = []
                availability_zones = set()

                # Look for subnet resources in the parsed data
                planned_values = parsed_data.get("planned_values", {})
                root_module = planned_values.get("root_module", {})
                resources = root_module.get("resources", [])

                for resource in resources:
                    if resource.get("type") == "aws_subnet":
                        values = resource.get("values", {})
                        subnet_info = {
                            "address": resource.get("address", ""),
                            "cidr_block": values.get("cidr_block", ""),
                            "availability_zone": values.get("availability_zone", ""),
                            "map_public_ip_on_launch": values.get(
                                "map_public_ip_on_launch", False
                            ),
                        }
                        subnet_details.append(subnet_info)

                        if az := values.get("availability_zone"):
                            availability_zones.add(az)

                if subnet_details:
                    metadata["aws_subnet_details"] = subnet_details
                if availability_zones:
                    metadata["aws_availability_zones"] = sorted(availability_zones)

    def _add_core_metadata(
        self,
        metadata: dict[str, Any],
        values: dict[str, Any],
        metadata_values: dict[str, Any],
    ) -> None:
        """Add core ElastiCache subnet group metadata."""
        # Subnet group name and description
        if name := metadata_values.get("name"):
            metadata["aws_cache_subnet_group_name"] = name

        if description := metadata_values.get("description"):
            metadata["aws_cache_subnet_group_description"] = description

        # Subnet IDs
        if subnet_ids := metadata_values.get("subnet_ids", []):
            metadata["aws_subnet_ids"] = subnet_ids
            metadata["aws_subnet_count"] = len(subnet_ids)

        # Tags
        if tags := metadata_values.get("tags", {}):
            metadata["aws_tags"] = tags

        if tags_all := metadata_values.get("tags_all", {}):
            if tags_all != metadata.get("aws_tags", {}):
                metadata["aws_tags_all"] = tags_all

    def _add_placement_metadata(
        self, metadata: dict[str, Any], mapping_data: ElastiCacheSubnetGroupData
    ) -> None:
        """Add placement-specific metadata."""
        values = mapping_data["values"]
        subnet_ids = mapping_data["subnet_ids"]
        has_subnet_references = mapping_data["has_subnet_references"]

        if subnet_ids or has_subnet_references:
            metadata["placement_zone"] = "cache_subnet_group"
            metadata["subnet_group_name"] = (
                values.get("name") or mapping_data["clean_name"]
            )

            if subnet_ids:
                metadata["availability_zones_count"] = len(subnet_ids)
            else:
                metadata["availability_zones"] = "referenced"

    def _add_aws_attributes(
        self, metadata: dict[str, Any], metadata_values: dict[str, Any]
    ) -> None:
        """Add AWS computed attributes to metadata."""
        # Map AWS attributes efficiently
        aws_attrs = {
            "region": "aws_region",
            "arn": "aws_arn",
            "id": "aws_cache_subnet_group_id",
            "vpc_id": "aws_vpc_id",
        }

        for aws_key, metadata_key in aws_attrs.items():
            if value := metadata_values.get(aws_key):
                metadata[metadata_key] = value

    def _add_elasticache_targets(
        self,
        policy_builder: "PolicyBuilder",
        mapping_data: ElastiCacheSubnetGroupData,
        context: "TerraformMappingContext | None",
    ) -> bool:
        """Add ElastiCache targets to the placement policy."""
        if not context:
            return False

        subnet_group_name = mapping_data["metadata_values"].get("name") or mapping_data[
            "values"
        ].get("name")

        target_nodes = self._find_elasticache_targets(
            subnet_group_name, mapping_data["clean_name"], context
        )

        if target_nodes:
            policy_builder.with_targets(*target_nodes)
            logger.info(
                f"Policy will target {len(target_nodes)} ElastiCache nodes: "
                f"{target_nodes}"
            )
            return True

        return False

    def _finalize_and_log_success(
        self,
        policy_builder: "PolicyBuilder",
        mapping_data: ElastiCacheSubnetGroupData,
        targets_added: bool,
    ) -> None:
        """Finalize policy and log success information."""
        policy_builder.and_service()

        policy_name = BaseResourceMapper.generate_tosca_node_name(
            mapping_data["resource_name"], mapping_data["resource_type"]
        )

        subnet_ids = mapping_data["subnet_ids"]
        has_subnet_references = mapping_data["has_subnet_references"]
        clean_name = mapping_data["clean_name"]

        # Log policy target information
        if not targets_added:
            subnet_group_name = mapping_data["values"].get("name") or clean_name
            logger.info(
                f"Policy '{policy_name}' has no specific targets - it will govern "
                f"placement for any ElastiCache resources using "
                f"subnet group '{subnet_group_name}'"
            )

        # Log success with subnet count
        if subnet_ids:
            subnet_count_msg = f"with {len(subnet_ids)} subnets"
        elif has_subnet_references:
            subnet_count_msg = "with referenced subnets"
        else:
            subnet_count_msg = "with unknown subnet count"

        logger.info(
            f"Successfully created Placement policy '{policy_name}' for ElastiCache "
            f"Subnet Group {subnet_count_msg}"
        )

        # Debug mapped metadata
        self._log_debug_metadata(policy_name, mapping_data, targets_added)

    def _log_debug_metadata(
        self,
        policy_name: str,
        mapping_data: ElastiCacheSubnetGroupData,
        targets_added: bool,
    ) -> None:
        """Log detailed debug information about mapped metadata."""
        metadata_values = mapping_data["metadata_values"]

        logger.debug(
            f"Mapped ElastiCache Subnet Group metadata for '{policy_name}':\n"
            f"  - Name: {metadata_values.get('name')}\n"
            f"  - Description: {metadata_values.get('description')}\n"
            f"  - Subnet IDs: {metadata_values.get('subnet_ids', [])}\n"
            f"  - Region: {metadata_values.get('region')}\n"
            f"  - VPC ID: {metadata_values.get('vpc_id')}\n"
            f"  - Tags: {metadata_values.get('tags', {})}\n"
            f"  - ARN: {metadata_values.get('arn')}\n"
            f"  - Placement Zone: cache_subnet_group\n"
            f"  - Targets Added: {targets_added}"
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

        logger.debug(f"Extracted subnet information: {len(subnet_info)} subnets found")
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
        parsed_data = context.parsed_data
        if not parsed_data:
            logger.debug("Could not access parsed_data for target identification")
            return []

        # Get ElastiCache resources efficiently
        elasticache_resources = self._get_elasticache_resources(context)
        target_subnet_group = subnet_group_name or clean_name

        # Use list comprehension for better performance
        targets = [
            BaseResourceMapper.generate_tosca_node_name(
                f"{resource['address']}_dbms", resource["type"]
            )
            for resource in elasticache_resources
            if (
                resource.get("values", {}).get("subnet_group_name")
                == target_subnet_group
                and resource.get("address")
            )
        ]

        return targets

    def _get_elasticache_resources(
        self, context: "TerraformMappingContext"
    ) -> list[dict[str, Any]]:
        """Get all ElastiCache resources from context.

        Note: Removed caching to avoid potential memory leaks with method caching.
        """
        parsed_data = context.parsed_data
        if not parsed_data:
            return []

        # Look for ElastiCache resources in planned values
        planned_values = parsed_data.get("planned_values", {})
        if not planned_values and "plan" in parsed_data:
            planned_values = parsed_data["plan"].get("planned_values", {})

        root_module = planned_values.get("root_module", {})

        # Filter ElastiCache resources efficiently
        elasticache_types = {
            "aws_elasticache_cluster",
            "aws_elasticache_replication_group",
        }

        return [
            resource
            for resource in root_module.get("resources", [])
            if resource.get("type") in elasticache_types
        ]
