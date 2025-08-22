import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder

logger = logging.getLogger(__name__)


class AWSS3BucketMapper(SingleResourceMapper):
    """Map a Terraform 'aws_s3_bucket' resource to a TOSCA
    Storage.ObjectStorage node.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        return resource_type == "aws_s3_bucket"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
    ) -> None:
        logger.info(f"Mapping S3 Bucket resource: '{resource_name}'")

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

        # Create the ObjectStorage node
        bucket_node = builder.add_node(
            name=node_name,
            node_type="Storage.ObjectStorage",
        )

        # Standard TOSCA properties
        bucket_name = values.get("bucket")
        if bucket_name:
            bucket_node.with_property("name", bucket_name)

        # Metadata
        metadata = {}
        metadata["original_resource_type"] = resource_type
        metadata["original_resource_name"] = clean_name
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name
        region = values.get("region")
        if region:
            metadata["aws_region"] = region
        arn = values.get("arn")
        if arn:
            metadata["aws_arn"] = arn
        force_destroy = values.get("force_destroy")
        if force_destroy is not None:
            metadata["aws_force_destroy"] = force_destroy
        object_lock_enabled = values.get("object_lock_enabled")
        if object_lock_enabled is not None:
            metadata["aws_object_lock_enabled"] = object_lock_enabled
        tags = values.get("tags", {})
        if tags:
            metadata["aws_tags"] = tags
        tags_all = values.get("tags_all", {})
        if tags_all and tags_all != tags:
            metadata["aws_tags_all"] = tags_all
        bucket_domain_name = values.get("bucket_domain_name")
        if bucket_domain_name:
            metadata["aws_bucket_domain_name"] = bucket_domain_name
        bucket_region = values.get("bucket_region")
        if bucket_region:
            metadata["aws_bucket_region"] = bucket_region
        bucket_regional_domain_name = values.get("bucket_regional_domain_name")
        if bucket_regional_domain_name:
            metadata["aws_bucket_regional_domain_name"] = bucket_regional_domain_name
        hosted_zone_id = values.get("hosted_zone_id")
        if hosted_zone_id:
            metadata["aws_hosted_zone_id"] = hosted_zone_id

        # Deprecated/advanced: save anything not explicitly mapped
        for k, v in values.items():
            if k not in [
                "bucket",
                "region",
                "arn",
                "force_destroy",
                "object_lock_enabled",
                "tags",
                "tags_all",
                "bucket_domain_name",
                "bucket_region",
                "bucket_regional_domain_name",
                "hosted_zone_id",
            ]:
                metadata[f"aws_{k}"] = v

        bucket_node.with_metadata(metadata)

        logger.debug(f"Storage.ObjectStorage node '{node_name}' created successfully.")
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Mapped properties for '{node_name}':")
            logger.debug(f"  - Bucket name: {bucket_name}")
            logger.debug(f"  - Region: {region}")
            logger.debug(f"  - Tags: {tags}")
