import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.provisioning.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSElastiCacheClusterMapper(SingleResourceMapper):
    """Map a Terraform 'aws_elasticache_cluster' resource to TOSCA DBMS and Database.

    This mapper creates two interconnected nodes for ElastiCache clusters:
    1. DBMS node - represents the cache cluster management system
    2. Database node - represents the logical cache database within the cluster
    """

    # Class-level constants for engine configurations (Performance improvement)
    _ENGINE_TYPE_MAPPING: dict[str, str] = {
        "redis": "Redis",
        "memcached": "Memcached",
    }

    _ENGINE_DEFAULT_PORTS: dict[str, int] = {
        "redis": 6379,
        "memcached": 11211,
    }

    _ENGINE_VERSION_DEFAULTS: dict[str, str] = {
        "redis": "7.0",
        "memcached": "1.6.17",
    }

    def __init__(self):
        """Initialize the mapper with engine-specific configurations."""
        super().__init__()

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_elasticache_cluster'."""
        return resource_type == "aws_elasticache_cluster"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Translate an aws_elasticache_cluster into TOSCA DBMS and Database nodes.

        Args:
            resource_name: resource name (e.g. 'aws_elasticache_cluster.redis')
            resource_type: resource type (always 'aws_elasticache_cluster')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for variable resolution
        """
        logger.info(f"Mapping ElastiCache Cluster resource: '{resource_name}'")

        # Get resolved values using the context for properties and metadata
        if context:
            values = context.get_resolved_values(resource_data, "property")
            metadata_values = context.get_resolved_values(resource_data, "metadata")
        else:
            # Fallback to original values if no context available
            values = resource_data.get("values", {})
            metadata_values = resource_data.get("values", {})

        if not values:
            logger.warning(
                f"Resource '{resource_name}' has no 'values' section. Skipping."
            )
            return

        # Extract the clean name for metadata (without the type prefix)
        if "." in resource_name:
            _, clean_name = resource_name.split(".", 1)
        else:
            clean_name = resource_name

        # Generate unique TOSCA node names
        base_node_name = BaseResourceMapper.generate_tosca_node_name(
            resource_name, resource_type
        )
        dbms_node_name = f"{base_node_name}_dbms"
        database_node_name = f"{base_node_name}_database"

        # Create the DBMS node (for cache cluster management)
        self._create_dbms_node(
            builder,
            dbms_node_name,
            clean_name,
            resource_type,
            resource_data,
            values,
            metadata_values,
        )

        # Create the Database node (for logical cache database within cluster)
        database_node = self._create_database_node(
            builder,
            database_node_name,
            clean_name,
            resource_type,
            resource_data,
            values,
            metadata_values,
        )

        # Create the relationship between Database and DBMS
        database_node.add_requirement("host").to_node(dbms_node_name).with_relationship(
            "HostedOn"
        ).and_node()

        # Add dependencies using injected context
        if context:
            terraform_refs = context.extract_terraform_references(resource_data)
            logger.debug(
                f"Found {len(terraform_refs)} terraform references for {resource_name}"
            )

            for prop_name, target_ref, relationship_type in terraform_refs:
                logger.debug(
                    f"Processing reference: {prop_name} -> {target_ref} "
                    f"({relationship_type})"
                )

                if "." in target_ref:
                    # target_ref like "aws_elasticache_subnet_group.cache_subnet_group"
                    target_resource_type = target_ref.split(".", 1)[0]
                    target_node_name = BaseResourceMapper.generate_tosca_node_name(
                        target_ref, target_resource_type
                    )

                    # Add requirement with the property name as the requirement name
                    requirement_name = (
                        prop_name if prop_name not in ["dependency"] else "dependency"
                    )

                    # For ElastiCache clusters, both DBMS and Database nodes might need
                    # dependencies. Apply to DBMS node for infra-level dependencies
                    dbms_node = builder.get_node(dbms_node_name)
                    if dbms_node:
                        (
                            dbms_node.add_requirement(requirement_name)
                            .to_node(target_node_name)
                            .with_relationship(relationship_type)
                            .and_node()
                        )

                        logger.info(
                            f"Added {requirement_name} requirement '{target_node_name}'"
                            f" to DBMS '{dbms_node_name}' with rel {relationship_type}"
                        )
        else:
            logger.warning(
                f"No context provided to detect dependencies for resource "
                f"'{resource_name}'"
            )

        logger.debug(
            f"ElastiCache Cluster nodes '{dbms_node_name}' and "
            f"'{database_node_name}' created successfully."
        )

        # Debug: log mapped properties
        logger.debug(
            f"DBMS node properties - Engine: {metadata_values.get('engine')}, "
            f"Version: {metadata_values.get('engine_version')}"
        )
        logger.debug(
            f"Database node properties - ID: {metadata_values.get('cluster_id')}, "
            f"Port: {metadata_values.get('port')}"
        )

    def _resolve_port_with_default(
        self, port: Any, metadata_values: dict[str, Any]
    ) -> int:
        """Resolve port with engine-specific default fallback and validation."""
        # If port is provided, validate and use it
        if port is not None:
            if isinstance(port, int) and 1 <= port <= 65535:
                return port
            else:
                logger.warning(f"Invalid port number: {port}. Using engine default.")

        # Use engine-specific default port
        metadata_engine = metadata_values.get("engine")
        if metadata_engine and metadata_engine in self._ENGINE_DEFAULT_PORTS:
            return self._ENGINE_DEFAULT_PORTS[metadata_engine]

        # Final fallback to Redis default
        return 6379

    def _create_dbms_node(
        self,
        builder: "ServiceTemplateBuilder",
        node_name: str,
        clean_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        values: dict[str, Any],
        metadata_values: dict[str, Any],
    ):
        """Create and configure the DBMS node for ElastiCache cluster."""
        dbms_node = builder.add_node(name=node_name, node_type="DBMS")

        # Build metadata
        metadata: dict[str, Any] = {
            "original_resource_type": resource_type,
            "original_resource_name": clean_name,
            "aws_component_type": "ElastiCacheCluster",
            "description": "AWS ElastiCache cluster providing managed caching",
        }

        # Provider information
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # Engine information - use metadata values for concrete resolution
        metadata_engine = metadata_values.get("engine")
        if metadata_engine:
            # Map to standardized engine type
            standardized_engine = self._ENGINE_TYPE_MAPPING.get(
                metadata_engine, metadata_engine
            )
            metadata["aws_engine"] = metadata_engine
            metadata["engine_type"] = standardized_engine

        # Engine version
        metadata_engine_version = metadata_values.get("engine_version")
        if metadata_engine_version:
            metadata["aws_engine_version"] = metadata_engine_version

        # Cluster identifier
        metadata_cluster_id = metadata_values.get("cluster_id")
        if metadata_cluster_id:
            metadata["aws_cluster_id"] = metadata_cluster_id

        # Node configuration
        metadata_node_type = metadata_values.get("node_type")
        if metadata_node_type:
            metadata["aws_node_type"] = metadata_node_type

        metadata_num_cache_nodes = metadata_values.get("num_cache_nodes")
        if metadata_num_cache_nodes is not None:
            metadata["aws_num_cache_nodes"] = metadata_num_cache_nodes

        # Port (set as DBMS property)
        port = self._resolve_port_with_default(values.get("port"), metadata_values)
        dbms_node.with_property("port", port)
        if port != values.get("port"):
            metadata["aws_default_port"] = port

        # Parameter group
        metadata_parameter_group_name = metadata_values.get("parameter_group_name")
        if metadata_parameter_group_name:
            metadata["aws_parameter_group_name"] = metadata_parameter_group_name

        # Networking
        metadata_subnet_group_name = metadata_values.get("subnet_group_name")
        if metadata_subnet_group_name:
            metadata["aws_subnet_group_name"] = metadata_subnet_group_name

        metadata_security_group_ids = metadata_values.get("security_group_ids", [])
        if metadata_security_group_ids:
            metadata["aws_security_group_ids"] = metadata_security_group_ids

        # Availability zones
        metadata_availability_zones = metadata_values.get(
            "preferred_availability_zones", []
        )
        if metadata_availability_zones:
            metadata["aws_preferred_availability_zones"] = metadata_availability_zones

        # Maintenance window
        metadata_maintenance_window = metadata_values.get("maintenance_window")
        if metadata_maintenance_window:
            metadata["aws_maintenance_window"] = metadata_maintenance_window

        # Snapshots
        metadata_snapshot_retention_limit = metadata_values.get(
            "snapshot_retention_limit"
        )
        if metadata_snapshot_retention_limit is not None:
            metadata["aws_snapshot_retention_limit"] = metadata_snapshot_retention_limit

        metadata_snapshot_window = metadata_values.get("snapshot_window")
        if metadata_snapshot_window:
            metadata["aws_snapshot_window"] = metadata_snapshot_window

        # Auto upgrade
        metadata_auto_minor_version_upgrade = metadata_values.get(
            "auto_minor_version_upgrade"
        )
        if metadata_auto_minor_version_upgrade is not None:
            metadata["aws_auto_minor_version_upgrade"] = (
                metadata_auto_minor_version_upgrade
            )

        # Tags
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        # Attach metadata to the node
        dbms_node.with_metadata(metadata)

        # Add capabilities
        dbms_node.add_capability("host").and_node()

        return dbms_node

    def _create_database_node(
        self,
        builder: "ServiceTemplateBuilder",
        node_name: str,
        clean_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        values: dict[str, Any],
        metadata_values: dict[str, Any],
    ):
        """Create and configure the Database node for ElastiCache cluster."""
        database_node = builder.add_node(name=node_name, node_type="Database")

        # Build metadata
        metadata: dict[str, Any] = {
            "original_resource_type": resource_type,
            "original_resource_name": clean_name,
            "aws_component_type": "CacheDatabase",
            "description": "Logical cache database within AWS ElastiCache cluster",
        }

        # Provider information
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # Database name - use cluster_id as the logical name
        cluster_id = values.get("cluster_id")
        if cluster_id:
            database_node.with_property("name", cluster_id)
            metadata["aws_cluster_id"] = cluster_id
        else:
            # Use clean_name as fallback
            database_node.with_property("name", clean_name)

        # Port (inherit from DBMS) - Required property for Database node
        port = self._resolve_port_with_default(values.get("port"), metadata_values)
        database_node.with_property("port", port)
        if port != values.get("port"):
            metadata["aws_default_port"] = port

        # Encryption settings
        metadata_transit_encryption_enabled = metadata_values.get(
            "transit_encryption_enabled"
        )
        if metadata_transit_encryption_enabled is not None:
            metadata["aws_transit_encryption_enabled"] = (
                metadata_transit_encryption_enabled
            )

        metadata_at_rest_encryption_enabled = metadata_values.get(
            "at_rest_encryption_enabled"
        )
        if metadata_at_rest_encryption_enabled is not None:
            metadata["aws_at_rest_encryption_enabled"] = (
                metadata_at_rest_encryption_enabled
            )

        # Auth token (if Redis with encryption)
        auth_token = values.get("auth_token")
        if auth_token:
            # Store reference instead of actual token for security
            metadata["aws_auth_token_configured"] = True

        # Network type
        metadata_network_type = metadata_values.get("network_type")
        if metadata_network_type:
            metadata["aws_network_type"] = metadata_network_type

        # IP discovery
        metadata_ip_discovery = metadata_values.get("ip_discovery")
        if metadata_ip_discovery:
            metadata["aws_ip_discovery"] = metadata_ip_discovery

        # Logging configuration
        metadata_log_delivery_configuration = metadata_values.get(
            "log_delivery_configuration", []
        )
        if metadata_log_delivery_configuration:
            metadata["aws_log_delivery_configuration"] = (
                metadata_log_delivery_configuration
            )

        # Notification settings
        metadata_notification_topic_arn = metadata_values.get("notification_topic_arn")
        if metadata_notification_topic_arn:
            metadata["aws_notification_topic_arn"] = metadata_notification_topic_arn

        # Tags
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        # Attach metadata to the node
        database_node.with_metadata(metadata)

        # Add capabilities
        database_node.add_capability("database_endpoint").and_node()

        return database_node
