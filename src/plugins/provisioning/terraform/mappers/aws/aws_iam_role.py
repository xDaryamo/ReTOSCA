import json
import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.provisioning.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSIAMRoleMapper(SingleResourceMapper):
    """Map a Terraform 'aws_iam_role' resource to a TOSCA SoftwareComponent node.

    IAM Roles are AWS security entities that define permissions for accessing
    AWS resources. They are mapped as SoftwareComponent nodes with JSON policy
    artifacts and comprehensive metadata capturing all IAM-specific information.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_iam_role'."""
        return resource_type == "aws_iam_role"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Translate an aws_iam_role resource into a TOSCA SoftwareComponent node.

        Args:
            resource_name: resource name (e.g. 'aws_iam_role.test_role')
            resource_type: resource type (always 'aws_iam_role')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for variable resolution
        """
        logger.info("Mapping IAM Role resource: '%s'", resource_name)

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

        # Create the SoftwareComponent node for the IAM Role
        role_node = (
            builder.add_node(name=node_name, node_type="SoftwareComponent")
            .with_description("AWS IAM Role defining permissions and access policies")
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
        metadata["aws_component_type"] = "IAMRole"
        metadata["description"] = (
            "AWS IAM Role defining permissions and access policies"
        )

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # Core IAM Role properties - use metadata values for concrete resolution
        metadata_role_name = metadata_values.get("name")
        if metadata_role_name:
            metadata["aws_role_name"] = metadata_role_name

        # Assume role policy (required)
        metadata_assume_role_policy = metadata_values.get("assume_role_policy")
        if metadata_assume_role_policy:
            # Store as parsed dictionary for better YAML readability
            parsed_policy = self._parse_policy_document(metadata_assume_role_policy)
            metadata["aws_assume_role_policy"] = parsed_policy

        # Optional properties - use metadata values for concrete resolution
        metadata_description = metadata_values.get("description")
        if metadata_description:
            metadata["aws_role_description"] = metadata_description

        metadata_path = metadata_values.get("path")
        if metadata_path:
            metadata["aws_role_path"] = metadata_path

        metadata_max_session_duration = metadata_values.get("max_session_duration")
        if metadata_max_session_duration:
            metadata["aws_max_session_duration"] = metadata_max_session_duration

        metadata_permissions_boundary = metadata_values.get("permissions_boundary")
        if metadata_permissions_boundary:
            metadata["aws_permissions_boundary"] = metadata_permissions_boundary

        metadata_force_detach_policies = metadata_values.get("force_detach_policies")
        if metadata_force_detach_policies is not None:
            metadata["aws_force_detach_policies"] = metadata_force_detach_policies

        # Handle inline policies (deprecated but still supported)
        metadata_inline_policies = metadata_values.get("inline_policy", [])
        if metadata_inline_policies:
            processed_inline_policies = []
            for policy in metadata_inline_policies:
                processed_policy = {}
                if policy.get("name"):
                    processed_policy["name"] = policy["name"]
                if policy.get("policy"):
                    processed_policy["policy"] = self._parse_policy_document(
                        policy["policy"]
                    )
                if processed_policy:
                    processed_inline_policies.append(processed_policy)
            if processed_inline_policies:
                metadata["aws_inline_policies"] = processed_inline_policies

        # Handle managed policy ARNs (deprecated but still supported)
        metadata_managed_policy_arns = metadata_values.get("managed_policy_arns", [])
        if metadata_managed_policy_arns:
            metadata["aws_managed_policy_arns"] = metadata_managed_policy_arns

        # Tags for the role
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        # Tags_all (all tags including provider defaults)
        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

        # Additional AWS properties that might be available
        metadata_region = metadata_values.get("region")
        if metadata_region:
            metadata["aws_region"] = metadata_region

        # Set computed attributes if available
        metadata_arn = metadata_values.get("arn")
        if metadata_arn:
            metadata["aws_arn"] = metadata_arn

        metadata_create_date = metadata_values.get("create_date")
        if metadata_create_date:
            metadata["aws_create_date"] = metadata_create_date

        metadata_unique_id = metadata_values.get("unique_id")
        if metadata_unique_id:
            metadata["aws_unique_id"] = metadata_unique_id

        # Attach collected metadata to the node
        role_node.with_metadata(metadata)

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
                    # target_ref is like "aws_iam_policy.main"
                    target_resource_type = target_ref.split(".", 1)[0]
                    target_node_name = BaseResourceMapper.generate_tosca_node_name(
                        target_ref, target_resource_type
                    )

                    # Add requirement with the property name as the requirement name
                    requirement_name = (
                        prop_name if prop_name not in ["dependency"] else "dependency"
                    )

                    (
                        role_node.add_requirement(requirement_name)
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

        logger.debug("IAM Role node '%s' created successfully.", node_name)

        # Debug: mapped properties - use metadata values for concrete display
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Mapped properties for '%s':", node_name)
            logger.debug("  - Role Name: %s", metadata_role_name)
            logger.debug("  - Path: %s", metadata_path)
            logger.debug("  - Max Session Duration: %s", metadata_max_session_duration)
            logger.debug("  - Inline Policies: %d", len(metadata_inline_policies))
            logger.debug(
                "  - Managed Policy ARNs: %d", len(metadata_managed_policy_arns)
            )
            logger.debug("  - Tags: %s", metadata_tags)

    def _format_policy_for_yaml_literal(self, policy_content: str | dict) -> str:
        """Format policy content for YAML literal block (|) syntax.

        Args:
            policy_content: Policy content as string or dict

        Returns:
            JSON string formatted with newlines suitable for YAML literal block
        """
        try:
            if isinstance(policy_content, str):
                # Parse and re-format for consistent formatting
                parsed = json.loads(policy_content)
                return json.dumps(parsed, indent=2)
            elif isinstance(policy_content, dict):
                return json.dumps(policy_content, indent=2)
            else:
                return str(policy_content)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(
                "Failed to format policy content as JSON: %s. Using original content.",
                e,
            )
            return str(policy_content)

    def _format_policy_for_metadata(self, policy_content: str | dict) -> str:
        """Format policy content as pretty-printed JSON string for metadata.

        Args:
            policy_content: Policy content as string or dict

        Returns:
            Pretty-formatted JSON string with proper indentation
        """
        try:
            if isinstance(policy_content, str):
                # Parse and re-format for consistent formatting
                parsed = json.loads(policy_content)
                return json.dumps(parsed, indent=2)
            elif isinstance(policy_content, dict):
                return json.dumps(policy_content, indent=2)
            else:
                return str(policy_content)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(
                "Failed to format policy content as JSON: %s. Using original content.",
                e,
            )
            return str(policy_content)

    def _format_policy_for_artifact(self, policy_content: str | dict) -> str:
        """Format policy content as pretty-printed JSON string for artifacts.

        Args:
            policy_content: Policy content as string or dict

        Returns:
            Pretty-formatted JSON string
        """
        try:
            if isinstance(policy_content, str):
                # Parse and re-format for consistent formatting
                parsed = json.loads(policy_content)
                return json.dumps(parsed, indent=2)
            elif isinstance(policy_content, dict):
                return json.dumps(policy_content, indent=2)
            else:
                return str(policy_content)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(
                "Failed to format policy content as JSON: %s. Using original content.",
                e,
            )
            return str(policy_content)

    def _parse_policy_document(self, policy_content: str) -> dict[str, Any] | str:
        """Parse a JSON policy document string into a dictionary.

        Args:
            policy_content: JSON string containing the policy document

        Returns:
            Parsed policy as dictionary, or original string if parsing fails
        """
        if not policy_content:
            return {}

        try:
            # Try to parse as JSON
            if isinstance(policy_content, str):
                return json.loads(policy_content)
            elif isinstance(policy_content, dict):
                return policy_content
            else:
                return str(policy_content)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(
                "Failed to parse policy document as JSON: %s. Storing as string.", e
            )
            return str(policy_content)
