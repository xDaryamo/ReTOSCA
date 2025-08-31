import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSVolumeAttachmentMapper(SingleResourceMapper):
    """Map a Terraform 'aws_volume_attachment' resource to TOSCA relationships.

    This mapper doesn't create a separate node but instead modifies existing nodes
    to establish the attachment relationship between a Compute node and a
    BlockStorage node.

    Args:
        resource_name: Name of the aws_volume_attachment resource
        resource_type: Type of the resource (always 'aws_volume_attachment')
        resource_data: Resource configuration data from Terraform plan
        builder: ServiceTemplateBuilder instance for TOSCA template construction
        context: TerraformMappingContext for dependency resolution and variable handling
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_volume_attachment'."""
        return resource_type == "aws_volume_attachment"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Create attachment relationship between instance and EBS volume.

        This mapper doesn't create a new TOSCA node. Instead, it modifies the existing
        Compute node to add a local_storage requirement pointing to the EBS volume.

        Args:
            resource_name: Resource name (e.g. 'aws_volume_attachment.ebs_att')
            resource_type: Resource type (always 'aws_volume_attachment')
            resource_data: Resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for dependency resolution and
                variable handling
        """
        logger.info("Processing volume attachment resource: '%s'", resource_name)

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

        # Get device name
        device_name = values.get("device_name")
        if not device_name:
            logger.warning(
                "No device_name found for volume attachment '%s'. Skipping.",
                resource_name,
            )
            return

        # Find instance and volume references from configuration
        if not context:
            logger.warning(
                "No context provided to resolve references for '%s'. Skipping.",
                resource_name,
            )
            return

        instance_address, volume_address = self._extract_references(
            resource_data, context
        )

        if not instance_address or not volume_address:
            logger.warning(
                "Could not resolve instance or volume references for '%s'. "
                "Instance: %s, Volume: %s",
                resource_name,
                instance_address,
                volume_address,
            )
            return

        # Generate TOSCA node names
        instance_node_name = BaseResourceMapper.generate_tosca_node_name(
            instance_address, "aws_instance"
        )
        volume_node_name = BaseResourceMapper.generate_tosca_node_name(
            volume_address, "aws_ebs_volume"
        )

        # Find the instance node in the builder
        instance_node = self._find_node_in_builder(builder, instance_node_name)
        if not instance_node:
            logger.warning(
                "Instance node '%s' not found. The aws_instance mapper may not "
                "have run yet. Volume attachment for '%s' will be skipped.",
                instance_node_name,
                resource_name,
            )
            return

        # Check if volume node exists
        volume_node = self._find_node_in_builder(builder, volume_node_name)
        if not volume_node:
            logger.warning(
                "Volume node '%s' not found. The aws_ebs_volume mapper may not "
                "have run yet. Volume attachment for '%s' will be skipped.",
                volume_node_name,
                resource_name,
            )
            return

        # Add the local_storage requirement to the instance
        self._add_volume_attachment_requirement(
            instance_node, volume_node_name, device_name, resource_name
        )

        # Get resolved values specifically for metadata (always concrete values)
        if context:
            metadata_values = context.get_resolved_values(resource_data, "metadata")
        else:
            metadata_values = resource_data.get("values", {})

        logger.info(
            "Successfully added volume attachment: %s -> %s (device: %s)",
            instance_node_name,
            volume_node_name,
            metadata_values.get("device_name", device_name),
        )

    def _extract_references(
        self, resource_data: dict[str, Any], context: "TerraformMappingContext"
    ) -> tuple[str | None, str | None]:
        """Extract instance and volume references from the resource configuration.

        Args:
            resource_data: The resource data from Terraform plan
            context: TerraformMappingContext containing parsed data

        Returns:
            Tuple of (instance_address, volume_address) or (None, None) if not found
        """
        # Extract all Terraform references using context
        terraform_refs = context.extract_terraform_references(resource_data)

        instance_address = None
        volume_address = None

        # Process each reference to find instance and volume
        for prop_name, target_ref, _relationship_type in terraform_refs:
            if "." in target_ref:
                target_resource_type = target_ref.split(".", 1)[0]

                # Check for instance reference
                if (
                    prop_name == "instance_id"
                    and target_resource_type == "aws_instance"
                ):
                    instance_address = target_ref

                # Check for volume reference
                elif (
                    prop_name == "volume_id"
                    and target_resource_type == "aws_ebs_volume"
                ):
                    volume_address = target_ref

        logger.debug(
            "Extracted references - Instance: %s, Volume: %s",
            instance_address,
            volume_address,
        )

        return instance_address, volume_address

    def _find_node_in_builder(self, builder: "ServiceTemplateBuilder", node_name: str):
        """Find a node in the builder by name.

        Args:
            builder: The ServiceTemplateBuilder instance
            node_name: Name of the node to find

        Returns:
            The node object if found, None otherwise
        """
        try:
            # Use the new get_node method
            return builder.get_node(node_name)

        except Exception as e:
            logger.debug("Error while searching for node '%s': %s", node_name, e)
            return None

    def _add_volume_attachment_requirement(
        self, instance_node, volume_node_name: str, device_name: str, resource_name: str
    ) -> None:
        """Add local_storage requirement to the instance node.

        Args:
            instance_node: The instance node to modify
            volume_node_name: Name of the volume node to attach
            device_name: Device name for the attachment (e.g., '/dev/sdh')
            resource_name: Original resource name for logging
        """
        try:
            # Generate mount point from device name
            mount_point = self._generate_mount_point(device_name)

            # Add the local_storage requirement with relationship properties
            req_builder = (
                instance_node.add_requirement("local_storage")
                .to_node(volume_node_name)
                .with_relationship(
                    {
                        "type": "AttachesTo",
                        "properties": {"location": mount_point, "device": device_name},
                    }
                )
            )

            req_builder.and_node()

            logger.debug(
                "Added local_storage requirement: %s -> %s (device: %s, mount: %s)",
                instance_node.name if hasattr(instance_node, "name") else "unknown",
                volume_node_name,
                device_name,
                mount_point,
            )

        except Exception as e:
            logger.error(
                "Failed to add volume attachment requirement for '%s': %s",
                resource_name,
                e,
            )
            raise

    def _generate_mount_point(self, device_name: str) -> str:
        """Generate a logical mount point from a device name.

        Args:
            device_name: Device name like '/dev/sdh', '/dev/xvdf', etc.

        Returns:
            A mount point string based on the device name.
        """
        if not device_name:
            return "unspecified"

        # Extract the device suffix (e.g., 'sdh' from '/dev/sdh')
        if "/" in device_name:
            device_suffix = device_name.split("/")[-1]
        else:
            device_suffix = device_name

        # Generate a mount point based on the device suffix
        # For example: /dev/sdh -> /mnt/sdh
        mount_point = f"/mnt/{device_suffix}"

        logger.debug(
            "Generated mount point '%s' for device '%s'", mount_point, device_name
        )
        return mount_point
