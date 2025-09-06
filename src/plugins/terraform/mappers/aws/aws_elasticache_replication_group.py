import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSElastiCacheReplicationGroupMapper(SingleResourceMapper):
    """Map Terraform 'aws_elasticache_replication_group' to TOSCA Database node.

    This mapper creates a Database node representing an AWS ElastiCache Redis
    replication group. The replication group provides a clustered Redis cache with
    high availability, automatic failover, and read scaling capabilities.

    The Database node type is appropriate because:
    - ElastiCache serves as a caching database service
    - It provides a database endpoint for applications
    - It has similar properties to other databases (port, name, authentication)
    - Applications connect to it like any other database service
    """

    def __init__(self):
        """Initialize the mapper with ElastiCache engine type mapping."""
        super().__init__()
        self._logger = logging.getLogger(self.__class__.__name__)

        # Default ports for different ElastiCache engines
        self._default_ports = {
            "redis": 6379,
            "memcached": 11211,
        }

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_elasticache_replication_group'."""
        return resource_type == "aws_elasticache_replication_group"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Map aws_elasticache_replication_group resource to TOSCA Database node.

        Args:
            resource_name: resource name (e.g.
                'aws_elasticache_replication_group.example')
            resource_type: resource type (always 'aws_elasticache_replication_group')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for dependency resolution and
                variable handling
        """
        logger.info(
            "Mapping ElastiCache Replication Group resource: '%s'", resource_name
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

        # Extract the clean name for metadata (without the type prefix)
        if "." in resource_name:
            _, clean_name = resource_name.split(".", 1)
        else:
            clean_name = resource_name

        # Generate unique TOSCA node name
        node_name = BaseResourceMapper.generate_tosca_node_name(
            resource_name, resource_type
        )

        # Create the Database node
        cache_node = builder.add_node(name=node_name, node_type="Database")

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
        metadata["aws_component_type"] = "ElastiCacheReplicationGroup"
        metadata["description"] = (
            "AWS ElastiCache Redis replication group providing clustered "
            "caching with high availability and read scaling"
        )

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # Core ElastiCache properties - use metadata values for concrete resolution

        # Replication group ID (required)
        replication_group_id = values.get("replication_group_id")
        metadata_replication_group_id = metadata_values.get("replication_group_id")
        if metadata_replication_group_id:
            metadata["aws_replication_group_id"] = metadata_replication_group_id

        # Use replication group ID as the database name for TOSCA
        if replication_group_id:
            cache_node.with_property("name", replication_group_id)
        elif metadata_replication_group_id:
            cache_node.with_property("name", metadata_replication_group_id)
        else:
            # Fallback to clean name if replication_group_id is not available
            cache_node.with_property("name", clean_name)

        # Description
        metadata_description = metadata_values.get("description")
        if metadata_description:
            metadata["aws_description"] = metadata_description

        # Engine (should be 'redis' for replication groups)
        metadata_engine = metadata_values.get("engine")
        if metadata_engine:
            metadata["aws_engine"] = metadata_engine
        else:
            # Default to redis for replication groups
            metadata["aws_engine"] = "redis"

        # Engine version
        metadata_engine_version = metadata_values.get("engine_version")
        if metadata_engine_version:
            metadata["aws_engine_version"] = metadata_engine_version

        # Node type (instance class)
        metadata_node_type = metadata_values.get("node_type")
        if metadata_node_type:
            metadata["aws_node_type"] = metadata_node_type

        # Port configuration
        port = values.get("port")
        metadata_port = metadata_values.get("port")
        if port:
            cache_node.with_property("port", port)
        elif metadata_port:
            cache_node.with_property("port", metadata_port)
        else:
            # Use default Redis port
            default_port = self._default_ports.get("redis", 6379)
            cache_node.with_property("port", default_port)
            metadata["aws_default_port"] = default_port

        # Cluster configuration
        metadata_num_cache_clusters = metadata_values.get("num_cache_clusters")
        if metadata_num_cache_clusters:
            metadata["aws_num_cache_clusters"] = metadata_num_cache_clusters

        metadata_num_node_groups = metadata_values.get("num_node_groups")
        if metadata_num_node_groups:
            metadata["aws_num_node_groups"] = metadata_num_node_groups

        metadata_replicas_per_node_group = metadata_values.get(
            "replicas_per_node_group"
        )
        if metadata_replicas_per_node_group:
            metadata["aws_replicas_per_node_group"] = metadata_replicas_per_node_group

        # High availability configuration
        metadata_automatic_failover_enabled = metadata_values.get(
            "automatic_failover_enabled"
        )
        if metadata_automatic_failover_enabled is not None:
            metadata["aws_automatic_failover_enabled"] = (
                metadata_automatic_failover_enabled
            )

        metadata_multi_az_enabled = metadata_values.get("multi_az_enabled")
        if metadata_multi_az_enabled is not None:
            metadata["aws_multi_az_enabled"] = metadata_multi_az_enabled

        # Availability zones
        metadata_preferred_cache_cluster_azs = metadata_values.get(
            "preferred_cache_cluster_azs", []
        )
        if metadata_preferred_cache_cluster_azs:
            metadata["aws_preferred_cache_cluster_azs"] = (
                metadata_preferred_cache_cluster_azs
            )

        # Parameter group
        metadata_parameter_group_name = metadata_values.get("parameter_group_name")
        if metadata_parameter_group_name:
            metadata["aws_parameter_group_name"] = metadata_parameter_group_name

        # Subnet group
        metadata_subnet_group_name = metadata_values.get("subnet_group_name")
        if metadata_subnet_group_name:
            metadata["aws_subnet_group_name"] = metadata_subnet_group_name

        # Security groups
        metadata_security_group_ids = metadata_values.get("security_group_ids", [])
        if metadata_security_group_ids:
            metadata["aws_security_group_ids"] = metadata_security_group_ids

        metadata_security_group_names = metadata_values.get("security_group_names", [])
        if metadata_security_group_names:
            metadata["aws_security_group_names"] = metadata_security_group_names

        # Authentication
        metadata_auth_token = metadata_values.get("auth_token")
        if metadata_auth_token:
            # Don't store the actual token in metadata for security
            metadata["aws_auth_token_enabled"] = True
            # Set as TOSCA property for applications to use
            cache_node.with_property("password", metadata_auth_token)

        metadata_user_group_ids = metadata_values.get("user_group_ids", [])
        if metadata_user_group_ids:
            metadata["aws_user_group_ids"] = metadata_user_group_ids

        # Encryption
        metadata_at_rest_encryption_enabled = metadata_values.get(
            "at_rest_encryption_enabled"
        )
        if metadata_at_rest_encryption_enabled is not None:
            metadata["aws_at_rest_encryption_enabled"] = (
                metadata_at_rest_encryption_enabled
            )

        metadata_transit_encryption_enabled = metadata_values.get(
            "transit_encryption_enabled"
        )
        if metadata_transit_encryption_enabled is not None:
            metadata["aws_transit_encryption_enabled"] = (
                metadata_transit_encryption_enabled
            )

        metadata_kms_key_id = metadata_values.get("kms_key_id")
        if metadata_kms_key_id:
            metadata["aws_kms_key_id"] = metadata_kms_key_id

        # Backup configuration
        metadata_snapshot_retention_limit = metadata_values.get(
            "snapshot_retention_limit"
        )
        if metadata_snapshot_retention_limit is not None:
            metadata["aws_snapshot_retention_limit"] = metadata_snapshot_retention_limit

        metadata_snapshot_window = metadata_values.get("snapshot_window")
        if metadata_snapshot_window:
            metadata["aws_snapshot_window"] = metadata_snapshot_window

        metadata_final_snapshot_identifier = metadata_values.get(
            "final_snapshot_identifier"
        )
        if metadata_final_snapshot_identifier:
            metadata["aws_final_snapshot_identifier"] = (
                metadata_final_snapshot_identifier
            )

        # Maintenance
        metadata_maintenance_window = metadata_values.get("maintenance_window")
        if metadata_maintenance_window:
            metadata["aws_maintenance_window"] = metadata_maintenance_window

        metadata_apply_immediately = metadata_values.get("apply_immediately")
        if metadata_apply_immediately is not None:
            metadata["aws_apply_immediately"] = metadata_apply_immediately

        # Auto minor version upgrade
        metadata_auto_minor_version_upgrade = metadata_values.get(
            "auto_minor_version_upgrade"
        )
        if metadata_auto_minor_version_upgrade is not None:
            metadata["aws_auto_minor_version_upgrade"] = (
                metadata_auto_minor_version_upgrade
            )

        # Notification
        metadata_notification_topic_arn = metadata_values.get("notification_topic_arn")
        if metadata_notification_topic_arn:
            metadata["aws_notification_topic_arn"] = metadata_notification_topic_arn

        # Global replication group
        metadata_global_replication_group_id = metadata_values.get(
            "global_replication_group_id"
        )
        if metadata_global_replication_group_id:
            metadata["aws_global_replication_group_id"] = (
                metadata_global_replication_group_id
            )

        # Data tiering
        metadata_data_tiering_enabled = metadata_values.get("data_tiering_enabled")
        if metadata_data_tiering_enabled is not None:
            metadata["aws_data_tiering_enabled"] = metadata_data_tiering_enabled

        # IP discovery
        metadata_ip_discovery = metadata_values.get("ip_discovery")
        if metadata_ip_discovery:
            metadata["aws_ip_discovery"] = metadata_ip_discovery

        metadata_network_type = metadata_values.get("network_type")
        if metadata_network_type:
            metadata["aws_network_type"] = metadata_network_type

        # Computed attributes
        metadata_arn = metadata_values.get("arn")
        if metadata_arn:
            metadata["aws_arn"] = metadata_arn

        metadata_engine_version_actual = metadata_values.get("engine_version_actual")
        if metadata_engine_version_actual:
            metadata["aws_engine_version_actual"] = metadata_engine_version_actual

        metadata_cluster_enabled = metadata_values.get("cluster_enabled")
        if metadata_cluster_enabled is not None:
            metadata["aws_cluster_enabled"] = metadata_cluster_enabled

        metadata_configuration_endpoint_address = metadata_values.get(
            "configuration_endpoint_address"
        )
        if metadata_configuration_endpoint_address:
            metadata["aws_configuration_endpoint_address"] = (
                metadata_configuration_endpoint_address
            )

        metadata_primary_endpoint_address = metadata_values.get(
            "primary_endpoint_address"
        )
        if metadata_primary_endpoint_address:
            metadata["aws_primary_endpoint_address"] = metadata_primary_endpoint_address

        metadata_reader_endpoint_address = metadata_values.get(
            "reader_endpoint_address"
        )
        if metadata_reader_endpoint_address:
            metadata["aws_reader_endpoint_address"] = metadata_reader_endpoint_address

        # Member clusters
        metadata_member_clusters = metadata_values.get("member_clusters", [])
        if metadata_member_clusters:
            metadata["aws_member_clusters"] = metadata_member_clusters

        # Tags
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        # Tags_all (all tags including provider defaults)
        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

        # Attach metadata to the node
        cache_node.with_metadata(metadata)

        # Add database endpoint capability
        cache_node.add_capability("database_endpoint").and_node()

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

                if "." in target_ref:
                    # target_ref is like "aws_elasticache_subnet_group.main"
                    target_resource_type = target_ref.split(".", 1)[0]
                    target_node_name = BaseResourceMapper.generate_tosca_node_name(
                        target_ref, target_resource_type
                    )

                    # Add requirement with the property name as the requirement name
                    requirement_name = (
                        prop_name if prop_name not in ["dependency"] else "dependency"
                    )

                    (
                        cache_node.add_requirement(requirement_name)
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

        logger.debug(
            "ElastiCache Replication Group node '%s' created successfully.", node_name
        )

        # Debug: log mapped properties
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Mapped properties for '{node_name}':")
            logger.debug(f"  - Replication Group ID: {metadata_replication_group_id}")
            logger.debug(f"  - Engine: {metadata_engine}")
            logger.debug(f"  - Engine Version: {metadata_engine_version}")
            logger.debug(f"  - Node Type: {metadata_node_type}")
            default_port = self._default_ports.get("redis", 6379)
            logger.debug(f"  - Port: {metadata_port or default_port}")
            logger.debug(f"  - Number of Cache Clusters: {metadata_num_cache_clusters}")
            logger.debug(
                f"  - Automatic Failover: {metadata_automatic_failover_enabled}"
            )
            logger.debug(f"  - Multi-AZ: {metadata_multi_az_enabled}")
            logger.debug(f"  - Auth Token Enabled: {metadata_auth_token is not None}")
            logger.debug(
                f"  - At-Rest Encryption: {metadata_at_rest_encryption_enabled}"
            )
            logger.debug(
                f"  - Transit Encryption: {metadata_transit_encryption_enabled}"
            )
