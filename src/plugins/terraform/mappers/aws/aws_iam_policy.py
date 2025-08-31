import json
import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSIAMPolicyMapper(SingleResourceMapper):
    """Map a Terraform 'aws_iam_policy' resource to a TOSCA SoftwareComponent node.

    IAM Policies are AWS security entities that define permissions and access rules.
    They are mapped as SoftwareComponent nodes with JSON policy artifacts and
    comprehensive metadata capturing all IAM-specific information.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_iam_policy'."""
        return resource_type == "aws_iam_policy"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Translate an aws_iam_policy resource into a TOSCA SoftwareComponent node.

        Args:
            resource_name: resource name (e.g. 'aws_iam_policy.policy')
            resource_type: resource type (always 'aws_iam_policy')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for variable resolution
        """
        logger.info("Mapping IAM Policy resource: '%s'", resource_name)

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

        # Generate a unique TOSCA node name using the utility function
        node_name = BaseResourceMapper.generate_tosca_node_name(
            resource_name, resource_type
        )

        # Extract the clean name for metadata (without the type prefix)
        if "." in resource_name:
            _, clean_name = resource_name.split(".", 1)
        else:
            clean_name = resource_name

        # Create the SoftwareComponent node for the IAM Policy
        policy_node = (
            builder.add_node(name=node_name, node_type="SoftwareComponent")
            .with_description("AWS IAM Policy defining permissions and access rules")
            .with_property("component_version", "1.0")
        )

        # Get resolved values specifically for metadata (always concrete values)
        if context:
            metadata_values = context.get_resolved_values(resource_data, "metadata")
        else:
            metadata_values = resource_data.get("values", {})

        # Build metadata with Terraform and AWS information
        metadata: dict[str, Any] = {}

        # Original resource information
        metadata["original_resource_type"] = resource_type
        metadata["original_resource_name"] = clean_name
        metadata["aws_component_type"] = "IAMPolicy"
        metadata["description"] = "AWS IAM Policy defining permissions and access rules"

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["terraform_provider"] = provider_name

        # Core IAM Policy properties - use metadata values for concrete resolution
        metadata_policy_name = metadata_values.get("name")
        if metadata_policy_name:
            metadata["aws_policy_name"] = metadata_policy_name

        # Policy document (required)
        policy_document = values.get("policy")
        metadata_policy_document = metadata_values.get("policy")
        if metadata_policy_document:
            # Format policy document for metadata (using YAML literal block format)
            formatted_policy = self._format_policy_for_yaml_literal(
                metadata_policy_document
            )
            metadata["aws_policy_document"] = formatted_policy

        # Add policy document as an artifact (use property value for processing)
        if policy_document:
            artifact_content = self._format_policy_for_artifact(policy_document)
            policy_node.add_artifact(
                "policy_document", "application/json", artifact_content
            ).and_node()

        # Optional properties - use metadata values for concrete resolution
        metadata_description = metadata_values.get("description")
        if metadata_description:
            metadata["aws_policy_description"] = metadata_description

        metadata_path = metadata_values.get("path")
        if metadata_path:
            metadata["aws_policy_path"] = metadata_path

        metadata_name_prefix = metadata_values.get("name_prefix")
        if metadata_name_prefix:
            metadata["aws_policy_name_prefix"] = metadata_name_prefix

        # Tags for the policy
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        # Additional AWS properties that might be available
        metadata_region = metadata_values.get("region")
        if metadata_region:
            metadata["aws_region"] = metadata_region

        # Set computed attributes if available
        metadata_arn = metadata_values.get("arn")
        if metadata_arn:
            metadata["aws_arn"] = metadata_arn

        metadata_policy_id = metadata_values.get("policy_id")
        if metadata_policy_id:
            metadata["aws_policy_id"] = metadata_policy_id

        metadata_attachment_count = metadata_values.get("attachment_count")
        if metadata_attachment_count is not None:
            metadata["aws_attachment_count"] = metadata_attachment_count

        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

        # Attach collected metadata to the node
        policy_node.with_metadata(metadata)

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
                    # target_ref is like "aws_iam_role.main"
                    target_resource_type = target_ref.split(".", 1)[0]
                    target_node_name = BaseResourceMapper.generate_tosca_node_name(
                        target_ref, target_resource_type
                    )

                    # Add requirement with the property name as the requirement name
                    requirement_name = (
                        prop_name if prop_name not in ["dependency"] else "dependency"
                    )

                    (
                        policy_node.add_requirement(requirement_name)
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

        logger.debug("IAM Policy node '%s' created successfully.", node_name)

        # Debug: mapped properties - use metadata values for concrete display
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Mapped properties for '%s':", node_name)
            logger.debug("  - Policy Name: %s", metadata_policy_name)
            logger.debug("  - Path: %s", metadata_path)
            logger.debug("  - Description: %s", metadata_description)
            logger.debug("  - ARN: %s", metadata_arn)
            logger.debug("  - Policy ID: %s", metadata_policy_id)
            logger.debug("  - Tags: %s", metadata_tags)

    def _format_policy_for_yaml_literal(self, policy_content: str | dict) -> dict:
        """Format policy content as a structured dict for YAML metadata."""
        try:
            if isinstance(policy_content, str):
                # Parse and return as dict
                return json.loads(policy_content)
            elif isinstance(policy_content, dict):
                return policy_content
            else:
                return {"policy": str(policy_content)}
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("Failed to format policy for YAML literal: %s", e)
            return {"policy": str(policy_content)}

    def _format_policy_for_metadata(self, policy_content: str | dict) -> str:
        """Format policy content for inclusion in metadata (pretty-printed JSON)."""
        try:
            if isinstance(policy_content, str):
                # Parse and re-serialize with pretty printing for readability
                parsed = json.loads(policy_content)
                return json.dumps(parsed, indent=2, sort_keys=True)
            elif isinstance(policy_content, dict):
                return json.dumps(policy_content, indent=2, sort_keys=True)
            else:
                return str(policy_content)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("Failed to format policy for metadata: %s", e)
            return str(policy_content)

    def _format_policy_for_artifact(self, policy_content: str | dict) -> str:
        """Format policy content for artifact (pretty-printed JSON)."""
        try:
            if isinstance(policy_content, str):
                # Parse and re-serialize with pretty printing
                parsed = json.loads(policy_content)
                return json.dumps(parsed, indent=2, sort_keys=True)
            elif isinstance(policy_content, dict):
                return json.dumps(policy_content, indent=2, sort_keys=True)
            else:
                return str(policy_content)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("Failed to format policy for artifact: %s", e)
            return str(policy_content)
