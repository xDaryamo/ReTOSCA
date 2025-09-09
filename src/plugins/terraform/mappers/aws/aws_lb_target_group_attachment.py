import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper
from src.plugins.terraform.exceptions import (
    ResourceMappingError,
    ValidationError,
)

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class TargetGroupAttachmentError(ResourceMappingError):
    """Specific exception for target group attachment mapping errors."""

    pass


class AWSLBTargetGroupAttachmentMapper(SingleResourceMapper):
    """Map a Terraform 'aws_lb_target_group_attachment' resource to TOSCA relationships.

    This mapper doesn't create a separate node but instead modifies existing nodes
    to establish the attachment relationship between a Load Balancer Target Group
    and its targets (EC2 instances, IP addresses, Lambda functions, etc.).

    Args:
        resource_name: Name of the aws_lb_target_group_attachment resource
        resource_type: Type of the resource (always 'aws_lb_target_group_attachment')
        resource_data: Resource configuration data from Terraform plan
        builder: ServiceTemplateBuilder instance for TOSCA template construction
        context: TerraformMappingContext for dependency resolution and variable handling
    """

    # Target types that can be attached to target groups
    SUPPORTED_TARGET_TYPES = frozenset(
        [
            "aws_instance",
            "aws_lambda_function",
            "aws_lb",  # For target group chaining
        ]
    )

    # Required configuration fields
    REQUIRED_FIELDS = frozenset(["target_group_arn", "target_id"])

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_lb_target_group_attachment'."""
        return resource_type == "aws_lb_target_group_attachment"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Create attachment relationship between target group and target.

        This mapper doesn't create a new TOSCA node. Instead, it modifies the existing
        Target Group node to add a client requirement pointing to the target.

        Args:
            resource_name: Resource name (e.g. 'aws_lb_target_group_attachment.example')
            resource_type: Resource type (always 'aws_lb_target_group_attachment')
            resource_data: Resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for dependency resolution and
                variable handling
        """
        logger.info("Processing target group attachment resource: '%s'", resource_name)

        # Validate resource state before processing
        self._validate_resource_state(resource_data, resource_name)

        # Validate context availability
        if not context:
            raise TargetGroupAttachmentError(
                f"No context provided to resolve references for '{resource_name}'. "
                "Context is required for processing target group attachments."
            )

        # Get resolved values using the context for properties
        values = context.get_resolved_values(resource_data, "property")
        if not values:
            raise ValidationError(
                f"Resource '{resource_name}' has no 'values' section. "
                "Unable to process target group attachment."
            )

        # Validate configuration
        self._validate_attachment_config(values, resource_name)

        # Get port information if specified
        port = values.get("port")
        availability_zone = values.get("availability_zone")

        # Find target group and target references from configuration
        target_group_address, target_address = self._extract_references(
            resource_data, context
        )

        if not target_group_address or not target_address:
            # Provide more detailed error information for debugging
            available_values = list(values.keys()) if values else []
            logger.error(
                "Could not resolve target group or target references for '%s'. "
                "Available values: %s. This may be due to plan-only mode where "
                "computed values are not available.",
                resource_name,
                available_values,
            )
            raise TargetGroupAttachmentError(
                f"Could not resolve target group or target references for "
                f"'{resource_name}'. Target Group: {target_group_address}, "
                f"Target: {target_address}. In plan-only mode, ensure the "
                "configuration contains proper resource references for "
                "target_group_arn and target_id."
            )

        # Generate TOSCA node names
        # If address already looks like a TOSCA node name, use it directly
        if "." in target_group_address:
            target_group_node_name = BaseResourceMapper.generate_tosca_node_name(
                target_group_address, "aws_lb_target_group"
            )
        else:
            target_group_node_name = target_group_address  # Already TOSCA format

        if "." in target_address:
            # Determine target type to generate proper TOSCA name
            target_type = self._determine_target_type(target_address, context)
            target_node_name = BaseResourceMapper.generate_tosca_node_name(
                target_address, target_type
            )
        else:
            target_node_name = target_address  # Already TOSCA format

        # Find the target group node in the builder
        target_group_node = self._find_node_in_builder(builder, target_group_node_name)
        if not target_group_node:
            raise TargetGroupAttachmentError(
                f"Target group node '{target_group_node_name}' not found. "
                f"The aws_lb_target_group mapper may not have run yet for "
                f"'{resource_name}'. Ensure target group resources are "
                "processed before attachments."
            )

        # Check if target node exists
        target_node = self._find_node_in_builder(builder, target_node_name)
        if not target_node:
            raise TargetGroupAttachmentError(
                f"Target node '{target_node_name}' not found. "
                f"The target resource mapper may not have run yet for "
                f"'{resource_name}'. Ensure target resources are "
                "processed before attachments."
            )

        # Add the client requirement to the target group
        self._add_target_attachment_requirement(
            target_group_node, target_node_name, port, availability_zone, resource_name
        )

        # Get resolved values specifically for metadata (always concrete values)
        if context:
            metadata_values = context.get_resolved_values(resource_data, "metadata")
        else:
            metadata_values = resource_data.get("values", {})

        logger.info(
            "Successfully added target attachment: %s -> %s (port: %s)",
            target_group_node_name,
            target_node_name,
            metadata_values.get("port", port),
        )

    def _validate_attachment_config(
        self, values: dict[str, Any], resource_name: str
    ) -> None:
        """Validate target group attachment configuration.

        Args:
            values: Target group attachment configuration values
            resource_name: Resource name for error context

        Raises:
            ValidationError: If configuration is invalid
        """
        # In plan-only mode, target_group_arn and target_id may not be present
        # as they are computed values. We'll rely on configuration references
        # for validation in those cases.
        # Check if we have either direct values or if this is plan-only mode
        has_target_group_arn = "target_group_arn" in values
        has_target_id = "target_id" in values

        # If neither is present, this might be plan-only mode - validation
        # will be done in _extract_references based on configuration
        if not has_target_group_arn and not has_target_id:
            logger.debug(
                "No direct target_group_arn or target_id found for '%s' - "
                "assuming plan-only mode, will validate references from "
                "configuration",
                resource_name,
            )
        else:
            # If some fields are present, validate them
            missing_fields = self.REQUIRED_FIELDS - values.keys()
            if missing_fields:
                logger.debug(
                    "Some required fields missing for '%s': %s - "
                    "this is expected in plan-only mode",
                    resource_name,
                    missing_fields,
                )

        # Validate port if specified
        port = values.get("port")
        if port is not None:
            if not isinstance(port, int) or not (1 <= port <= 65535):
                raise ValidationError(
                    f"Invalid port '{port}' for '{resource_name}'. "
                    "Port must be an integer between 1 and 65535."
                )

        logger.debug("Configuration validation passed for '%s'", resource_name)

    def _extract_references(
        self, resource_data: dict[str, Any], context: "TerraformMappingContext"
    ) -> tuple[str | None, str | None]:
        """Extract target group and target references from the resource configuration.

        Args:
            resource_data: The resource data from Terraform plan
            context: TerraformMappingContext containing parsed data

        Returns:
            Tuple of (target_group_address, target_address) or (None, None) if not found
        """
        # First try to extract from Terraform references using context
        terraform_refs = context.extract_terraform_references(resource_data)

        target_group_address = None
        target_address = None

        # Process each reference to find target group and target
        for prop_name, target_ref, _relationship_type in terraform_refs:
            # Check for target group reference
            if prop_name == "target_group_arn":
                # Handle both terraform format (aws_lb_target_group.app) and
                # TOSCA format (aws_lb_target_group_app)
                if "." in target_ref and target_ref.startswith("aws_lb_target_group."):
                    target_group_address = target_ref  # Original terraform format
                elif target_ref.startswith("aws_lb_target_group_"):
                    target_group_address = target_ref  # Already resolved TOSCA format
                elif "." in target_ref:
                    target_resource_type = target_ref.split(".", 1)[0]
                    if target_resource_type == "aws_lb_target_group":
                        target_group_address = target_ref

            # Check for target reference
            elif prop_name == "target_id":
                # Handle different target types and formats
                if "." in target_ref:
                    # This is a resource reference like aws_instance.web
                    target_address = target_ref
                elif target_ref.startswith(("aws_instance_", "aws_lambda_function_")):
                    target_address = target_ref  # Already resolved TOSCA format
                else:
                    # This might be an IP address or other direct reference
                    # Try to find a resource with this ID
                    resolved_target = self._find_target_by_id(context, target_ref)
                    if resolved_target:
                        target_address = resolved_target

        # If we didn't find references using the standard method, try to extract
        # from configuration directly (for plan-only mode)
        if not target_group_address or not target_address:
            config_target_group, config_target = self._extract_from_configuration(
                resource_data, context
            )
            if not target_group_address:
                target_group_address = config_target_group
            if not target_address:
                target_address = config_target

        logger.debug(
            "Extracted references - Target Group: %s, Target: %s",
            target_group_address,
            target_address,
        )

        return target_group_address, target_address

    def _extract_from_configuration(
        self, resource_data: dict[str, Any], context: "TerraformMappingContext"
    ) -> tuple[str | None, str | None]:
        """Extract references directly from configuration (for plan-only mode).

        Args:
            resource_data: The resource data from Terraform plan
            context: TerraformMappingContext containing parsed data

        Returns:
            Tuple of (target_group_address, target_address) or (None, None) if not found
        """
        target_group_address = None
        target_address = None

        # Get the resource address to find it in configuration
        resource_address = resource_data.get("address")
        if not resource_address:
            return None, None

        # Look in the plan's configuration section
        parsed_data = context.parsed_data
        configuration = parsed_data.get("configuration", {})
        if not configuration:
            return None, None

        root_module = configuration.get("root_module", {})
        config_resources = root_module.get("resources", [])

        # Find our resource in configuration
        config_resource = None
        for config_res in config_resources:
            if config_res.get("address") == resource_address:
                config_resource = config_res
                break

        if not config_resource:
            return None, None

        # Extract references from expressions
        expressions = config_resource.get("expressions", {})

        # Look for target_group_arn expression
        target_group_arn_expr = expressions.get("target_group_arn", {})
        if target_group_arn_expr:
            references = target_group_arn_expr.get("references", [])
            for ref in references:
                if isinstance(ref, str) and "aws_lb_target_group." in ref:
                    # Extract the resource address (e.g., "aws_lb_target_group.test")
                    target_group_address = ref.split(".arn")[0]
                    break

        # Look for target_id expression
        target_id_expr = expressions.get("target_id", {})
        if target_id_expr:
            references = target_id_expr.get("references", [])
            for ref in references:
                if isinstance(ref, str) and (
                    "aws_instance." in ref or "aws_lambda_function." in ref
                ):
                    # Extract the resource address (e.g., "aws_instance.test")
                    target_address = ref.split(".id")[0]
                    break

        logger.debug(
            "Extracted from configuration - Target Group: %s, Target: %s",
            target_group_address,
            target_address,
        )

        return target_group_address, target_address

    def _find_target_by_id(
        self, context: "TerraformMappingContext", target_id: str
    ) -> str | None:
        """Find a target resource by its ID.

        Args:
            context: TerraformMappingContext containing parsed data
            target_id: Target ID to search for

        Returns:
            Target resource address if found, None otherwise
        """
        # Look in state data for resources with matching ID
        state_data = context.parsed_data.get("state", {})
        values = state_data.get("values", {})
        if values:
            root_module = values.get("root_module", {})
            resources = root_module.get("resources", [])

            for resource in resources:
                resource_type = resource.get("type")
                if resource_type in self.SUPPORTED_TARGET_TYPES:
                    if resource.get("values", {}).get("id") == target_id:
                        return resource.get("address")

        # Also check in planned_values (for plan JSON)
        planned_values = context.parsed_data.get("planned_values", {})
        if planned_values:
            root_module = planned_values.get("root_module", {})
            resources = root_module.get("resources", [])

            for resource in resources:
                resource_type = resource.get("type")
                if resource_type in self.SUPPORTED_TARGET_TYPES:
                    if resource.get("values", {}).get("id") == target_id:
                        return resource.get("address")

        logger.debug("Target resource with ID '%s' not found", target_id)
        return None

    def _determine_target_type(
        self, target_address: str, context: "TerraformMappingContext"
    ) -> str:
        """Determine the target resource type from the address.

        Args:
            target_address: Target resource address
            context: TerraformMappingContext for additional lookups

        Returns:
            Target resource type
        """
        if "." in target_address:
            return target_address.split(".", 1)[0]

        # If we can't determine from address, try to look it up
        # This is a fallback for edge cases
        return "aws_instance"  # Default assumption

    def _find_node_in_builder(
        self, builder: "ServiceTemplateBuilder", node_name: str
    ) -> Any | None:
        """Find a node in the builder by name.

        Args:
            builder: The ServiceTemplateBuilder instance
            node_name: Name of the node to find

        Returns:
            The node object if found, None otherwise
        """
        try:
            # Use the new get_node method
            return builder.get_node(node_name)

        except Exception as e:
            logger.debug("Error while searching for node '%s': %s", node_name, e)
            return None

    def _find_endpoint_capability(
        self, target_node_name: str, port: int | None, resource_name: str
    ) -> str | None:
        """Find the appropriate endpoint capability on the target node.

        Args:
            target_node_name: Name of the target node
            port: Port number to match (optional)
            resource_name: Original resource name for logging

        Returns:
            The endpoint capability name if found, None otherwise
        """
        if port is None:
            logger.debug(
                "No port specified for '%s', cannot find specific endpoint capability",
                resource_name,
            )
            return None

        # Use TOSCA-compliant endpoint capability names
        # Following TOSCA Simple Profile standards
        if port == 22:
            return "admin_endpoint"
        else:
            # Standard endpoint capability for application services
            return "endpoint"

    def _add_target_attachment_requirement(
        self,
        target_group_node,
        target_node_name: str,
        port: int | None,
        availability_zone: str | None,
        resource_name: str,
    ) -> None:
        """Add client requirement to the target group node.

        Args:
            target_group_node: The target group node to modify
            target_node_name: Name of the target node to attach
            port: Port number for the attachment (optional)
            availability_zone: Availability zone for IP targets (optional)
            resource_name: Original resource name for logging
        """
        try:
            # Build relationship properties (excluding port - it belongs in capability)
            relationship_properties: dict[str, Any] = {}
            if availability_zone:
                relationship_properties["availability_zone"] = availability_zone

            # Find the appropriate endpoint capability on the target node
            capability_name = self._find_endpoint_capability(
                target_node_name, port, resource_name
            )

            if capability_name:
                # Route to the specific endpoint capability
                # Build relationship configuration with properties if available
                relationship_config: dict[str, Any] = {"type": "RoutesTo"}
                if relationship_properties:
                    relationship_config["properties"] = relationship_properties

                req_builder = (
                    target_group_node.add_requirement("application")
                    .to_node(target_node_name)
                    .to_capability(capability_name)
                    .with_relationship(relationship_config)
                )

                req_builder.and_node()

                node_name = (
                    target_group_node.name
                    if hasattr(target_group_node, "name")
                    else "unknown"
                )
                logger.info(
                    "Added application requirement: %s -> %s.%s "
                    "(target port: %s, az: %s)",
                    node_name,
                    target_node_name,
                    capability_name,
                    port,
                    availability_zone,
                )
            else:
                # Fallback to routing to the node directly if no specific
                # capability found
                req_builder = (
                    target_group_node.add_requirement("application")
                    .to_node(target_node_name)
                    .with_relationship("RoutesTo")
                )

                if relationship_properties:
                    req_builder.with_properties(**relationship_properties)

                req_builder.and_node()

                node_name = (
                    target_group_node.name
                    if hasattr(target_group_node, "name")
                    else "unknown"
                )
                logger.debug(
                    "Added application requirement: %s -> %s (target port: %s, "
                    "az: %s) - no specific endpoint capability found",
                    node_name,
                    target_node_name,
                    port,
                    availability_zone,
                )

        except (AttributeError, KeyError, ValueError) as e:
            logger.error(
                "Failed to add target attachment requirement for '%s': %s",
                resource_name,
                e,
            )
            raise TargetGroupAttachmentError(
                f"Unable to create target attachment for '{resource_name}': {e}"
            ) from e
        except Exception as e:
            logger.error(
                "Unexpected error adding target attachment requirement for '%s': %s",
                resource_name,
                e,
            )
            raise

    def _validate_resource_state(
        self, resource_data: dict[str, Any], resource_name: str
    ) -> None:
        """Validate resource is in a processable state.

        Args:
            resource_data: Resource data from Terraform plan
            resource_name: Resource name for error context

        Raises:
            ValidationError: If resource is in an invalid state
        """
        if not resource_data:
            raise ValidationError(f"Empty resource data for '{resource_name}'")

        # Check if resource is marked for destruction
        mode = resource_data.get("mode")
        if mode == "destroy":
            raise ValidationError(
                f"Resource '{resource_name}' is marked for destruction and "
                "cannot be processed"
            )

        # Check for change actions that indicate problematic states
        change = resource_data.get("change", {})
        actions = change.get("actions", [])

        if "delete" in actions and "create" not in actions:
            logger.warning(
                "Resource '%s' is being deleted, skipping processing", resource_name
            )
            raise ValidationError(
                f"Resource '{resource_name}' is being deleted and cannot be processed"
            )
