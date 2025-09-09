import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSRDSClusterMapper(SingleResourceMapper):
    """Map a Terraform 'aws_rds_cluster' resource to TOSCA DBMS and Database nodes.

    This mapper creates two interconnected nodes for RDS Aurora clusters:
    1. DBMS node - represents the cluster management system
    2. Database node - represents the logical database instance within the cluster
    """

    def __init__(self):
        """Initialize the mapper with database engine type mapping."""
        super().__init__()
        self._logger = logging.getLogger(self.__class__.__name__)
        # Mapping from AWS RDS cluster engine names to more standardized types
        self._engine_type_mapping = {
            "aurora": "Aurora",
            "aurora-mysql": "Aurora MySQL",
            "aurora-postgresql": "Aurora PostgreSQL",
            "mysql": "MySQL",
            "postgres": "PostgreSQL",
            "postgresql": "PostgreSQL",
        }

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_rds_cluster'."""
        return resource_type == "aws_rds_cluster"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Translate an aws_rds_cluster resource into TOSCA DBMS and Database nodes.

        Args:
            resource_name: resource name (e.g. 'aws_rds_cluster.aurora_cluster')
            resource_type: resource type (always 'aws_rds_cluster')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for variable resolution
        """
        logger.info("Mapping RDS Cluster resource: '%s'", resource_name)

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

        # Generate unique TOSCA node names
        base_node_name = BaseResourceMapper.generate_tosca_node_name(
            resource_name, resource_type
        )
        dbms_node_name = f"{base_node_name}_dbms"
        database_node_name = f"{base_node_name}_database"

        # Create the DBMS node (for cluster-level management)
        self._create_dbms_node(
            builder,
            dbms_node_name,
            clean_name,
            resource_type,
            resource_data,
            values,
            context,
        )

        # Create the Database node (for logical database within cluster)
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
                    # target_ref is like "aws_db_subnet_group.cluster_subnet_group"
                    target_resource_type = target_ref.split(".", 1)[0]
                    target_node_name = BaseResourceMapper.generate_tosca_node_name(
                        target_ref, target_resource_type
                    )

                    # Add requirement with the property name as the requirement name
                    requirement_name = (
                        prop_name if prop_name not in ["dependency"] else "dependency"
                    )

                    # For RDS clusters, both DBMS and Database nodes might need
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
                            "Added %s requirement '%s' to DBMS '%s' with rel %s",
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
            "RDS Cluster nodes '%s' and '%s' created successfully.",
            dbms_node_name,
            database_node_name,
        )

        # Debug: log mapped properties
        if context:
            debug_metadata_values = context.get_resolved_values(
                resource_data, "metadata"
            )
        else:
            debug_metadata_values = resource_data.get("values", {})

        logger.debug(
            "DBMS node properties - Engine: %s, Version: %s",
            debug_metadata_values.get("engine"),
            debug_metadata_values.get("engine_version"),
        )
        logger.debug(
            "Database node properties - Name: %s, User: %s",
            debug_metadata_values.get("database_name"),
            debug_metadata_values.get("master_username"),
        )

    def _create_dbms_node(
        self,
        builder: "ServiceTemplateBuilder",
        node_name: str,
        clean_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        values: dict[str, Any],
        context: "TerraformMappingContext | None" = None,
    ):
        """Create and configure the DBMS node for RDS cluster."""
        dbms_node = builder.add_node(name=node_name, node_type="DBMS")

        # Get resolved values specifically for metadata (always concrete values)
        if context:
            metadata_values = context.get_resolved_values(resource_data, "metadata")
        else:
            metadata_values = resource_data.get("values", {})

        # Build metadata
        metadata: dict[str, Any] = {
            "original_resource_type": resource_type,
            "original_resource_name": clean_name,
            "aws_component_type": "RDSCluster",
            "description": "AWS RDS Aurora cluster providing managed clustering",
        }

        # Provider information
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # Engine information - use metadata values for concrete resolution
        metadata_engine = metadata_values.get("engine")
        if metadata_engine:
            # Map to standardized engine type
            standardized_engine = self._engine_type_mapping.get(
                metadata_engine, metadata_engine
            )
            metadata["aws_engine"] = metadata_engine
            metadata["engine_type"] = standardized_engine

        # Engine version
        metadata_engine_version = metadata_values.get("engine_version")
        if metadata_engine_version:
            metadata["aws_engine_version"] = metadata_engine_version

        # Engine mode (for Aurora)
        metadata_engine_mode = metadata_values.get("engine_mode")
        if metadata_engine_mode:
            metadata["aws_engine_mode"] = metadata_engine_mode

        # Cluster identifier
        metadata_cluster_identifier = metadata_values.get("cluster_identifier")
        if metadata_cluster_identifier:
            metadata["aws_cluster_identifier"] = metadata_cluster_identifier

        # Storage configuration
        metadata_storage_type = metadata_values.get("storage_type")
        if metadata_storage_type:
            metadata["aws_storage_type"] = metadata_storage_type

        metadata_allocated_storage = metadata_values.get("allocated_storage")
        if metadata_allocated_storage:
            metadata["aws_allocated_storage"] = metadata_allocated_storage

        metadata_storage_encrypted = metadata_values.get("storage_encrypted")
        if metadata_storage_encrypted is not None:
            metadata["aws_storage_encrypted"] = metadata_storage_encrypted

        metadata_kms_key_id = metadata_values.get("kms_key_id")
        if metadata_kms_key_id:
            metadata["aws_kms_key_id"] = metadata_kms_key_id

        # Backup configuration
        metadata_backup_retention_period = metadata_values.get(
            "backup_retention_period"
        )
        if metadata_backup_retention_period is not None:
            metadata["aws_backup_retention_period"] = metadata_backup_retention_period

        metadata_preferred_backup_window = metadata_values.get(
            "preferred_backup_window"
        )
        if metadata_preferred_backup_window:
            metadata["aws_preferred_backup_window"] = metadata_preferred_backup_window

        metadata_copy_tags_to_snapshot = metadata_values.get("copy_tags_to_snapshot")
        if metadata_copy_tags_to_snapshot is not None:
            metadata["aws_copy_tags_to_snapshot"] = metadata_copy_tags_to_snapshot

        # Maintenance window
        metadata_preferred_maintenance_window = metadata_values.get(
            "preferred_maintenance_window"
        )
        if metadata_preferred_maintenance_window:
            metadata["aws_preferred_maintenance_window"] = (
                metadata_preferred_maintenance_window
            )

        # Availability zones
        metadata_availability_zones = metadata_values.get("availability_zones", [])
        if metadata_availability_zones:
            metadata["aws_availability_zones"] = metadata_availability_zones

        # Port (set as DBMS property)
        port = values.get("port")
        if port:
            dbms_node.with_property("port", port)
        else:
            # Set default ports based on engine type if not specified
            default_ports = {
                "aurora": 3306,  # Aurora MySQL default
                "aurora-mysql": 3306,
                "aurora-postgresql": 5432,
                "mysql": 3306,
                "postgres": 5432,
                "postgresql": 5432,
            }
            metadata_engine_for_port = metadata_values.get("engine")
            if metadata_engine_for_port and metadata_engine_for_port in default_ports:
                dbms_node.with_property("port", default_ports[metadata_engine_for_port])
                metadata["aws_default_port"] = default_ports[metadata_engine_for_port]

        # Master password (if not using managed password)
        master_password = values.get("master_password")
        metadata_manage_master_user_password = metadata_values.get(
            "manage_master_user_password"
        )
        if master_password and not metadata_manage_master_user_password:
            dbms_node.with_property("root_password", master_password)
        elif metadata_manage_master_user_password:
            metadata["aws_managed_master_password"] = True

        # Cluster security and networking
        metadata_vpc_security_group_ids = metadata_values.get(
            "vpc_security_group_ids", []
        )
        if metadata_vpc_security_group_ids:
            metadata["aws_vpc_security_group_ids"] = metadata_vpc_security_group_ids

        metadata_db_subnet_group_name = metadata_values.get("db_subnet_group_name")
        if metadata_db_subnet_group_name:
            metadata["aws_db_subnet_group_name"] = metadata_db_subnet_group_name

        metadata_db_cluster_parameter_group_name = metadata_values.get(
            "db_cluster_parameter_group_name"
        )
        if metadata_db_cluster_parameter_group_name:
            metadata["aws_db_cluster_parameter_group_name"] = (
                metadata_db_cluster_parameter_group_name
            )

        # Deletion protection
        metadata_deletion_protection = metadata_values.get("deletion_protection")
        if metadata_deletion_protection is not None:
            metadata["aws_deletion_protection"] = metadata_deletion_protection

        # Skip final snapshot
        metadata_skip_final_snapshot = metadata_values.get("skip_final_snapshot")
        if metadata_skip_final_snapshot is not None:
            metadata["aws_skip_final_snapshot"] = metadata_skip_final_snapshot

        # Final snapshot identifier
        metadata_final_snapshot_identifier = metadata_values.get(
            "final_snapshot_identifier"
        )
        if metadata_final_snapshot_identifier:
            metadata["aws_final_snapshot_identifier"] = (
                metadata_final_snapshot_identifier
            )

        # IAM database authentication
        metadata_iam_db_auth_enabled = metadata_values.get(
            "iam_database_authentication_enabled"
        )
        if metadata_iam_db_auth_enabled is not None:
            metadata["aws_iam_database_authentication_enabled"] = (
                metadata_iam_db_auth_enabled
            )

        # Tags
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        # Tags_all (all tags including provider defaults)
        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

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
        context: "TerraformMappingContext | None" = None,
    ):
        """Create and configure the Database node for RDS cluster."""
        database_node = builder.add_node(name=node_name, node_type="Database")

        # Get resolved values specifically for metadata (always concrete values)
        if context:
            metadata_values = context.get_resolved_values(resource_data, "metadata")
        else:
            metadata_values = resource_data.get("values", {})

        # Build metadata
        metadata: dict[str, Any] = {
            "original_resource_type": resource_type,
            "original_resource_name": clean_name,
            "aws_component_type": "ClusterDatabase",
            "description": "Logical database within AWS RDS Aurora cluster",
        }

        # Provider information
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # Get resource address for variable resolution
        resource_address = resource_data.get("address", f"aws_rds_cluster.{clean_name}")

        # IMPORTANT: For metadata, always use concrete values (never $get_input)
        # Store the actual resolved database name in metadata for reference
        database_name_concrete = values.get("database_name")
        if context and context.variable_context:
            database_name_concrete = context.variable_context.get_concrete_value(
                resource_address, "database_name"
            ) or values.get("database_name")

        if database_name_concrete is not None:
            metadata["aws_database_name"] = database_name_concrete

        # Database name - Required property for Database node
        # Use variable-aware resolution for database_name
        database_name_resolved = values.get("database_name")
        if context and context.variable_context:
            database_name_resolved = context.variable_context.resolve_property(
                resource_address, "database_name", "property"
            ) or values.get("database_name")

        if database_name_resolved is not None:
            database_node.with_property("name", database_name_resolved)
            # Log the resolution for debugging
            if (
                isinstance(database_name_resolved, dict)
                and "$get_input" in database_name_resolved
            ):
                logger.debug(
                    "Property database_name resolved to $get_input:%s "
                    "(variable-backed)",
                    database_name_resolved["$get_input"],
                )
            else:
                logger.debug(
                    "Property database_name resolved to %s (concrete value)",
                    database_name_resolved,
                )
        else:
            # Use cluster_identifier or fallback to clean_name if database_name
            # is not specified
            cluster_identifier = values.get("cluster_identifier", clean_name)
            database_node.with_property("name", cluster_identifier)

        # Port (inherit from DBMS) - Required property for Database node
        port = values.get("port")
        if port:
            database_node.with_property("port", port)
        else:
            # Set default ports based on engine type if not specified
            default_ports = {
                "aurora": 3306,  # Aurora MySQL default
                "aurora-mysql": 3306,
                "aurora-postgresql": 5432,
                "mysql": 3306,
                "postgres": 5432,
                "postgresql": 5432,
            }
            metadata_engine_for_port = metadata_values.get("engine")
            if metadata_engine_for_port and metadata_engine_for_port in default_ports:
                database_node.with_property(
                    "port", default_ports[metadata_engine_for_port]
                )
                metadata["aws_default_port"] = default_ports[metadata_engine_for_port]
            else:
                # Fallback to a generic default port if engine is unknown
                database_node.with_property("port", 3306)
                metadata["aws_default_port"] = 3306

        # Master username
        master_username = values.get("master_username")
        if master_username:
            database_node.with_property("user", master_username)

        # Master password (if not using managed password)
        master_password = values.get("master_password")
        metadata_manage_master_user_password = metadata_values.get(
            "manage_master_user_password"
        )
        if master_password and not metadata_manage_master_user_password:
            database_node.with_property("password", master_password)

        # Cluster identifier
        metadata_cluster_identifier = metadata_values.get("cluster_identifier")
        if metadata_cluster_identifier:
            metadata["aws_cluster_identifier"] = metadata_cluster_identifier

        # Character set (for MySQL-based engines)
        metadata_character_set_name = metadata_values.get("character_set_name")
        if metadata_character_set_name:
            metadata["aws_character_set_name"] = metadata_character_set_name

        # Global cluster configuration
        metadata_global_cluster_identifier = metadata_values.get(
            "global_cluster_identifier"
        )
        if metadata_global_cluster_identifier:
            metadata["aws_global_cluster_identifier"] = (
                metadata_global_cluster_identifier
            )

        # Replication source identifier (for read replicas)
        metadata_replication_source_identifier = metadata_values.get(
            "replication_source_identifier"
        )
        if metadata_replication_source_identifier:
            metadata["aws_replication_source_identifier"] = (
                metadata_replication_source_identifier
            )

        # Source region (for cross-region replicas)
        metadata_source_region = metadata_values.get("source_region")
        if metadata_source_region:
            metadata["aws_source_region"] = metadata_source_region

        # Enabled CloudWatch logs exports
        metadata_enabled_cloudwatch_logs_exports = metadata_values.get(
            "enabled_cloudwatch_logs_exports", []
        )
        if metadata_enabled_cloudwatch_logs_exports:
            metadata["aws_enabled_cloudwatch_logs_exports"] = (
                metadata_enabled_cloudwatch_logs_exports
            )

        # Tags
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        # Tags_all (all tags including provider defaults)
        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

        # Attach metadata to the node
        database_node.with_metadata(metadata)

        # Add capabilities
        database_node.add_capability("database_endpoint").and_node()

        return database_node
