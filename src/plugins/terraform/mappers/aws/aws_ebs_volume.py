import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSEBSVolumeMapper(SingleResourceMapper):
    """Map a Terraform 'aws_ebs_volume' resource into a
    tosca.nodes.Storage.BlockStorage node.
    """

    # TOSCA property mappings
    TOSCA_PROPERTY_MAPPINGS = {
        "size": "size",
        "id": "volume_id",
        "snapshot_id": "snapshot_id",
    }

    # AWS metadata field mappings
    METADATA_FIELD_MAPPINGS = {
        "availability_zone": "aws_availability_zone",
        "region": "aws_region",
        "encrypted": "aws_encrypted",
        "kms_key_id": "aws_kms_key_id",
        "type": "aws_volume_type",
        "iops": "aws_iops",
        "throughput": "aws_throughput",
        "multi_attach_enabled": "aws_multi_attach_enabled",
        "outpost_arn": "aws_outpost_arn",
        "final_snapshot": "aws_final_snapshot",
        "volume_initialization_rate": "aws_volume_initialization_rate",
        "arn": "aws_arn",
        "create_time": "aws_create_time",
    }

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        return resource_type == "aws_ebs_volume"

    def _get_resolved_values(
        self,
        resource_data: dict[str, Any],
        context: "TerraformMappingContext | None",
        value_type: str = "property",
    ) -> dict[str, Any]:
        """Get resolved values from context or fallback to resource data."""
        if context:
            return context.get_resolved_values(resource_data, value_type)
        return resource_data.get("values", {})

    def _validate_resource_data(
        self, values: dict[str, Any], resource_name: str
    ) -> bool:
        """Validate resource data and return False if should skip mapping."""
        if not values:
            logger.warning(
                f"Resource '{resource_name}' has no 'values' section. Skipping."
            )
            return False
        return True

    def _extract_clean_name(self, resource_name: str) -> str:
        """Extract clean name from resource identifier."""
        if "." in resource_name:
            _, clean_name = resource_name.split(".", 1)
            return clean_name
        return resource_name

    def _set_tosca_properties(self, volume_node, values: dict[str, Any]) -> None:
        """Set standard TOSCA properties on the volume node."""
        for aws_field, tosca_property in self.TOSCA_PROPERTY_MAPPINGS.items():
            value = values.get(aws_field)
            if value:
                if aws_field == "size":
                    # Convert from GiB to GB for TOSCA compliance
                    volume_node.with_property(tosca_property, f"{value} GB")
                else:
                    volume_node.with_property(tosca_property, value)

    def _build_metadata(
        self,
        resource_data: dict[str, Any],
        resource_type: str,
        clean_name: str,
        context: "TerraformMappingContext | None",
    ) -> dict[str, Any]:
        """Build metadata dictionary for the volume node."""
        metadata_values = self._get_resolved_values(resource_data, context, "metadata")

        metadata: dict[str, Any] = {
            "original_resource_type": resource_type,
            "original_resource_name": clean_name,
        }

        # Add provider information
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # Map AWS-specific metadata fields
        for aws_field, metadata_key in self.METADATA_FIELD_MAPPINGS.items():
            value = metadata_values.get(aws_field)
            if value is not None:
                metadata[metadata_key] = value

        # Handle tags separately as they require special processing
        self._add_tags_to_metadata(metadata, metadata_values)

        return metadata

    def _add_tags_to_metadata(
        self, metadata: dict[str, Any], metadata_values: dict[str, Any]
    ) -> None:
        """Add tags to metadata with special handling for tags vs tags_all."""
        tags = metadata_values.get("tags", {})
        if tags:
            metadata["aws_tags"] = tags

        tags_all = metadata_values.get("tags_all", {})
        if tags_all and tags_all != tags:
            metadata["aws_tags_all"] = tags_all

    def _process_dependencies(
        self,
        volume_node,
        resource_data: dict[str, Any],
        context: "TerraformMappingContext | None",
        node_name: str,
        resource_name: str,
    ) -> None:
        """Process Terraform dependencies and add them as requirements."""
        if not context:
            logger.warning(
                "No context provided to detect dependencies for resource '%s'",
                resource_name,
            )
            return

        terraform_refs = context.extract_terraform_references(resource_data)
        logger.debug(
            f"Found {len(terraform_refs)} terraform references for {resource_name}"
        )

        for prop_name, target_ref, relationship_type in terraform_refs:
            self._process_single_dependency(
                volume_node, prop_name, target_ref, relationship_type, node_name
            )

    def _process_single_dependency(
        self,
        volume_node,
        prop_name: str,
        target_ref: str,
        relationship_type: str,
        node_name: str,
    ) -> None:
        """Process a single terraform dependency reference."""
        logger.debug(
            "Processing reference: %s -> %s (%s)",
            prop_name,
            target_ref,
            relationship_type,
        )

        if "." not in target_ref:
            logger.warning(f"Invalid target reference format: {target_ref}")
            return

        # target_ref is like "aws_kms_key.main"
        target_resource_type = target_ref.split(".", 1)[0]
        target_node_name = BaseResourceMapper.generate_tosca_node_name(
            target_ref, target_resource_type
        )

        # Add requirement with the property name as the requirement name
        requirement_name = prop_name if prop_name != "dependency" else "dependency"

        (
            volume_node.add_requirement(requirement_name)
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

    def _log_mapped_properties(
        self,
        node_name: str,
        values: dict[str, Any],
        metadata_values: dict[str, Any],
    ) -> None:
        """Log mapped properties for debugging purposes."""
        if not logger.isEnabledFor(logging.DEBUG):
            return

        logger.debug(f"Mapped properties for '{node_name}':")
        logger.debug(f"  - Size: {values.get('size')} GiB")
        logger.debug(
            f"  - Availability Zone: {metadata_values.get('availability_zone')}"
        )
        logger.debug(f"  - Volume Type: {metadata_values.get('type')}")
        logger.debug(f"  - Encrypted: {metadata_values.get('encrypted')}")
        logger.debug(f"  - IOPS: {metadata_values.get('iops')}")
        logger.debug(f"  - Throughput: {metadata_values.get('throughput')}")
        logger.debug(f"  - Tags: {metadata_values.get('tags', {})}")

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Map AWS EBS Volume to TOSCA Storage.BlockStorage node.

        Args:
            resource_name: Terraform resource identifier (e.g., "aws_ebs_volume.main")
            resource_type: Must be "aws_ebs_volume"
            resource_data: Terraform resource configuration including 'values' section
            builder: TOSCA service template builder for node creation
            context: Optional context for variable resolution and dependencies

        Note:
            Silently returns if resource_data has no 'values' section,
            logging a warning.
        """
        logger.info(f"Mapping EBS Volume resource: '{resource_name}'")

        # Get and validate resolved values
        values = self._get_resolved_values(resource_data, context, "property")
        if not self._validate_resource_data(values, resource_name):
            return

        # Extract clean name and generate node name
        clean_name = self._extract_clean_name(resource_name)
        node_name = BaseResourceMapper.generate_tosca_node_name(
            resource_name, resource_type
        )

        # Create the BlockStorage node
        volume_node = builder.add_node(name=node_name, node_type="Storage.BlockStorage")

        # Set standard TOSCA properties
        self._set_tosca_properties(volume_node, values)

        # Build and set metadata
        metadata = self._build_metadata(
            resource_data, resource_type, clean_name, context
        )
        volume_node.with_metadata(metadata)

        # Add the 'attachment' capability to allow attaching to compute nodes
        volume_node.add_capability("attachment").and_node()

        # Process dependencies
        self._process_dependencies(
            volume_node, resource_data, context, node_name, resource_name
        )

        logger.debug(f"Storage.BlockStorage node '{node_name}' created successfully.")

        # Log mapped properties for debugging
        metadata_values = self._get_resolved_values(resource_data, context, "metadata")
        self._log_mapped_properties(node_name, values, metadata_values)
