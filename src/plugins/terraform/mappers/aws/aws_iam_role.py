import inspect
import json
import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper
from src.plugins.terraform.mapper import TerraformMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder

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
    ) -> None:
        """Translate an aws_iam_role resource into a TOSCA SoftwareComponent node.

        Args:
            resource_name: resource name (e.g. 'aws_iam_role.test_role')
            resource_type: resource type (always 'aws_iam_role')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
        """
        logger.info("Mapping IAM Role resource: '%s'", resource_name)

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

        # Create the SoftwareComponent node for the IAM Role
        role_node = (
            builder.add_node(name=node_name, node_type="SoftwareComponent")
            .with_description("AWS IAM Role defining permissions and access policies")
            .with_property("component_version", "1.0")
        )

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

        # Core IAM Role properties
        role_name = values.get("name")
        if role_name:
            metadata["aws_role_name"] = role_name

        # Assume role policy (required)
        assume_role_policy = values.get("assume_role_policy")
        if assume_role_policy:
            # Store as parsed dictionary for better YAML readability
            parsed_policy = self._parse_policy_document(assume_role_policy)
            metadata["aws_assume_role_policy"] = parsed_policy

        # Optional properties
        description = values.get("description")
        if description:
            metadata["aws_role_description"] = description

        path = values.get("path")
        if path:
            metadata["aws_role_path"] = path

        max_session_duration = values.get("max_session_duration")
        if max_session_duration:
            metadata["aws_max_session_duration"] = max_session_duration

        permissions_boundary = values.get("permissions_boundary")
        if permissions_boundary:
            metadata["aws_permissions_boundary"] = permissions_boundary

        force_detach_policies = values.get("force_detach_policies")
        if force_detach_policies is not None:
            metadata["aws_force_detach_policies"] = force_detach_policies

        # Handle inline policies (deprecated but still supported)
        inline_policies = values.get("inline_policy", [])
        if inline_policies:
            processed_inline_policies = []
            for policy in inline_policies:
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
        managed_policy_arns = values.get("managed_policy_arns", [])
        if managed_policy_arns:
            metadata["aws_managed_policy_arns"] = managed_policy_arns

        # Tags for the role
        tags = values.get("tags", {})
        if tags:
            metadata["aws_tags"] = tags

        # Tags_all (all tags including provider defaults)
        tags_all = values.get("tags_all", {})
        if tags_all and tags_all != tags:
            metadata["aws_tags_all"] = tags_all

        # Additional AWS properties that might be available
        region = values.get("region")
        if region:
            metadata["aws_region"] = region

        # Set computed attributes if available
        arn = values.get("arn")
        if arn:
            metadata["aws_arn"] = arn

        create_date = values.get("create_date")
        if create_date:
            metadata["aws_create_date"] = create_date

        unique_id = values.get("unique_id")
        if unique_id:
            metadata["aws_unique_id"] = unique_id

        # Attach collected metadata to the node
        role_node.with_metadata(metadata)

        # Detect dependencies (IAM roles typically don't have explicit dependencies
        # in the plan, but we check anyway)
        self._add_dependencies(role_node, resource_data, node_name)

        logger.debug("IAM Role node '%s' created successfully.", node_name)

        # Debug: mapped properties
        logger.debug(
            "Mapped properties for '%s':\n"
            "  - Role Name: %s\n"
            "  - Path: %s\n"
            "  - Max Session Duration: %s\n"
            "  - Inline Policies: %d\n"
            "  - Managed Policy ARNs: %d\n"
            "  - Tags: %s",
            node_name,
            role_name,
            path,
            max_session_duration,
            len(inline_policies),
            len(managed_policy_arns),
            tags,
        )

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
                "Failed to format policy content as JSON: %s. "
                "Using original content.",
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
                "Failed to format policy content as JSON: %s. "
                "Using original content.",
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
                "Failed to format policy content as JSON: %s. "
                "Using original content.",
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
                "Failed to parse policy document as JSON: %s. " "Storing as string.", e
            )
            return str(policy_content)

    def _add_dependencies(
        self,
        role_node,
        resource_data: dict[str, Any],
        node_name: str,
    ) -> None:
        """Add dependency relationships for IAM Role.

        IAM Roles typically don't have explicit dependencies in Terraform plans,
        but we check for any references just in case.
        """
        # Access the full plan via the TerraformMapper instance found on the call stack
        parsed_data: dict[str, Any] = {}
        for frame_info in inspect.stack():
            frame_locals = frame_info.frame.f_locals
            if "self" in frame_locals and isinstance(
                frame_locals["self"], TerraformMapper
            ):
                terraform_mapper = frame_locals["self"]
                parsed_data = terraform_mapper.get_current_parsed_data()
                break
        else:
            logger.debug(
                "No TerraformMapper found on stack for IAM Role '%s'. "
                "No dependencies will be added.",
                node_name,
            )
            return

        dependencies_added = set()

        if parsed_data:
            # Find any dependencies using the Terraform reference system
            terraform_refs = TerraformMapper.extract_terraform_references(
                resource_data, parsed_data
            )

            for _prop_name, target_ref, relationship_type in terraform_refs:
                if target_ref not in dependencies_added:
                    if "." in target_ref:
                        # target_ref is like "aws_iam_policy.example"
                        target_resource_type = target_ref.split(".", 1)[0]
                        target_node_name = BaseResourceMapper.generate_tosca_node_name(
                            target_ref, target_resource_type
                        )

                        # Add appropriate relationship
                        if relationship_type == "tosca.DependsOn":
                            role_node.add_requirement("dependency").to_node(
                                target_node_name
                            ).with_relationship("DependsOn").and_node()
                        else:
                            # Default to DependsOn for IAM resources
                            role_node.add_requirement("dependency").to_node(
                                target_node_name
                            ).with_relationship("DependsOn").and_node()

                        dependencies_added.add(target_ref)
                        logger.info(
                            "Added dependency %s from '%s' to '%s'",
                            relationship_type,
                            node_name,
                            target_node_name,
                        )
