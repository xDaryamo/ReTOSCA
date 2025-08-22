import json
import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder

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
    ) -> None:
        """Translate an aws_iam_policy resource into a TOSCA SoftwareComponent node.

        Args:
            resource_name: resource name (e.g. 'aws_iam_policy.policy')
            resource_type: resource type (always 'aws_iam_policy')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
        """
        logger.info("Mapping IAM Policy resource: '%s'", resource_name)

        # Validate input data
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

        # Core IAM Policy properties
        policy_name = values.get("name")
        if policy_name:
            metadata["aws_policy_name"] = policy_name

        # Policy document (required)
        policy_document = values.get("policy")
        if policy_document:
            # Format policy document for metadata (using YAML literal block format)
            formatted_policy = self._format_policy_for_yaml_literal(policy_document)
            metadata["aws_policy_document"] = formatted_policy

            # Add policy document as an artifact
            artifact_content = self._format_policy_for_artifact(policy_document)
            policy_node.add_artifact(
                "policy_document", "application/json", artifact_content
            ).and_node()

        # Optional properties
        description = values.get("description")
        if description:
            metadata["aws_policy_description"] = description

        path = values.get("path")
        if path:
            metadata["aws_policy_path"] = path

        name_prefix = values.get("name_prefix")
        if name_prefix:
            metadata["aws_policy_name_prefix"] = name_prefix

        # Tags for the policy
        tags = values.get("tags", {})
        if tags:
            metadata["aws_tags"] = tags

        # Additional AWS properties that might be available
        region = values.get("region")
        if region:
            metadata["aws_region"] = region

        # Set computed attributes if available
        arn = values.get("arn")
        if arn:
            metadata["aws_arn"] = arn

        policy_id = values.get("policy_id")
        if policy_id:
            metadata["aws_policy_id"] = policy_id

        attachment_count = values.get("attachment_count")
        if attachment_count is not None:
            metadata["aws_attachment_count"] = attachment_count

        tags_all = values.get("tags_all", {})
        if tags_all and tags_all != tags:
            metadata["aws_tags_all"] = tags_all

        # Attach collected metadata to the node
        policy_node.with_metadata(metadata)

        # IAM policies typically don't have explicit dependencies in the plan,
        # but we check anyway
        self._add_dependencies(policy_node, resource_data, node_name)

        logger.debug("IAM Policy node '%s' created successfully.", node_name)

        # Debug: mapped properties
        logger.debug(
            "Mapped properties for '%s':\n"
            "  - Policy Name: %s\n"
            "  - Path: %s\n"
            "  - Description: %s\n"
            "  - ARN: %s\n"
            "  - Policy ID: %s\n"
            "  - Tags: %s",
            node_name,
            policy_name,
            path,
            description,
            arn,
            policy_id,
            tags,
        )

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

    def _add_dependencies(
        self,
        policy_node,
        resource_data: dict[str, Any],
        node_name: str,
    ) -> None:
        """Add dependency relationships if any are detected.

        IAM policies typically don't have explicit dependencies in Terraform plans,
        but this method is included for completeness and future extensions.
        """
        # Currently, aws_iam_policy resources typically don't reference other
        # resources directly in their configuration. Dependencies are usually
        # established when policies are attached to roles, users, or groups.

        # We could potentially add logic here to detect references to:
        # - IAM roles, users, or groups (if policy attachments are inline)
        # - Other AWS resources mentioned in the policy document itself

        # For now, we'll just log that we're checking for dependencies
        logger.debug(
            "Checking for dependencies for IAM Policy '%s' - "
            "typically none expected for standalone policies",
            node_name,
        )
