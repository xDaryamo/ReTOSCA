import logging
from typing import TYPE_CHECKING, Any, TypeAlias

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper
from src.plugins.terraform.exceptions import TerraformDataError

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

# Type aliases for better code clarity
ResourceData: TypeAlias = dict[str, Any]
MetadataDict: TypeAlias = dict[str, Any]

logger = logging.getLogger(__name__)


class AWSElastiCacheReplicationGroupMapper(SingleResourceMapper):
    """Map Terraform 'aws_elasticache_replication_group' to TOSCA DBMS and Database.

    This mapper creates two interconnected nodes:
    1. DBMS node - represents the ElastiCache infrastructure and engine
    2. Database node - represents the logical replication group database

    The replication group provides a clustered Redis cache with high availability,
    automatic failover, and read scaling capabilities.
    """

    # Class constants for engine mappings to avoid recreation overhead
    _ENGINE_DEFAULT_PORTS: dict[str, int] = {
        "redis": 6379,
        "memcached": 11211,
    }

    _ENGINE_TYPE_MAPPING: dict[str, str] = {
        "redis": "Redis",
        "memcached": "Memcached",
    }

    def __init__(self):
        """Initialize the mapper with ElastiCache engine type mapping."""
        super().__init__()
        self._logger = logging.getLogger(self.__class__.__name__)

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
        """Map aws_elasticache_replication_group resource to TOSCA DBMS and Database.

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
            raise TerraformDataError(
                f"Resource '{resource_name}' has no 'values' section",
                resource_name=resource_name,
                missing_field="values",
            )

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

        # Create the DBMS node
        self._create_dbms_node(
            builder,
            dbms_node_name,
            clean_name,
            resource_type,
            resource_data,
            values,
            context,
        )

        # Create the Database node
        database_node = self._create_database_node(
            builder,
            database_node_name,
            clean_name,
            resource_type,
            resource_data,
            values,
            context,
        )

        # Create the relationship between Database and DBMS
        database_node.add_requirement("host").to_node(dbms_node_name).with_relationship(
            "HostedOn"
        ).and_node()

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
                    # target_ref is like "aws_elasticache_subnet_group.main"
                    target_resource_type = target_ref.split(".", 1)[0]
                    target_node_name = BaseResourceMapper.generate_tosca_node_name(
                        target_ref, target_resource_type
                    )

                    # Add requirement with the property name as the requirement name
                    requirement_name = (
                        prop_name if prop_name not in ["dependency"] else "dependency"
                    )

                    # For ElastiCache replication groups, both DBMS and Database
                    # nodes might need dependencies - Apply to DBMS node for
                    # infrastructure-level dependencies
                    dbms_node = builder.get_node(dbms_node_name)
                    if dbms_node:
                        (
                            dbms_node.add_requirement(requirement_name)
                            .to_node(target_node_name)
                            .with_relationship(relationship_type)
                            .and_node()
                        )

                        logger.info(
                            "Added %s requirement '%s' to DBMS '%s' with "
                            "relationship %s",
                            requirement_name,
                            target_node_name,
                            dbms_node_name,
                            relationship_type,
                        )
        else:
            logger.warning(
                "No context provided to detect dependencies for resource '%s'",
                resource_name,
            )

        logger.debug(
            "ElastiCache Replication Group nodes '%s' and '%s' created successfully.",
            dbms_node_name,
            database_node_name,
        )

        logger.debug(
            "ElastiCache Replication Group nodes '%s' and '%s' created successfully",
            dbms_node_name,
            database_node_name,
        )

    def _get_resolved_values(
        self,
        resource_data: ResourceData,
        context: "TerraformMappingContext | None",
        value_type: str,
    ) -> MetadataDict:
        """Get resolved values with caching for performance."""
        if context:
            # Use context to resolve values
            return context.get_resolved_values(resource_data, value_type)
        else:
            # Fallback to raw values if no context available
            return resource_data.get("values", {})

    def _create_dbms_node(
        self,
        builder: "ServiceTemplateBuilder",
        node_name: str,
        clean_name: str,
        resource_type: str,
        resource_data: ResourceData,
        values: MetadataDict,
        context: "TerraformMappingContext | None" = None,
    ):
        """Create and configure the DBMS node for ElastiCache Replication Group."""
        dbms_node = builder.add_node(name=node_name, node_type="DBMS")

        # Get resolved values specifically for metadata (always concrete values)
        metadata_values = self._get_resolved_values(resource_data, context, "metadata")

        # Build metadata
        metadata: dict[str, Any] = {
            "original_resource_type": resource_type,
            "original_resource_name": clean_name,
            "aws_component_type": "DBMS",
        }

        # Provider information
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # ElastiCache specific metadata
        replication_group_id = metadata_values.get("replication_group_id", clean_name)
        metadata["aws_replication_group_id"] = replication_group_id

        # Engine information
        engine = metadata_values.get("engine", "redis")  # Default to redis
        metadata["aws_engine"] = engine

        # Map engine to standardized type
        engine_type = self._ENGINE_TYPE_MAPPING.get(engine.lower(), engine.capitalize())
        metadata["aws_engine_type"] = engine_type

        # Engine version
        engine_version = metadata_values.get("engine_version")
        if engine_version:
            metadata["aws_engine_version"] = engine_version

        # Node type (instance class)
        node_type = metadata_values.get("node_type")
        if node_type:
            metadata["aws_node_type"] = node_type

        # Port information
        port = metadata_values.get("port")
        if port:
            dbms_node.with_property("port", port)
            metadata["aws_port"] = port
        else:
            # Use default port based on engine
            default_port = self._ENGINE_DEFAULT_PORTS.get(engine.lower(), 6379)
            dbms_node.with_property("port", default_port)
            metadata["aws_default_port"] = default_port

        # High availability and clustering
        num_cache_clusters = metadata_values.get("num_cache_clusters")
        if num_cache_clusters:
            metadata["aws_num_cache_clusters"] = num_cache_clusters

        automatic_failover = metadata_values.get("automatic_failover_enabled")
        if automatic_failover is not None:
            metadata["aws_automatic_failover_enabled"] = automatic_failover

        multi_az = metadata_values.get("multi_az_enabled")
        if multi_az is not None:
            metadata["aws_multi_az_enabled"] = multi_az

        # Security and encryption
        auth_token = metadata_values.get("auth_token")
        if auth_token:
            metadata["aws_auth_token_enabled"] = True

        at_rest_encryption = metadata_values.get("at_rest_encryption_enabled")
        if at_rest_encryption is not None:
            metadata["aws_at_rest_encryption_enabled"] = at_rest_encryption

        transit_encryption = metadata_values.get("transit_encryption_enabled")
        if transit_encryption is not None:
            metadata["aws_transit_encryption_enabled"] = transit_encryption

        # Set metadata on the node
        dbms_node.with_metadata(metadata)

        return dbms_node

    def _create_database_node(
        self,
        builder: "ServiceTemplateBuilder",
        node_name: str,
        clean_name: str,
        resource_type: str,
        resource_data: ResourceData,
        values: MetadataDict,
        context: "TerraformMappingContext | None" = None,
    ):
        """Create and configure the Database node for ElastiCache Replication Group."""
        database_node = builder.add_node(name=node_name, node_type="Database")

        # Get resolved values specifically for metadata (always concrete values)
        metadata_values = self._get_resolved_values(resource_data, context, "metadata")

        # Build metadata
        metadata: dict[str, Any] = {
            "original_resource_type": resource_type,
            "original_resource_name": clean_name,
            "aws_component_type": "Database",
        }

        # Provider information
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # Database name - use replication group ID as the logical database name
        replication_group_id = values.get("replication_group_id", clean_name)
        database_node.with_property("name", replication_group_id)

        # Port information (inherit from DBMS)
        port = metadata_values.get("port")
        if port:
            database_node.with_property("port", port)
        else:
            # Use default port based on engine
            engine = metadata_values.get("engine", "redis")
            default_port = self._ENGINE_DEFAULT_PORTS.get(engine.lower(), 6379)
            database_node.with_property("port", default_port)

        # Description if provided
        description = metadata_values.get("description")
        if description:
            metadata["aws_description"] = description

        # Set metadata on the node
        database_node.with_metadata(metadata)

        return database_node
