import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.provisioning.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class TargetGroupDefaults:
    """Constants for AWS Load Balancer Target Group configuration."""

    NODE_TYPE = "LoadBalancer"
    DEFAULT_ALGORITHM = "round_robin"
    DEFAULT_PROTOCOL = "HTTP"
    DEFAULT_TARGET_TYPE = "instance"
    DEFAULT_IP_VERSION = 4
    DEFAULT_IP_ADDRESS_TYPE = "ipv4"
    SUPPORTED_PROTOCOLS = {"HTTP", "HTTPS", "TCP", "UDP", "TCP_UDP", "TLS"}
    MIN_PORT = 1
    MAX_PORT = 65535


class AWSLBTargetGroupMapper(SingleResourceMapper):
    """Map a Terraform 'aws_lb_target_group' resource to a TOSCA LoadBalancer node.

    A Load Balancer Target Group is a logical grouping of targets that route
    requests from a load balancer. It's mapped as a LoadBalancer node since it
    represents a load balancing function that distributes traffic to registered targets.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_lb_target_group'."""
        return resource_type == "aws_lb_target_group"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Translate an aws_lb_target_group into a TOSCA LoadBalancer node.

        Args:
            resource_name: resource name (e.g. 'aws_lb_target_group.app')
            resource_type: resource type (always 'aws_lb_target_group')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for variable resolution
        """
        logger.info("Mapping Load Balancer Target Group resource: '%s'", resource_name)

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

        # Generate a unique TOSCA node name using array-aware logic
        if context:
            node_name = context.generate_tosca_node_name_from_address(
                resource_name, resource_type
            )
        else:
            # Fallback to base mapper logic
            node_name = BaseResourceMapper.generate_tosca_node_name(
                resource_name, resource_type
            )

        # Extract the clean name for metadata (without the type prefix)
        if "." in resource_name:
            _, clean_name = resource_name.split(".", 1)
        else:
            clean_name = resource_name

        # Validate target group configuration
        if not self._validate_target_group_config(values, resource_name):
            logger.error(
                "Invalid target group configuration for '%s'. Skipping.", resource_name
            )
            return

        # Create the Target Group node as a LoadBalancer node
        target_group_node = builder.add_node(
            name=node_name, node_type=TargetGroupDefaults.NODE_TYPE
        )

        # Set LoadBalancer algorithm based on load balancing algorithm type
        algorithm = values.get(
            "load_balancing_algorithm_type", TargetGroupDefaults.DEFAULT_ALGORITHM
        )
        target_group_node.with_property("algorithm", algorithm)

        # Add the client capability for LoadBalancer nodes (public endpoint)
        client_capability = target_group_node.add_capability("client")

        # Configure the client endpoint properties
        port = values.get("port")
        if port is not None:
            client_capability.with_property("port", port)

        protocol = values.get("protocol", TargetGroupDefaults.DEFAULT_PROTOCOL).lower()
        client_capability.with_property("protocol", protocol)

        # Set secure property based on protocol
        is_secure = protocol in ["https", "tls"]
        client_capability.with_property("secure", is_secure)

        client_capability.and_node()

        # Get resolved values specifically for metadata (always concrete values)
        if context:
            metadata_values = context.get_resolved_values(resource_data, "metadata")
        else:
            metadata_values = resource_data.get("values", {})

        # Build comprehensive metadata
        metadata = self._build_metadata(
            resource_type, clean_name, resource_data, metadata_values
        )

        # Attach all metadata to the node
        target_group_node.with_metadata(metadata)

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

                # target_ref is now already resolved to TOSCA node name by context
                target_node_name = target_ref

                # For LoadBalancer nodes, we can add application requirements
                # that point to target instances/endpoints
                if prop_name in ["target_id", "target_group_attachment"]:
                    # This represents an application that the load balancer routes to
                    requirement_name = "application"
                    relationship_type = "RoutesTo"
                else:
                    # Use 'dependency' for all infrastructure dependencies
                    requirement_name = "dependency"

                (
                    target_group_node.add_requirement(requirement_name)
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

        logger.debug(
            "Target Group LoadBalancer node '%s' created successfully.", node_name
        )

        # Log mapped properties for debugging
        if logger.isEnabledFor(logging.DEBUG):
            self._log_mapped_properties(node_name, values, metadata_values)

    def _validate_target_group_config(
        self, values: dict[str, Any], resource_name: str
    ) -> bool:
        """Validate target group configuration for common issues.

        Args:
            values: Target group configuration values
            resource_name: Resource name for logging context

        Returns:
            True if configuration is valid, False otherwise
        """
        port = values.get("port")
        protocol = values.get("protocol", TargetGroupDefaults.DEFAULT_PROTOCOL)

        # Validate port range
        if port is not None and not (
            TargetGroupDefaults.MIN_PORT <= port <= TargetGroupDefaults.MAX_PORT
        ):
            logger.warning("Invalid port %s for target group '%s'", port, resource_name)
            return False

        # Validate protocol
        if protocol not in TargetGroupDefaults.SUPPORTED_PROTOCOLS:
            logger.warning(
                "Unsupported protocol '%s' for target group '%s'",
                protocol,
                resource_name,
            )
            return False

        return True

    def _build_metadata(
        self,
        resource_type: str,
        clean_name: str,
        resource_data: dict[str, Any],
        metadata_values: dict[str, Any],
    ) -> dict[str, Any]:
        """Build comprehensive metadata for the Target Group node."""
        metadata = self._build_base_metadata(resource_type, clean_name, resource_data)
        metadata.update(self._build_aws_core_metadata(metadata_values))
        metadata.update(self._build_aws_configuration_metadata(metadata_values))
        metadata.update(self._build_aws_operational_metadata(metadata_values))
        return metadata

    def _build_base_metadata(
        self, resource_type: str, clean_name: str, resource_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Build base metadata common to all target groups."""
        metadata: dict[str, Any] = {
            "original_resource_type": resource_type,
            "original_resource_name": clean_name,
            "aws_component_type": "TargetGroup",
            "description": (
                "AWS Load Balancer Target Group providing load balancing "
                "functionality to distribute traffic to registered targets"
            ),
        }

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        return metadata

    def _build_aws_core_metadata(
        self, metadata_values: dict[str, Any]
    ) -> dict[str, Any]:
        """Build core AWS-specific metadata for the target group."""
        # Define field mappings with defaults
        core_fields = {
            "name": ("aws_target_group_name", None),
            "port": ("aws_port", None),
            "protocol": ("aws_protocol", TargetGroupDefaults.DEFAULT_PROTOCOL),
            "vpc_id": ("aws_vpc_id", None),
            "target_type": ("aws_target_type", TargetGroupDefaults.DEFAULT_TARGET_TYPE),
            "region": ("aws_region", None),
            "arn": ("aws_target_group_arn", None),
            "id": ("aws_target_group_id", None),
        }

        metadata: dict[str, Any] = {}
        for source_key, (target_key, default) in core_fields.items():
            value = metadata_values.get(source_key, default)
            if value is not None:
                metadata[target_key] = value

        return metadata

    def _build_aws_configuration_metadata(
        self, metadata_values: dict[str, Any]
    ) -> dict[str, Any]:
        """Build AWS configuration-specific metadata."""
        config_fields: dict[str, tuple[str, Any]] = {
            "health_check": ("aws_health_check", []),
            "stickiness": ("aws_stickiness", []),
            "protocol_version": ("aws_protocol_version", None),
            "load_balancing_algorithm_type": (
                "aws_load_balancing_algorithm_type",
                None,
            ),
            "ip_address_type": ("aws_ip_address_type", None),
        }

        metadata: dict[str, Any] = {}
        for source_key, (target_key, default) in config_fields.items():
            value = metadata_values.get(source_key, default)
            # Only include non-empty collections and non-None values
            if value and (not isinstance(value, list | dict) or value):
                metadata[target_key] = value

        return metadata

    def _build_aws_operational_metadata(
        self, metadata_values: dict[str, Any]
    ) -> dict[str, Any]:
        """Build AWS operational metadata."""
        operational_fields = [
            ("connection_termination", "aws_connection_termination"),
            ("deregistration_delay", "aws_deregistration_delay"),
            (
                "lambda_multi_value_headers_enabled",
                "aws_lambda_multi_value_headers_enabled",
            ),
            ("preserve_client_ip", "aws_preserve_client_ip"),
            ("proxy_protocol_v2", "aws_proxy_protocol_v2"),
            ("slow_start", "aws_slow_start"),
        ]

        metadata: dict[str, Any] = {}
        for source_key, target_key in operational_fields:
            value = metadata_values.get(source_key)
            if value is not None:
                metadata[target_key] = value

        # Handle tags separately to check for differences
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

        return metadata

    def _log_mapped_properties(
        self, node_name: str, values: dict[str, Any], metadata_values: dict[str, Any]
    ) -> None:
        """Log mapped properties for debugging."""
        logger.debug("Mapped properties for '%s':", node_name)
        logger.debug("  - Name: %s", metadata_values.get("name", ""))
        logger.debug("  - Port: %s", metadata_values.get("port"))
        logger.debug(
            "  - Protocol: %s",
            metadata_values.get("protocol", TargetGroupDefaults.DEFAULT_PROTOCOL),
        )
        logger.debug("  - VPC ID: %s", metadata_values.get("vpc_id"))
        logger.debug(
            "  - Target Type: %s",
            metadata_values.get("target_type", TargetGroupDefaults.DEFAULT_TARGET_TYPE),
        )
        logger.debug("  - Tags: %s", metadata_values.get("tags", {}))
        logger.debug("  - Region: %s", metadata_values.get("region"))
