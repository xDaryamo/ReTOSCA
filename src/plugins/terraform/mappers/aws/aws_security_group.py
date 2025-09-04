import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext


logger = logging.getLogger(__name__)


class AWSSecurityGroupMapper(SingleResourceMapper):
    """
    Map a Terraform 'aws_security_group' resource into a tosca.nodes.Root node.

    Because there is no standard TOSCA type for security groups in the simple
    profile, we use the Root type and store the relevant information in
    metadata.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """This mapper is specific to the 'aws_security_group' resource type."""
        return resource_type == "aws_security_group"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Perform translation from aws_security_group to tosca.nodes.Root.

        Args:
            resource_name: The name/identifier of the resource
            resource_type: The type/kind of resource (e.g., 'aws_security_group')
            resource_data: The resource configuration data
            builder: The ServiceTemplateBuilder to populate with TOSCA resources
            context: TerraformMappingContext containing dependencies for reference
                extraction
        """
        logger.info(f"Mapping Security Group resource: '{resource_name}'")

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

        # Generate a unique TOSCA node name using the utility function
        node_name = BaseResourceMapper.generate_tosca_node_name(
            resource_name, resource_type
        )

        # Extract the clean name for metadata (without the type prefix)
        if "." in resource_name:
            _, clean_name = resource_name.split(".", 1)
        else:
            clean_name = resource_name

        # Create the Root node to represent the security group
        sg_node = builder.add_node(name=node_name, node_type="Root")

        # Get resolved values specifically for metadata (always concrete values)
        if context:
            metadata_values = context.get_resolved_values(resource_data, "metadata")
        else:
            metadata_values = resource_data.get("values", {})

        # Build metadata containing Terraform and AWS information
        metadata: dict[str, Any] = {}

        # Original resource information
        metadata["original_resource_type"] = resource_type
        metadata["original_resource_name"] = clean_name

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # AWS Security Group information - use metadata_values for concrete values
        metadata_sg_name = metadata_values.get("name")
        if metadata_sg_name:
            metadata["aws_security_group_name"] = metadata_sg_name

        metadata_description = metadata_values.get("description")
        if metadata_description:
            metadata["aws_description"] = metadata_description

        metadata_vpc_id = metadata_values.get("vpc_id")
        if metadata_vpc_id:
            metadata["aws_vpc_id"] = metadata_vpc_id

        metadata_arn = metadata_values.get("arn")
        if metadata_arn:
            metadata["aws_arn"] = metadata_arn

        metadata_sg_id = metadata_values.get("id")
        if metadata_sg_id:
            metadata["aws_security_group_id"] = metadata_sg_id

        metadata_owner_id = metadata_values.get("owner_id")
        if metadata_owner_id:
            metadata["aws_owner_id"] = metadata_owner_id

        # Optional configurations - use metadata_values for concrete values
        metadata_revoke_rules_on_delete = metadata_values.get("revoke_rules_on_delete")
        if metadata_revoke_rules_on_delete is not None:
            metadata["aws_revoke_rules_on_delete"] = metadata_revoke_rules_on_delete

        metadata_name_prefix = metadata_values.get("name_prefix")
        if metadata_name_prefix:
            metadata["aws_name_prefix"] = metadata_name_prefix

        # AWS Security Group tags - use concrete metadata values
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        # Extract additional AWS info for extra metadata

        # Tags_all (all tags including provider defaults)
        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

        # === Security Group Rules ===

        # Process ingress rules from metadata values (concrete values)
        metadata_ingress_rules = metadata_values.get("ingress", [])
        if metadata_ingress_rules:
            processed_ingress = []
            for rule in metadata_ingress_rules:
                rule_data = {
                    "from_port": rule.get("from_port"),
                    "to_port": rule.get("to_port"),
                    "protocol": rule.get("protocol"),
                }

                # Add description if available
                if rule.get("description"):
                    rule_data["description"] = rule.get("description")

                # Add CIDR blocks if available
                if rule.get("cidr_blocks"):
                    rule_data["cidr_blocks"] = rule.get("cidr_blocks")

                # Add IPv6 CIDR blocks if available
                if rule.get("ipv6_cidr_blocks"):
                    rule_data["ipv6_cidr_blocks"] = rule.get("ipv6_cidr_blocks")

                # Add prefix list IDs if available
                if rule.get("prefix_list_ids"):
                    rule_data["prefix_list_ids"] = rule.get("prefix_list_ids")

                # Add security groups if available
                if rule.get("security_groups"):
                    rule_data["security_groups"] = rule.get("security_groups")

                # Add self reference if available
                if rule.get("self") is not None:
                    rule_data["self"] = rule.get("self")

                processed_ingress.append(rule_data)

            metadata["aws_ingress_rules"] = processed_ingress

        # Process egress rules from metadata values (concrete values)
        metadata_egress_rules = metadata_values.get("egress", [])
        if metadata_egress_rules:
            processed_egress = []
            for rule in metadata_egress_rules:
                rule_data = {
                    "from_port": rule.get("from_port"),
                    "to_port": rule.get("to_port"),
                    "protocol": rule.get("protocol"),
                }

                # Add description if available
                if rule.get("description"):
                    rule_data["description"] = rule.get("description")

                # Add CIDR blocks if available
                if rule.get("cidr_blocks"):
                    rule_data["cidr_blocks"] = rule.get("cidr_blocks")

                # Add IPv6 CIDR blocks if available
                if rule.get("ipv6_cidr_blocks"):
                    rule_data["ipv6_cidr_blocks"] = rule.get("ipv6_cidr_blocks")

                # Add prefix list IDs if available
                if rule.get("prefix_list_ids"):
                    rule_data["prefix_list_ids"] = rule.get("prefix_list_ids")

                # Add security groups if available
                if rule.get("security_groups"):
                    rule_data["security_groups"] = rule.get("security_groups")

                # Add self reference if available
                if rule.get("self") is not None:
                    rule_data["self"] = rule.get("self")

                processed_egress.append(rule_data)

            metadata["aws_egress_rules"] = processed_egress

        # Count rules for quick reference
        metadata["aws_ingress_rule_count"] = len(metadata_ingress_rules)
        metadata["aws_egress_rule_count"] = len(metadata_egress_rules)

        # Attach all metadata to the node
        sg_node.with_metadata(metadata)

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

                # Handle both Terraform format (aws_vpc.main) and
                # TOSCA format (aws_vpc_main)
                if "." in target_ref:
                    # target_ref is like "aws_vpc.main"
                    target_resource_type = target_ref.split(".", 1)[0]
                    target_node_name = BaseResourceMapper.generate_tosca_node_name(
                        target_ref, target_resource_type
                    )
                else:
                    # target_ref is already resolved to TOSCA node name
                    # (e.g., aws_vpc_main)
                    target_node_name = target_ref

                # Add requirement with the property name as the requirement name
                requirement_name = (
                    prop_name if prop_name not in ["dependency"] else "dependency"
                )

                (
                    sg_node.add_requirement(requirement_name)
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

        logger.debug(f"Root Security Group node '{node_name}' created successfully.")

        # Log mapped properties for debugging
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(f"Mapped properties for '{node_name}':")
            logger.debug(f"  - Name: {metadata_sg_name}")
            logger.debug(f"  - Description: {metadata_description}")
            logger.debug(f"  - VPC ID: {metadata_vpc_id}")
            logger.debug(f"  - Tags: {metadata_tags}")
            logger.debug(f"  - Ingress rules: {len(metadata_ingress_rules)}")
            logger.debug(f"  - Egress rules: {len(metadata_egress_rules)}")
