import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper
from src.plugins.terraform.terraform_mapper_base import TerraformResourceMapperMixin

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder

logger = logging.getLogger(__name__)


class AWSDBInstanceMapper(TerraformResourceMapperMixin, SingleResourceMapper):
    """Map a Terraform 'aws_db_instance' resource to TOSCA DBMS and Database nodes.

    This mapper creates two interconnected nodes:
    1. DBMS node - represents the database management system
    2. Database node - represents the logical database instance
    """

    def __init__(self):
        """Initialize the mapper with database engine type mapping."""
        super().__init__()
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
    ) -> None:
        """Translate an aws_db_instance resource into TOSCA DBMS and Database nodes.

        Args:
            resource_name: resource name (e.g. 'aws_db_instance.default')
            resource_type: resource type (always 'aws_db_instance')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
        """
        logger.info("Mapping DB Instance resource: '%s'", resource_name)

        # Validate input data
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
            builder, dbms_node_name, clean_name, resource_type, resource_data, values
        )

        # Create the Database node
        database_node = self._create_database_node(
            builder,
            database_node_name,
            clean_name,
            resource_type,
            resource_data,
            values,
        )

        # Create the relationship between Database and DBMS
        database_node.add_requirement("host").to_node(dbms_node_name).with_relationship(
            "HostedOn"
        ).and_node()

        logger.debug(
            "DB Instance nodes '%s' and '%s' created successfully.",
            dbms_node_name,
            database_node_name,
        )

        # Debug: log mapped properties
        logger.debug(
            "DBMS node properties - Engine: %s, Version: %s, Class: %s",
            values.get("engine"),
            values.get("engine_version"),
            values.get("instance_class"),
        )
        logger.debug(
            "Database node properties - Name: %s, User: %s",
            values.get("db_name"),
            values.get("username"),
        )

    def _create_dbms_node(
        self,
        builder: "ServiceTemplateBuilder",
        node_name: str,
        clean_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        values: dict[str, Any],
    ):
        """Create and configure the DBMS node."""
        dbms_node = builder.add_node(name=node_name, node_type="DBMS")

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

        # Engine information
        engine = values.get("engine")
        if engine:
            # Map to standardized engine type
            standardized_engine = self._engine_type_mapping.get(engine, engine)
            metadata["aws_engine"] = engine
            metadata["engine_type"] = standardized_engine

        # Engine version
        engine_version = values.get("engine_version")
        if engine_version:
            metadata["aws_engine_version"] = engine_version

        # Instance class
        instance_class = values.get("instance_class")
        if instance_class:
            metadata["aws_instance_class"] = instance_class

        # License model
        license_model = values.get("license_model")
        if license_model:
            metadata["aws_license_model"] = license_model

        # Multi-AZ configuration
        multi_az = values.get("multi_az")
        if multi_az is not None:
            metadata["aws_multi_az"] = multi_az

        # Storage information
        allocated_storage = values.get("allocated_storage")
        if allocated_storage:
            metadata["aws_allocated_storage"] = allocated_storage

        storage_type = values.get("storage_type")
        if storage_type:
            metadata["aws_storage_type"] = storage_type

        storage_encrypted = values.get("storage_encrypted")
        if storage_encrypted is not None:
            metadata["aws_storage_encrypted"] = storage_encrypted

        # Backup configuration
        backup_retention_period = values.get("backup_retention_period")
        if backup_retention_period is not None:
            metadata["aws_backup_retention_period"] = backup_retention_period

        backup_window = values.get("backup_window")
        if backup_window:
            metadata["aws_backup_window"] = backup_window

        # Maintenance window
        maintenance_window = values.get("maintenance_window")
        if maintenance_window:
            metadata["aws_maintenance_window"] = maintenance_window

        # Monitoring
        monitoring_interval = values.get("monitoring_interval")
        if monitoring_interval is not None:
            metadata["aws_monitoring_interval"] = monitoring_interval

        # Performance Insights
        performance_insights_enabled = values.get("performance_insights_enabled")
        if performance_insights_enabled is not None:
            metadata["aws_performance_insights_enabled"] = performance_insights_enabled

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
            engine = values.get("engine")
            if engine and engine in default_ports:
                dbms_node.with_property("port", default_ports[engine])
                metadata["aws_default_port"] = default_ports[engine]

        # Root password (if not using managed password)
        password = values.get("password")
        manage_master_user_password = values.get("manage_master_user_password")
        if password and not manage_master_user_password:
            dbms_node.with_property("root_password", password)
        elif manage_master_user_password:
            metadata["aws_managed_master_password"] = True

        # Security groups and networking
        vpc_security_group_ids = values.get("vpc_security_group_ids", [])
        if vpc_security_group_ids:
            metadata["aws_vpc_security_group_ids"] = vpc_security_group_ids

        db_subnet_group_name = values.get("db_subnet_group_name")
        if db_subnet_group_name:
            metadata["aws_db_subnet_group_name"] = db_subnet_group_name

        # Availability zone
        availability_zone = values.get("availability_zone")
        if availability_zone:
            metadata["aws_availability_zone"] = availability_zone

        # Tags
        tags = values.get("tags", {})
        if tags:
            metadata["aws_tags"] = tags

        # Tags_all (all tags including provider defaults)
        tags_all = values.get("tags_all", {})
        if tags_all and tags_all != tags:
            metadata["aws_tags_all"] = tags_all

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
    ):
        """Create and configure the Database node."""
        database_node = builder.add_node(name=node_name, node_type="Database")

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
        db_name_concrete = self.get_concrete_value(
            resource_address=resource_address,
            property_name="db_name",
            fallback_value=values.get("db_name"),
        )
        if db_name_concrete is not None:
            metadata["aws_database_name"] = db_name_concrete

        # Database name - Required property for Database node
        # Use variable-aware resolution for db_name
        db_name_resolved = self.resolve_property_value(
            resource_address=resource_address,
            property_name="db_name",
            fallback_value=values.get("db_name"),
            context="property",
        )

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
            engine = values.get("engine")
            if engine and engine in default_ports:
                database_node.with_property("port", default_ports[engine])
                metadata["aws_default_port"] = default_ports[engine]
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
        manage_master_user_password = values.get("manage_master_user_password")
        if password and not manage_master_user_password:
            database_node.with_property("password", password)

        # Identifier
        identifier = values.get("identifier")
        if identifier:
            metadata["aws_identifier"] = identifier

        # Character set (for Oracle and SQL Server)
        character_set_name = values.get("character_set_name")
        if character_set_name:
            metadata["aws_character_set_name"] = character_set_name

        # National character set (for Oracle)
        nchar_character_set_name = values.get("nchar_character_set_name")
        if nchar_character_set_name:
            metadata["aws_nchar_character_set_name"] = nchar_character_set_name

        # Timezone (for SQL Server)
        timezone = values.get("timezone")
        if timezone:
            metadata["aws_timezone"] = timezone

        # Deletion protection
        deletion_protection = values.get("deletion_protection")
        if deletion_protection is not None:
            metadata["aws_deletion_protection"] = deletion_protection

        # IAM database authentication
        iam_db_auth_enabled = values.get("iam_database_authentication_enabled")
        if iam_db_auth_enabled is not None:
            metadata["aws_iam_database_authentication_enabled"] = iam_db_auth_enabled

        # Public accessibility
        publicly_accessible = values.get("publicly_accessible")
        if publicly_accessible is not None:
            metadata["aws_publicly_accessible"] = publicly_accessible

        # Tags
        tags = values.get("tags", {})
        if tags:
            metadata["aws_tags"] = tags

        # Tags_all (all tags including provider defaults)
        tags_all = values.get("tags_all", {})
        if tags_all and tags_all != tags:
            metadata["aws_tags_all"] = tags_all

        # Attach metadata to the node
        database_node.with_metadata(metadata)

        # Add capabilities
        database_node.add_capability("database_endpoint").and_node()

        return database_node
