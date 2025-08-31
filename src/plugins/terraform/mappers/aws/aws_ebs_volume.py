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

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        return resource_type == "aws_ebs_volume"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        logger.info(f"Mapping EBS Volume resource: '{resource_name}'")

        # Get resolved values using the context for properties
        if context:
            values = context.get_resolved_values(resource_data, "property")
        else:
            # Fallback to original values if no context available
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

        # Get resolved values specifically for metadata (always concrete values)
        if context:
            metadata_values = context.get_resolved_values(resource_data, "metadata")
        else:
            metadata_values = resource_data.get("values", {})

        # === Metadata with AWS-specific information ===
        metadata: dict[str, Any] = {}
        metadata["original_resource_type"] = resource_type
        metadata["original_resource_name"] = clean_name

        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # Placement information - use metadata values for concrete resolution
        metadata_availability_zone = metadata_values.get("availability_zone")
        if metadata_availability_zone:
            metadata["aws_availability_zone"] = metadata_availability_zone

        metadata_region = metadata_values.get("region")
        if metadata_region:
            metadata["aws_region"] = metadata_region

        # Encryption information
        metadata_encrypted = metadata_values.get("encrypted")
        if metadata_encrypted is not None:
            metadata["aws_encrypted"] = metadata_encrypted

        metadata_kms_key_id = metadata_values.get("kms_key_id")
        if metadata_kms_key_id:
            metadata["aws_kms_key_id"] = metadata_kms_key_id

        # EBS volume type
        metadata_volume_type = metadata_values.get("type")
        if metadata_volume_type:
            metadata["aws_volume_type"] = metadata_volume_type

        # Performance settings
        metadata_iops = metadata_values.get("iops")
        if metadata_iops:
            metadata["aws_iops"] = metadata_iops

        metadata_throughput = metadata_values.get("throughput")
        if metadata_throughput:
            metadata["aws_throughput"] = metadata_throughput

        # Multi-attach capability
        metadata_multi_attach_enabled = metadata_values.get("multi_attach_enabled")
        if metadata_multi_attach_enabled is not None:
            metadata["aws_multi_attach_enabled"] = metadata_multi_attach_enabled

        # Outpost deployment
        metadata_outpost_arn = metadata_values.get("outpost_arn")
        if metadata_outpost_arn:
            metadata["aws_outpost_arn"] = metadata_outpost_arn

        # Snapshot configuration
        metadata_final_snapshot = metadata_values.get("final_snapshot")
        if metadata_final_snapshot is not None:
            metadata["aws_final_snapshot"] = metadata_final_snapshot

        # Volume initialization rate
        metadata_volume_initialization_rate = metadata_values.get(
            "volume_initialization_rate"
        )
        if metadata_volume_initialization_rate:
            metadata["aws_volume_initialization_rate"] = (
                metadata_volume_initialization_rate
            )

        # Volume ARN
        metadata_arn = metadata_values.get("arn")
        if metadata_arn:
            metadata["aws_arn"] = metadata_arn

        # Creation timestamp
        metadata_create_time = metadata_values.get("create_time")
        if metadata_create_time:
            metadata["aws_create_time"] = metadata_create_time

        # Tags
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

        # Attach all metadata to the node
        volume_node.with_metadata(metadata)

        # Add the 'attachment' capability to allow attaching to compute nodes
        volume_node.add_capability("attachment").and_node()

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
                    # target_ref is like "aws_kms_key.main"
                    target_resource_type = target_ref.split(".", 1)[0]
                    target_node_name = BaseResourceMapper.generate_tosca_node_name(
                        target_ref, target_resource_type
                    )

                    # Add requirement with the property name as the requirement name
                    requirement_name = (
                        prop_name if prop_name not in ["dependency"] else "dependency"
                    )

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
        else:
            logger.warning(
                "No context provided to detect dependencies for resource '%s'",
                resource_name,
            )

        logger.debug(f"Storage.BlockStorage node '{node_name}' created successfully.")

        # Log mapped properties for debugging - use metadata values for concrete display
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Mapped properties for '{node_name}':")
            logger.debug(f"  - Size: {size} GiB")
            logger.debug(f"  - Availability Zone: {metadata_availability_zone}")
            logger.debug(f"  - Volume Type: {metadata_volume_type}")
            logger.debug(f"  - Encrypted: {metadata_encrypted}")
            logger.debug(f"  - IOPS: {metadata_iops}")
            logger.debug(f"  - Throughput: {metadata_throughput}")
            logger.debug(f"  - Tags: {metadata_tags}")
