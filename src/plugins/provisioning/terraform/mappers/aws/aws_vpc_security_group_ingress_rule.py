import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.provisioning.terraform.context import TerraformMappingContext


logger = logging.getLogger(__name__)


class AWSVPCSecurityGroupIngressRuleMapper(SingleResourceMapper):
    """Map a Terraform 'aws_vpc_security_group_ingress_rule' resource.

    This mapper does not create a separate TOSCA node but modifies the
    existing aws_security_group node by adding ingress rule metadata.

    Args:
        resource_name: Name of the aws_vpc_security_group_ingress_rule resource
        resource_type: Type of the resource
            (always 'aws_vpc_security_group_ingress_rule')
        resource_data: Resource configuration data from Terraform plan
        builder: ServiceTemplateBuilder instance for TOSCA template construction
        context: TerraformMappingContext for dependency resolution and
            variable handling
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """
        This mapper is specific to the 'aws_vpc_security_group_ingress_rule' type.
        """
        return resource_type == "aws_vpc_security_group_ingress_rule"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """
        Map aws_vpc_security_group_ingress_rule by adding metadata to the
        related security group node.

        Args:
            resource_name: Resource name
                (e.g. 'aws_vpc_security_group_ingress_rule.allow_tls_ipv4')
            resource_type: Resource type
                (always 'aws_vpc_security_group_ingress_rule')
            resource_data: Resource data from the Terraform plan
            builder: Builder used to construct the TOSCA service template
            context: TerraformMappingContext for dependency resolution and
                variable handling
        """
        logger.info(f"Processing ingress rule resource: '{resource_name}'")

        # Check context availability
        if not context:
            logger.warning(
                f"No context provided for ingress rule '{resource_name}'. Skipping."
            )
            return

        # Extract security group reference and rule data
        sg_ref, rule_metadata = self._extract_rule_info(
            resource_name, resource_data, context
        )
        if not sg_ref or not rule_metadata:
            logger.warning(
                f"Could not extract rule information from '{resource_name}'. Skipping."
            )
            return

        # Find the security group node in the builder
        sg_node = self._find_security_group_node(sg_ref, builder)
        if not sg_node:
            logger.warning(
                f"Security group node not found for reference '{sg_ref}'. "
                f"Skipping rule '{resource_name}'."
            )
            return

        # Add the ingress rule to the security group metadata
        self._add_ingress_rule_to_node(sg_node, rule_metadata)
        logger.info(
            f"Successfully added ingress rule: {rule_metadata['rule_id']} "
            f"to security group {sg_ref}"
        )

    def _extract_rule_info(
        self,
        resource_name: str,
        resource_data: dict[str, Any],
        context: "TerraformMappingContext",
    ) -> tuple[str | None, dict[str, Any] | None]:
        """
        Extract security group reference and rule metadata from the resource data.

        Returns:
            Tuple of (security_group_reference, rule_metadata) or
            (None, None) if extraction fails
        """
        # Get resolved values using the context for properties
        if context:
            values = context.get_resolved_values(resource_data, "property")
        else:
            # Fallback to original values if no context available
            values = resource_data.get("values", {})

        if not values:
            logger.warning(f"Resource '{resource_name}' has no 'values' section.")
            return None, None

        # Extract clean rule name
        if "." in resource_name:
            _, rule_id = resource_name.split(".", 1)
        else:
            rule_id = resource_name

        # Extract Terraform references using context
        terraform_refs = context.extract_terraform_references(resource_data)

        # Look for security_group_id reference
        sg_ref = None
        for prop_name, target_ref, _relationship_type in terraform_refs:
            if prop_name == "security_group_id":
                sg_ref = target_ref
                break

        if not sg_ref:
            logger.warning(
                f"Could not find security group reference in '{resource_name}'"
            )
            return None, None

        # Build rule metadata
        rule_metadata = {
            "rule_id": rule_id,
            "from_port": values.get("from_port"),
            "to_port": values.get("to_port"),
            "protocol": values.get("ip_protocol"),
            "description": values.get("description"),
        }

        # Add CIDR blocks
        if values.get("cidr_ipv4"):
            rule_metadata["cidr_ipv4"] = values["cidr_ipv4"]
        if values.get("cidr_ipv6"):
            rule_metadata["cidr_ipv6"] = values["cidr_ipv6"]

        # Check for CIDR references in terraform refs
        for prop_name, target_ref, _relationship_type in terraform_refs:
            if prop_name == "cidr_ipv4":
                rule_metadata["cidr_ipv4_ref"] = target_ref
            elif prop_name == "cidr_ipv6":
                rule_metadata["cidr_ipv6_ref"] = target_ref

        # Other optional fields
        if values.get("prefix_list_id"):
            rule_metadata["prefix_list_id"] = values["prefix_list_id"]
        if values.get("referenced_security_group_id"):
            rule_metadata["referenced_security_group_id"] = values[
                "referenced_security_group_id"
            ]

        # ARN and rule ID from AWS
        if values.get("arn"):
            rule_metadata["arn"] = values["arn"]
        if values.get("security_group_rule_id"):
            rule_metadata["security_group_rule_id"] = values["security_group_rule_id"]

        # Tags
        tags = values.get("tags", {})
        if tags:
            rule_metadata["tags"] = tags

        tags_all = values.get("tags_all", {})
        if tags_all and tags_all != tags:
            rule_metadata["tags_all"] = tags_all

        return sg_ref, rule_metadata

    def _find_security_group_node(self, sg_ref: str, builder: "ServiceTemplateBuilder"):
        """
        Find the security group node in the builder based on the reference.

        Args:
            sg_ref: Security group reference - can be either terraform format
                    (e.g., "aws_security_group.allow_tls") or TOSCA node name
                    (e.g., "aws_security_group_allow_tls")
            builder: Service template builder

        Returns:
            The security group node or None if not found
        """
        # If sg_ref contains dots, it's a terraform reference that needs conversion
        if "." in sg_ref:
            # Extract resource type from reference
            resource_type = sg_ref.split(".", 1)[0]
            # Generate the expected TOSCA node name
            sg_node_name = BaseResourceMapper.generate_tosca_node_name(
                sg_ref, resource_type
            )
        else:
            # It's already a TOSCA node name
            sg_node_name = sg_ref

        # Try to get the node from the builder
        try:
            return builder.get_node(sg_node_name)
        except Exception as e:
            logger.debug(f"Failed to find security group node '{sg_node_name}': {e}")
            return None

    def _add_ingress_rule_to_node(self, sg_node, rule_metadata: dict[str, Any]) -> None:
        """
        Add the ingress rule metadata to the security group node.

        Args:
            sg_node: The security group node to modify
            rule_metadata: The rule metadata to add
        """
        # Get existing metadata from the node builder's internal data
        current_metadata = sg_node._data.get("metadata", {}).copy()

        # Initialize ingress_rules list if it doesn't exist
        if "ingress_rules" not in current_metadata:
            current_metadata["ingress_rules"] = []

        # Add the new rule
        current_metadata["ingress_rules"].append(rule_metadata)

        # Update the node metadata
        sg_node.with_metadata(current_metadata)

        logger.debug(
            f"Added ingress rule '{rule_metadata['rule_id']}' "
            f"to security group metadata"
        )
