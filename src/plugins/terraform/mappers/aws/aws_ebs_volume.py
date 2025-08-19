import logging
from typing import TYPE_CHECKING, Any

from core.common.base_mapper import BaseResourceMapper
from core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder

logger = logging.getLogger(__name__)


class AWSEBSVolumeMapper(SingleResourceMapper):
    """Map a Terraform 'aws_ebs_volume' resource into a
    tosca.nodes.Storage.BlockStorage node.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        return resource_type == "aws_ebs_volume"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
    ) -> None:
        logger.info(f"Mapping EBS Volume resource: '{resource_name}'")

        values = resource_data.get("values", {})
        if not values:
            logger.warning(
                f"Resource '{resource_name}' has no 'values' section. Skipping."
            )
            return

        node_name = BaseResourceMapper.generate_tosca_node_name(
            resource_name, resource_type
        )
        if "." in resource_name:
            _, clean_name = resource_name.split(".", 1)
        else:
            clean_name = resource_name

        # Create the BlockStorage node
        volume_node = builder.add_node(name=node_name, node_type="Storage.BlockStorage")

        # === Standard TOSCA properties ===

        # Volume size (standard TOSCA property)
        size = values.get("size")
        if size:
            # Convert from GiB to GB for TOSCA compliance (string representation)
            volume_node.with_property("size", f"{size} GB")

        # Volume ID (if available, typically after creation)
        volume_id = values.get("id")
        if volume_id:
            volume_node.with_property("volume_id", volume_id)

        # Snapshot ID (if the volume is based on a snapshot)
        snapshot_id = values.get("snapshot_id")
        if snapshot_id:
            volume_node.with_property("snapshot_id", snapshot_id)

        # === Metadata with AWS-specific information ===
        metadata: dict[str, Any] = {}
        metadata["original_resource_type"] = resource_type
        metadata["original_resource_name"] = clean_name

        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # Placement information
        availability_zone = values.get("availability_zone")
        if availability_zone:
            metadata["aws_availability_zone"] = availability_zone

        region = values.get("region")
        if region:
            metadata["aws_region"] = region

        # Encryption information
        encrypted = values.get("encrypted")
        if encrypted is not None:
            metadata["aws_encrypted"] = encrypted

        kms_key_id = values.get("kms_key_id")
        if kms_key_id:
            metadata["aws_kms_key_id"] = kms_key_id

        # EBS volume type
        volume_type = values.get("type")
        if volume_type:
            metadata["aws_volume_type"] = volume_type

        # Performance settings
        iops = values.get("iops")
        if iops:
            metadata["aws_iops"] = iops

        throughput = values.get("throughput")
        if throughput:
            metadata["aws_throughput"] = throughput

        # Multi-attach capability
        multi_attach_enabled = values.get("multi_attach_enabled")
        if multi_attach_enabled is not None:
            metadata["aws_multi_attach_enabled"] = multi_attach_enabled

        # Outpost deployment
        outpost_arn = values.get("outpost_arn")
        if outpost_arn:
            metadata["aws_outpost_arn"] = outpost_arn

        # Snapshot configuration
        final_snapshot = values.get("final_snapshot")
        if final_snapshot is not None:
            metadata["aws_final_snapshot"] = final_snapshot

        # Volume initialization rate
        volume_initialization_rate = values.get("volume_initialization_rate")
        if volume_initialization_rate:
            metadata["aws_volume_initialization_rate"] = volume_initialization_rate

        # Volume ARN
        arn = values.get("arn")
        if arn:
            metadata["aws_arn"] = arn

        # Creation timestamp
        create_time = values.get("create_time")
        if create_time:
            metadata["aws_create_time"] = create_time

        # Tags
        tags = values.get("tags", {})
        if tags:
            metadata["aws_tags"] = tags

        tags_all = values.get("tags_all", {})
        if tags_all:
            metadata["aws_tags_all"] = tags_all

        # Attach all metadata to the node
        volume_node.with_metadata(metadata)

        # Add the 'attachment' capability to allow attaching to compute nodes
        volume_node.add_capability("attachment").and_node()

        logger.debug(f"Storage.BlockStorage node '{node_name}' created successfully.")

        # Log mapped properties for debugging
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Mapped properties for '{node_name}':")
            logger.debug(f"  - Size: {size} GiB")
            logger.debug(f"  - Availability Zone: {availability_zone}")
            logger.debug(f"  - Volume Type: {volume_type}")
            logger.debug(f"  - Encrypted: {encrypted}")
            logger.debug(f"  - IOPS: {iops}")
            logger.debug(f"  - Throughput: {throughput}")
            logger.debug(f"  - Tags: {tags}")
