import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.provisioning.terraform.context import TerraformMappingContext

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
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Perform translation from aws_s3_bucket to Storage.ObjectStorage.

        Args:
            resource_name: The name/identifier of the resource
            resource_type: The type/kind of resource (e.g., 'aws_s3_bucket')
            resource_data: The resource configuration data
            builder: The ServiceTemplateBuilder to populate with TOSCA resources
            context: TerraformMappingContext containing dependencies for reference
                extraction
        """
        logger.info(f"Mapping S3 Bucket resource: '{resource_name}'")

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

        # Create the ObjectStorage node
        bucket_node = builder.add_node(
            name=node_name,
            node_type="Storage.ObjectStorage",
        )

        # Extract AWS S3 Bucket properties and map them to TOSCA Storage properties

        # Bucket name
        bucket_name = values.get("bucket")

        # Map standard TOSCA Storage.ObjectStorage properties

        # Bucket name -> maps to the TOSCA 'name' property
        if bucket_name:
            bucket_node.with_property("name", bucket_name)

        # Get resolved values specifically for metadata (always concrete values)
        if context:
            metadata_values = context.get_resolved_values(resource_data, "metadata")
        else:
            metadata_values = resource_data.get("values", {})

        # Build metadata containing Terraform and AWS information
        metadata = {}

        # Original resource information
        metadata["original_resource_type"] = resource_type
        metadata["original_resource_name"] = clean_name

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # AWS S3 Bucket specific information - use metadata_values for concrete values
        metadata_region = metadata_values.get("region")
        if metadata_region:
            metadata["aws_region"] = metadata_region

        metadata_arn = metadata_values.get("arn")
        if metadata_arn:
            metadata["aws_arn"] = metadata_arn

        metadata_force_destroy = metadata_values.get("force_destroy")
        if metadata_force_destroy is not None:
            metadata["aws_force_destroy"] = metadata_force_destroy

        metadata_object_lock_enabled = metadata_values.get("object_lock_enabled")
        if metadata_object_lock_enabled is not None:
            metadata["aws_object_lock_enabled"] = metadata_object_lock_enabled

        # AWS S3 Bucket tags - use concrete metadata values
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        # Extract additional AWS info for extra metadata

        # Tags_all (all tags including provider defaults)
        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

        # Bucket domain name (populated after creation)
        metadata_bucket_domain_name = metadata_values.get("bucket_domain_name")
        if metadata_bucket_domain_name:
            metadata["aws_bucket_domain_name"] = metadata_bucket_domain_name

        # Bucket region (might differ from specified region)
        metadata_bucket_region = metadata_values.get("bucket_region")
        if metadata_bucket_region:
            metadata["aws_bucket_region"] = metadata_bucket_region

        # Bucket regional domain name (populated after creation)
        metadata_bucket_regional_domain_name = metadata_values.get(
            "bucket_regional_domain_name"
        )
        if metadata_bucket_regional_domain_name:
            metadata["aws_bucket_regional_domain_name"] = (
                metadata_bucket_regional_domain_name
            )

        # Hosted zone ID (populated after creation)
        metadata_hosted_zone_id = metadata_values.get("hosted_zone_id")
        if metadata_hosted_zone_id:
            metadata["aws_hosted_zone_id"] = metadata_hosted_zone_id

        # Bucket ID (usually same as bucket name, populated after creation)
        metadata_bucket_id = metadata_values.get("id")
        if metadata_bucket_id:
            metadata["aws_bucket_id"] = metadata_bucket_id

        # Deprecated/advanced: save anything not explicitly mapped
        for k, v in metadata_values.items():
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
                "id",
            ]:
                metadata[f"aws_{k}"] = v

        # Attach all metadata to the node
        bucket_node.with_metadata(metadata)

        # Add dependencies using injected context (S3 buckets rarely have dependencies)
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
                    target_resource_type = target_ref.split(".", 1)[0]
                    target_node_name = BaseResourceMapper.generate_tosca_node_name(
                        target_ref, target_resource_type
                    )

                    # Add requirement with the property name as the requirement name
                    requirement_name = (
                        prop_name if prop_name not in ["dependency"] else "dependency"
                    )

                    (
                        bucket_node.add_requirement(requirement_name)
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

        logger.debug(f"Storage.ObjectStorage node '{node_name}' created successfully.")

        # Log mapped properties for debugging
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Mapped properties for '{node_name}':")
            logger.debug(f"  - Bucket name: {bucket_name}")
            logger.debug(f"  - Region: {metadata_region}")
            logger.debug(f"  - Tags: {metadata_tags}")
            logger.debug(f"  - Force destroy: {metadata_force_destroy}")
            logger.debug(f"  - Object lock: {metadata_object_lock_enabled}")
