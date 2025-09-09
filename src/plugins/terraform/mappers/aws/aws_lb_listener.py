import logging
from typing import TYPE_CHECKING, Any

from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class ListenerDefaults:
    """Constants for AWS Load Balancer Listener configuration."""

    NODE_TYPE = "Endpoint"
    DEFAULT_PROTOCOL = "HTTP"
    MIN_PORT = 1
    MAX_PORT = 65535
    SUPPORTED_PROTOCOLS = frozenset(
        {"HTTP", "HTTPS", "TCP", "TLS", "UDP", "TCP_UDP", "GENEVE"}
    )
    SECURE_PROTOCOLS = frozenset({"HTTPS", "TLS"})


class RequirementTypes:
    """Constants for requirement names."""

    HOST = "host"
    DEPENDENCY = "dependency"


class AWSLBListenerMapper(SingleResourceMapper):
    """Map a Terraform 'aws_lb_listener' resource to a TOSCA Endpoint node.

    A Load Balancer Listener is a process that checks for connection requests
    using the protocol and port that you configure. It's mapped as an Endpoint
    node since it represents a communication endpoint.
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for resource type 'aws_lb_listener'."""
        return resource_type == "aws_lb_listener"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Translate an aws_lb_listener into a TOSCA Endpoint node.

        Note: As of Simple Profile implementation, listeners are now integrated
        into the LoadBalancer node's client capability properties instead of
        being separate nodes. This mapper is kept for backwards compatibility
        but is effectively a no-op.

        Args:
            resource_name: resource name (e.g. 'aws_lb_listener.front_end')
            resource_type: resource type (always 'aws_lb_listener')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for variable resolution
        """
        logger.info(
            "Skipping AWS Load Balancer Listener resource: '%s' - "
            "Listener configuration is now integrated into the LoadBalancer node's "
            "client capability properties according to Simple Profile",
            resource_name,
        )
        # No-op: listeners are now handled by the AWSLoadBalancerMapper
        return

    def _validate_listener_config(
        self, values: dict[str, Any], resource_name: str
    ) -> bool:
        """Validate listener configuration for common issues.

        Args:
            values: Listener configuration values
            resource_name: Resource name for logging context

        Returns:
            True if configuration is valid, False otherwise
        """
        port = values.get("port")
        protocol = values.get("protocol", ListenerDefaults.DEFAULT_PROTOCOL)

        # Validate port range
        if port is not None and not (
            ListenerDefaults.MIN_PORT <= port <= ListenerDefaults.MAX_PORT
        ):
            logger.warning("Invalid port %s for listener '%s'", port, resource_name)
            return False

        # Validate protocol
        if protocol not in ListenerDefaults.SUPPORTED_PROTOCOLS:
            logger.warning(
                "Unsupported protocol '%s' for listener '%s'", protocol, resource_name
            )
            return False

        # Validate HTTPS/TLS specific requirements
        if protocol in ListenerDefaults.SECURE_PROTOCOLS:
            ssl_policy = values.get("ssl_policy")
            certificate_arn = values.get("certificate_arn")
            if not ssl_policy and not certificate_arn:
                logger.warning(
                    "HTTPS/TLS listener '%s' should specify ssl_policy "
                    "or certificate_arn",
                    resource_name,
                )
                # This is a warning, not an error - some configurations might be valid

        return True

    def _map_protocol_to_tosca(self, aws_protocol: str) -> str:
        """Map AWS listener protocol to TOSCA endpoint protocol.

        Args:
            aws_protocol: AWS listener protocol

        Returns:
            TOSCA-compatible protocol name
        """
        protocol_mapping = {
            "HTTP": "http",
            "HTTPS": "https",
            "TCP": "tcp",
            "TLS": "tcp",  # TLS over TCP
            "UDP": "udp",
            "TCP_UDP": "tcp",  # Primary protocol
            # GENEVE typically over UDP but represents as TCP for simplicity
            "GENEVE": "tcp",
        }

        return protocol_mapping.get(aws_protocol.upper(), aws_protocol.lower())

    def _build_metadata(
        self,
        resource_type: str,
        clean_name: str,
        resource_data: dict[str, Any],
        metadata_values: dict[str, Any],
    ) -> dict[str, Any]:
        """Build comprehensive metadata for the Listener node."""
        metadata: dict[str, Any] = {}

        # Build all metadata in a single pass for better performance
        self._populate_base_metadata(metadata, resource_type, clean_name, resource_data)
        self._populate_aws_core_metadata(metadata, metadata_values)
        self._populate_aws_configuration_metadata(metadata, metadata_values)
        self._populate_aws_operational_metadata(metadata, metadata_values)

        return metadata

    def _populate_base_metadata(
        self,
        metadata: dict[str, Any],
        resource_type: str,
        clean_name: str,
        resource_data: dict[str, Any],
    ) -> None:
        """Populate base metadata common to all listeners."""
        metadata.update(
            {
                "original_resource_type": resource_type,
                "original_resource_name": clean_name,
                "aws_component_type": "LoadBalancerListener",
                "description": (
                    "AWS Load Balancer Listener that checks for connection requests "
                    "and routes them to targets"
                ),
            }
        )

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

    def _populate_aws_core_metadata(
        self, metadata: dict[str, Any], metadata_values: dict[str, Any]
    ) -> None:
        """Populate core AWS-specific metadata for the listener."""
        # Define field mappings with defaults
        core_fields = {
            "arn": ("aws_listener_arn", None),
            "id": ("aws_listener_id", None),
            "load_balancer_arn": ("aws_load_balancer_arn", None),
            "port": ("aws_port", None),
            "protocol": ("aws_protocol", ListenerDefaults.DEFAULT_PROTOCOL),
            "region": ("aws_region", None),
        }

        for source_key, (target_key, default) in core_fields.items():
            value = metadata_values.get(source_key, default)
            if value is not None:
                metadata[target_key] = value

    def _populate_aws_configuration_metadata(
        self, metadata: dict[str, Any], metadata_values: dict[str, Any]
    ) -> None:
        """Populate AWS configuration-specific metadata."""
        config_fields: dict[str, tuple[str, Any]] = {
            "ssl_policy": ("aws_ssl_policy", None),
            "certificate_arn": ("aws_certificate_arn", None),
            "alpn_policy": ("aws_alpn_policy", None),
            "default_action": ("aws_default_action", []),
        }

        for source_key, (target_key, default) in config_fields.items():
            value = metadata_values.get(source_key, default)
            # Only include non-empty collections and non-None values
            if value and (not isinstance(value, list | dict) or value):
                metadata[target_key] = value

    def _populate_aws_operational_metadata(
        self, metadata: dict[str, Any], metadata_values: dict[str, Any]
    ) -> None:
        """Populate AWS operational metadata."""
        # Handle tags separately to check for differences
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

    def _determine_network_name(
        self,
        values: dict[str, Any],
        context: "TerraformMappingContext | None",
        resource_data: dict[str, Any],
    ) -> str:
        """Determine the network name based on load balancer configuration.

        Args:
            values: Listener configuration values
            context: TerraformMappingContext for load balancer lookup
            resource_data: Full resource data for dependency analysis

        Returns:
            Network name ("PUBLIC" or "PRIVATE")
        """
        # Default to PUBLIC if we can't determine otherwise
        default_network = "PUBLIC"

        # If no context available, use default
        if not context:
            logger.debug(
                "No context available for network name determination, "
                "using default: %s",
                default_network,
            )
            return default_network

        # Try to find the load balancer this listener belongs to
        load_balancer_arn = values.get("load_balancer_arn")
        if not load_balancer_arn:
            logger.debug(
                "No load_balancer_arn found, using default network: %s", default_network
            )
            return default_network

        # Try to extract load balancer configuration to determine if it's internal
        try:
            # Extract terraform references to find the load balancer
            terraform_refs = context.extract_terraform_references(resource_data)

            for prop_name, target_ref, _relationship_type in terraform_refs:
                if prop_name == "load_balancer_arn":
                    # Try to find the load balancer resource in the parsed data
                    lb_is_internal = self._check_load_balancer_internal_status(
                        context, target_ref
                    )
                    if lb_is_internal is not None:
                        network_name = "PRIVATE" if lb_is_internal else "PUBLIC"
                        logger.debug(
                            "Determined network name from load balancer: %s",
                            network_name,
                        )
                        return network_name

        except Exception as e:
            logger.debug("Error determining network name from load balancer: %s", e)

        logger.debug(
            "Could not determine network name from load balancer, using default: %s",
            default_network,
        )
        return default_network

    def _check_load_balancer_internal_status(
        self, context: "TerraformMappingContext", lb_reference: str
    ) -> bool | None:
        """Check if a load balancer is internal based on its configuration.

        Args:
            context: TerraformMappingContext for data access
            lb_reference: Load balancer reference (terraform address)

        Returns:
            True if internal, False if external, None if unknown
        """
        try:
            # Search for the load balancer resource in parsed data
            for data_key in ["planned_values", "state"]:
                if data_key in context.parsed_data:
                    if data_key == "planned_values":
                        root_module = context.parsed_data[data_key].get(
                            "root_module", {}
                        )
                    else:
                        # state data
                        state_data = context.parsed_data[data_key]
                        values = state_data.get("values", {})
                        root_module = values.get("root_module", {}) if values else {}

                    if root_module:
                        lb_internal_status = self._search_load_balancer_in_module(
                            root_module, lb_reference
                        )
                        if lb_internal_status is not None:
                            return lb_internal_status

        except Exception as e:
            logger.debug("Error checking load balancer internal status: %s", e)

        return None

    def _search_load_balancer_in_module(
        self, module_data: dict, lb_reference: str
    ) -> bool | None:
        """Search for load balancer internal status in module resources.

        Args:
            module_data: Module data containing resources
            lb_reference: Load balancer reference to find

        Returns:
            True if internal, False if external, None if not found
        """
        # Search in current module resources
        for resource in module_data.get("resources", []):
            resource_address = resource.get("address", "")

            # Check if this matches our load balancer reference
            if resource_address == lb_reference or resource_address.endswith(
                lb_reference
            ):
                resource_values = resource.get("values", {})
                internal_status = resource_values.get("internal")
                if internal_status is not None:
                    return bool(internal_status)

        # Search in child modules
        for child_module in module_data.get("child_modules", []):
            result = self._search_load_balancer_in_module(child_module, lb_reference)
            if result is not None:
                return result

        return None

    def _log_mapped_properties(
        self, node_name: str, values: dict[str, Any], metadata_values: dict[str, Any]
    ) -> None:
        """Log mapped properties for debugging."""
        logger.debug("Mapped properties for '%s':", node_name)
        logger.debug("  - Port: %s", metadata_values.get("port"))
        logger.debug(
            "  - Protocol: %s",
            metadata_values.get("protocol", ListenerDefaults.DEFAULT_PROTOCOL),
        )
        logger.debug(
            "  - Load Balancer ARN: %s", metadata_values.get("load_balancer_arn")
        )
        logger.debug("  - SSL Policy: %s", metadata_values.get("ssl_policy"))
        logger.debug("  - Certificate ARN: %s", metadata_values.get("certificate_arn"))
        logger.debug("  - Tags: %s", metadata_values.get("tags", {}))
        logger.debug("  - Region: %s", metadata_values.get("region"))
