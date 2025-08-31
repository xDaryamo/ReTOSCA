import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSDBInstanceMapper(SingleResourceMapper):
    """Map a Terraform 'aws_db_instance' resource to TOSCA DBMS and Database nodes.

    This mapper creates two interconnected nodes:
    1. DBMS node - represents the database management system
    2. Database node - represents the logical database instance
    """

    def __init__(self):
        """Initialize the mapper with database engine type mapping."""
        super().__init__()
        self._logger = logging.getLogger(self.__class__.__name__)
        # Mapping from AWS engine names to more standardized types
        self._engine_type_mapping = {
            "mysql": "MySQL",
            "postgres": "PostgreSQL",
            "postgresql": "PostgreSQL",
            "oracle-ee": "Oracle",
            "oracle-se": "Oracle",
            "oracle-se1": "Oracle",
            "oracle-se2": "Oracle",
            "sqlserver-ee": "SQL Server",
            "sqlserver-se": "SQL Server",
            "sqlserver-ex": "SQL Server",
            "sqlserver-web": "SQL Server",
            "mariadb": "MariaDB",
            "aurora": "Aurora",
            "aurora-mysql": "Aurora MySQL",
            "aurora-postgresql": "Aurora PostgreSQL",
            "custom-oracle-ee": "Custom Oracle",
            "custom-sqlserver-ee": "Custom SQL Server",
            "custom-sqlserver-se": "Custom SQL Server",
            "custom-sqlserver-web": "Custom SQL Server",
            "db2-se": "DB2",
            "db2-ae": "DB2",
        }

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_db_instance'."""
        return resource_type == "aws_db_instance"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Translate an aws_db_instance resource into TOSCA DBMS and Database nodes.

        Args:
            resource_name: resource name (e.g. 'aws_db_instance.default')
            resource_type: resource type (always 'aws_db_instance')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
        """
        logger.info("Mapping DB Instance resource: '%s'", resource_name)

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
                    # target_ref is like "aws_subnet.main"
                    target_resource_type = target_ref.split(".", 1)[0]
                    target_node_name = BaseResourceMapper.generate_tosca_node_name(
                        target_ref, target_resource_type
                    )

                    # Add requirement with the property name as the requirement name
                    requirement_name = (
                        prop_name if prop_name not in ["dependency"] else "dependency"
                    )

                    # For DB instances, both DBMS and Database nodes might need
                    # dependencies
                    # Apply to DBMS node for infrastructure-level dependencies
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
            "DB Instance nodes '%s' and '%s' created successfully.",
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
            "DBMS node properties - Engine: %s, Version: %s, Class: %s",
            debug_metadata_values.get("engine"),
            debug_metadata_values.get("engine_version"),
            debug_metadata_values.get("instance_class"),
        )
        logger.debug(
            "Database node properties - Name: %s, User: %s",
            debug_metadata_values.get("db_name"),
            debug_metadata_values.get("username"),
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
        """Create and configure the DBMS node."""
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
            "aws_component_type": "DBMS",
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

        # Instance class
        metadata_instance_class = metadata_values.get("instance_class")
        if metadata_instance_class:
            metadata["aws_instance_class"] = metadata_instance_class

        # License model
        metadata_license_model = metadata_values.get("license_model")
        if metadata_license_model:
            metadata["aws_license_model"] = metadata_license_model

        # Multi-AZ configuration
        metadata_multi_az = metadata_values.get("multi_az")
        if metadata_multi_az is not None:
            metadata["aws_multi_az"] = metadata_multi_az

        # Storage information
        metadata_allocated_storage = metadata_values.get("allocated_storage")
        if metadata_allocated_storage:
            metadata["aws_allocated_storage"] = metadata_allocated_storage

        metadata_storage_type = metadata_values.get("storage_type")
        if metadata_storage_type:
            metadata["aws_storage_type"] = metadata_storage_type

        metadata_storage_encrypted = metadata_values.get("storage_encrypted")
        if metadata_storage_encrypted is not None:
            metadata["aws_storage_encrypted"] = metadata_storage_encrypted

        # Backup configuration
        metadata_backup_retention_period = metadata_values.get(
            "backup_retention_period"
        )
        if metadata_backup_retention_period is not None:
            metadata["aws_backup_retention_period"] = metadata_backup_retention_period

        metadata_backup_window = metadata_values.get("backup_window")
        if metadata_backup_window:
            metadata["aws_backup_window"] = metadata_backup_window

        # Maintenance window
        metadata_maintenance_window = metadata_values.get("maintenance_window")
        if metadata_maintenance_window:
            metadata["aws_maintenance_window"] = metadata_maintenance_window

        # Monitoring
        metadata_monitoring_interval = metadata_values.get("monitoring_interval")
        if metadata_monitoring_interval is not None:
            metadata["aws_monitoring_interval"] = metadata_monitoring_interval

        # Performance Insights
        metadata_performance_insights_enabled = metadata_values.get(
            "performance_insights_enabled"
        )
        if metadata_performance_insights_enabled is not None:
            metadata["aws_performance_insights_enabled"] = (
                metadata_performance_insights_enabled
            )

        # Port (set as DBMS property)
        port = values.get("port")
        if port:
            dbms_node.with_property("port", port)
        else:
            # Set default ports based on engine type if not specified
            default_ports = {
                "mysql": 3306,
                "postgres": 5432,
                "postgresql": 5432,
                "oracle-ee": 1521,
                "oracle-se": 1521,
                "oracle-se1": 1521,
                "oracle-se2": 1521,
                "sqlserver-ee": 1433,
                "sqlserver-se": 1433,
                "sqlserver-ex": 1433,
                "sqlserver-web": 1433,
                "mariadb": 3306,
            }
            metadata_engine_for_port = metadata_values.get("engine")
            if metadata_engine_for_port and metadata_engine_for_port in default_ports:
                dbms_node.with_property("port", default_ports[metadata_engine_for_port])
                metadata["aws_default_port"] = default_ports[metadata_engine_for_port]

        # Root password (if not using managed password)
        password = values.get("password")
        metadata_manage_master_user_password = metadata_values.get(
            "manage_master_user_password"
        )
        if password and not metadata_manage_master_user_password:
            dbms_node.with_property("root_password", password)
        elif metadata_manage_master_user_password:
            metadata["aws_managed_master_password"] = True

        # Security groups and networking
        metadata_vpc_security_group_ids = metadata_values.get(
            "vpc_security_group_ids", []
        )
        if metadata_vpc_security_group_ids:
            metadata["aws_vpc_security_group_ids"] = metadata_vpc_security_group_ids

        metadata_db_subnet_group_name = metadata_values.get("db_subnet_group_name")
        if metadata_db_subnet_group_name:
            metadata["aws_db_subnet_group_name"] = metadata_db_subnet_group_name

        # Availability zone
        metadata_availability_zone = metadata_values.get("availability_zone")
        if metadata_availability_zone:
            metadata["aws_availability_zone"] = metadata_availability_zone

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
        """Create and configure the Database node."""
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
            "aws_component_type": "Database",
        }

        # Provider information
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # Get resource address for variable resolution
        resource_address = resource_data.get("address", f"aws_db_instance.{clean_name}")

        # IMPORTANT: For metadata, always use concrete values (never $get_input)
        # Store the actual resolved database name in metadata for reference
        db_name_concrete = values.get("db_name")
        if context and context.variable_context:
            db_name_concrete = context.variable_context.get_concrete_value(
                resource_address, "db_name"
            ) or values.get("db_name")

        if db_name_concrete is not None:
            metadata["aws_database_name"] = db_name_concrete

        # Database name - Required property for Database node
        # Use variable-aware resolution for db_name
        db_name_resolved = values.get("db_name")
        if context and context.variable_context:
            db_name_resolved = context.variable_context.resolve_property(
                resource_address, "db_name", "property"
            ) or values.get("db_name")

        if db_name_resolved is not None:
            database_node.with_property("name", db_name_resolved)
            # Log the resolution for debugging
            if isinstance(db_name_resolved, dict) and "$get_input" in db_name_resolved:
                logger.debug(
                    "Property db_name resolved to $get_input:%s (variable-backed)",
                    db_name_resolved["$get_input"],
                )
            else:
                logger.debug(
                    f"Property db_name resolved to {db_name_resolved} (concrete value)"
                )
        else:
            # Use identifier or fallback to clean_name if db_name is not specified
            identifier = values.get("identifier", clean_name)
            database_node.with_property("name", identifier)

        # Port (inherit from DBMS) - Required property for Database node
        port = values.get("port")
        if port:
            database_node.with_property("port", port)
        else:
            # Set default ports based on engine type if not specified
            default_ports = {
                "mysql": 3306,
                "postgres": 5432,
                "postgresql": 5432,
                "oracle-ee": 1521,
                "oracle-se": 1521,
                "oracle-se1": 1521,
                "oracle-se2": 1521,
                "sqlserver-ee": 1433,
                "sqlserver-se": 1433,
                "sqlserver-ex": 1433,
                "sqlserver-web": 1433,
                "mariadb": 3306,
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

        # Username
        username = values.get("username")
        if username:
            database_node.with_property("user", username)

        # Password (if not using managed password)
        password = values.get("password")
        metadata_manage_master_user_password = metadata_values.get(
            "manage_master_user_password"
        )
        if password and not metadata_manage_master_user_password:
            database_node.with_property("password", password)

        # Identifier
        metadata_identifier = metadata_values.get("identifier")
        if metadata_identifier:
            metadata["aws_identifier"] = metadata_identifier

        # Character set (for Oracle and SQL Server)
        metadata_character_set_name = metadata_values.get("character_set_name")
        if metadata_character_set_name:
            metadata["aws_character_set_name"] = metadata_character_set_name

        # National character set (for Oracle)
        metadata_nchar_character_set_name = metadata_values.get(
            "nchar_character_set_name"
        )
        if metadata_nchar_character_set_name:
            metadata["aws_nchar_character_set_name"] = metadata_nchar_character_set_name

        # Timezone (for SQL Server)
        metadata_timezone = metadata_values.get("timezone")
        if metadata_timezone:
            metadata["aws_timezone"] = metadata_timezone

        # Deletion protection
        metadata_deletion_protection = metadata_values.get("deletion_protection")
        if metadata_deletion_protection is not None:
            metadata["aws_deletion_protection"] = metadata_deletion_protection

        # IAM database authentication
        metadata_iam_db_auth_enabled = metadata_values.get(
            "iam_database_authentication_enabled"
        )
        if metadata_iam_db_auth_enabled is not None:
            metadata["aws_iam_database_authentication_enabled"] = (
                metadata_iam_db_auth_enabled
            )

        # Public accessibility
        metadata_publicly_accessible = metadata_values.get("publicly_accessible")
        if metadata_publicly_accessible is not None:
            metadata["aws_publicly_accessible"] = metadata_publicly_accessible

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
