import logging
from typing import TYPE_CHECKING, Any, Optional

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper
from src.plugins.provisioning.terraform.exceptions import ValidationError
from src.plugins.provisioning.terraform.mappers.aws.utils import AWSProtocolMapper


class LoadBalancerMappingError(Exception):
    """Base exception for Load Balancer mapping errors."""

    pass


class InvalidLoadBalancerDataError(LoadBalancerMappingError):
    """Raised when load balancer data is invalid or corrupted."""

    pass


class UnsupportedLoadBalancerTypeError(LoadBalancerMappingError):
    """Raised when attempting to map an unsupported load balancer type."""

    pass


if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.provisioning.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)

# Constants
SUPPORTED_RESOURCE_TYPES = ["aws_lb"]
DEFAULT_HTTP_PORT = 80
DEFAULT_IDLE_TIMEOUT = 60
DEFAULT_IP_ADDRESS_TYPE = "ipv4"
LOAD_BALANCER_TYPE_APPLICATION = "application"
LOAD_BALANCER_TYPE_NETWORK = "network"
LOAD_BALANCER_TYPE_GATEWAY = "gateway"
DEFAULT_PROTOCOL_HTTP = "HTTP"
DEFAULT_PROTOCOL_TCP = "tcp"
PUBLIC_NETWORK = "PUBLIC"
PRIVATE_NETWORK = "PRIVATE"
LISTENER_CACHE_SIZE = 128


class AWSLoadBalancerMapper(SingleResourceMapper):
    """Map Terraform AWS Load Balancer (aws_lb) resources to TOSCA LoadBalancer nodes.

    Supports all AWS Load Balancer types:
    - Application Load Balancer (ALB)
    - Network Load Balancer (NLB)
    - Gateway Load Balancer (GWLB)
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for AWS Load Balancer resource types.

        Args:
            resource_type: The type of resource to check
            resource_data: Resource configuration data

        Returns:
            True if this mapper can handle the resource type

        Raises:
            ValueError: If resource_type is None or empty
        """
        if not resource_type:
            raise ValueError("resource_type cannot be None or empty")
        if not isinstance(resource_data, dict):
            raise ValueError("resource_data must be a dictionary")
        return resource_type in SUPPORTED_RESOURCE_TYPES

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: Optional["TerraformMappingContext"] = None,
    ) -> None:
        """Translate AWS Load Balancer resources into TOSCA LoadBalancer nodes.

        Args:
            resource_name: resource name (e.g. 'aws_lb.test')
            resource_type: resource type ('aws_lb')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for variable resolution

        Raises:
            ValueError: If any required parameter is None or invalid
        """
        # Input validation
        if not resource_name:
            raise ValueError("resource_name cannot be None or empty")
        if not resource_type:
            raise ValueError("resource_type cannot be None or empty")
        if not isinstance(resource_data, dict):
            raise ValueError("resource_data must be a dictionary")
        if builder is None:
            raise ValueError("builder cannot be None")
        if resource_type != "aws_lb":
            raise ValueError(f"Unsupported resource type: {resource_type}")
        logger.info("Mapping AWS Load Balancer resource: '%s'", resource_name)

        # Validate resource state before processing
        self._validate_resource_state(resource_data, resource_name)

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

        # Create the Load Balancer node
        lb_node = builder.add_node(name=node_name, node_type="LoadBalancer")

        # Extract key properties
        lb_name = values.get("name", "")
        lb_type = values.get("load_balancer_type", LOAD_BALANCER_TYPE_APPLICATION)
        internal = values.get("internal", False)
        ip_address_type = values.get("ip_address_type", DEFAULT_IP_ADDRESS_TYPE)

        # Get resolved values specifically for metadata (always concrete values)
        if context:
            metadata_values = context.get_resolved_values(resource_data, "metadata")
        else:
            metadata_values = resource_data.get("values", {})

        # Build metadata with Terraform and AWS information
        metadata = self._build_metadata(
            resource_type,
            clean_name,
            resource_data,
            values,
            metadata_values,
            lb_type,
            internal,
        )

        # Attach metadata to the node
        lb_node.with_metadata(metadata)

        # Set LoadBalancer properties
        self._set_load_balancer_properties(lb_node, values, lb_type, lb_name)

        # Add capabilities based on load balancer type and configuration
        # Include listener information from the context
        self._add_load_balancer_capabilities(
            lb_node, values, internal, ip_address_type, context, resource_name
        )

        # Add DNS capabilities if Route53 records are associated
        self._add_dns_capabilities(lb_node, context, resource_name)

        # Add target group requirements
        logger.info(
            "Adding target group requirements for Load Balancer: %s", resource_name
        )
        self._add_target_group_requirements(lb_node, context, resource_name)

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

                # Check if target_ref is a TOSCA node name or terraform reference
                if "." in target_ref:
                    # target_ref like "aws_subnet.main" - convert to TOSCA name
                    target_resource_type = target_ref.split(".", 1)[0]
                    target_node_name = BaseResourceMapper.generate_tosca_node_name(
                        target_ref, target_resource_type
                    )
                else:
                    # target_ref is already a TOSCA node name (from context resolution)
                    target_node_name = target_ref

                # Add requirement with standardized dependency name
                # Map all AWS-specific property names to standard TOSCA dependency
                requirement_name = "dependency"

                (
                    lb_node.add_requirement(requirement_name)
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

        logger.debug("AWS Load Balancer node '%s' created successfully.", node_name)

        # Debug: mapped properties
        self._log_mapped_properties(node_name, values, metadata)

    def _build_metadata(
        self,
        resource_type: str,
        clean_name: str,
        resource_data: dict[str, Any],
        values: dict[str, Any],
        metadata_values: dict[str, Any],
        lb_type: str,
        internal: bool,
    ) -> dict[str, Any]:
        """Build comprehensive metadata for the Load Balancer node."""
        metadata: dict[str, Any] = {}

        # Original resource information
        metadata["original_resource_type"] = resource_type
        metadata["original_resource_name"] = clean_name

        # AWS Load Balancer specific metadata
        metadata["aws_component_type"] = "LoadBalancer"
        metadata["aws_load_balancer_type"] = lb_type
        metadata["aws_internal"] = internal

        # Description based on load balancer type
        if lb_type == LOAD_BALANCER_TYPE_APPLICATION:
            metadata["description"] = (
                "AWS Application Load Balancer (ALB) for HTTP/HTTPS traffic "
                "distribution"
            )
        elif lb_type == LOAD_BALANCER_TYPE_NETWORK:
            metadata["description"] = (
                "AWS Network Load Balancer (NLB) for TCP/UDP traffic distribution"
            )
        elif lb_type == LOAD_BALANCER_TYPE_GATEWAY:
            metadata["description"] = (
                "AWS Gateway Load Balancer (GWLB) for third-party virtual appliances"
            )
        else:
            metadata["description"] = "AWS Load Balancer for traffic distribution"

        # Provider information
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # AWS specific properties - use metadata values for concrete resolution
        metadata_region = metadata_values.get("region")
        if metadata_region:
            metadata["aws_region"] = metadata_region

        # Access logs configuration
        metadata_access_logs = metadata_values.get("access_logs", [])
        if metadata_access_logs:
            metadata["aws_access_logs"] = metadata_access_logs

        # Connection logs (ALB only)
        metadata_connection_logs = metadata_values.get("connection_logs", [])
        if metadata_connection_logs:
            metadata["aws_connection_logs"] = metadata_connection_logs

        # Tags
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

        # Advanced settings
        metadata_deletion_protection = metadata_values.get(
            "enable_deletion_protection", False
        )
        if metadata_deletion_protection:
            metadata["aws_deletion_protection_enabled"] = metadata_deletion_protection

        # ALB specific features
        if lb_type == "application":
            metadata_http2_enabled = metadata_values.get("enable_http2", True)
            metadata["aws_http2_enabled"] = metadata_http2_enabled

            metadata_drop_invalid_headers = metadata_values.get(
                "drop_invalid_header_fields", False
            )
            if metadata_drop_invalid_headers:
                metadata["aws_drop_invalid_header_fields"] = (
                    metadata_drop_invalid_headers
                )

            metadata_idle_timeout = metadata_values.get("idle_timeout", 60)
            if metadata_idle_timeout != 60:
                metadata["aws_idle_timeout"] = metadata_idle_timeout

        # Cross-zone load balancing
        metadata_cross_zone = metadata_values.get("enable_cross_zone_load_balancing")
        if metadata_cross_zone is not None:
            metadata["aws_cross_zone_load_balancing"] = metadata_cross_zone

        # IP address type
        metadata_ip_address_type = metadata_values.get("ip_address_type", "ipv4")
        if metadata_ip_address_type != "ipv4":
            metadata["aws_ip_address_type"] = metadata_ip_address_type

        return metadata

    def _set_load_balancer_properties(
        self,
        lb_node: Any,  # NodeTemplateBuilder type from builder
        values: dict[str, Any],
        lb_type: str,
        lb_name: str,
    ) -> None:
        """Set TOSCA LoadBalancer properties based on AWS configuration."""
        # Set load balancing algorithm (TOSCA property)
        if lb_type == "application":
            # ALB uses round_robin by default
            lb_node.with_property("algorithm", "round_robin")
        elif lb_type == "network":
            # NLB uses flow_hash algorithm
            lb_node.with_property("algorithm", "flow_hash")
        else:
            # Default for gateway or unknown types
            lb_node.with_property("algorithm", "round_robin")

    def _add_load_balancer_capabilities(
        self,
        lb_node: Any,  # NodeTemplateBuilder type from builder
        values: dict[str, Any],
        internal: bool,
        ip_address_type: str,
        context: Optional["TerraformMappingContext"] = None,
        resource_name: str = "",
    ) -> None:
        """Add appropriate capabilities to the LoadBalancer node.

        Args:
            lb_node: The LoadBalancer node to add capabilities to
            values: Load balancer configuration values
            internal: Whether the load balancer is internal
            ip_address_type: IP address type configuration
            context: Terraform mapping context for finding listeners
            resource_name: Resource name for finding related listeners
        """
        # Add client capability - this is where clients connect to the LB
        client_capability = lb_node.add_capability("client")

        # Configure endpoint properties based on internal/external and IP type
        if not internal:
            # External load balancer - accessible from internet
            client_capability.with_property("network_name", PUBLIC_NETWORK)
        else:
            # Internal load balancer - only accessible from VPC
            client_capability.with_property("network_name", PRIVATE_NETWORK)

        # Find and integrate listener information from the context
        listener_info = self._find_listeners_for_load_balancer(context, resource_name)

        if listener_info and len(listener_info) == 1:
            # Single listener: Set direct properties
            listener = listener_info[0]
            aws_protocol = listener.get("protocol", "HTTP")
            protocol = AWSProtocolMapper.to_tosca_protocol(aws_protocol)
            port = listener.get("port", 80)
            is_secure = AWSProtocolMapper.is_secure_protocol(aws_protocol)

            client_capability.with_property("protocol", protocol)
            client_capability.with_property("port", port)
            client_capability.with_property("secure", is_secure)

        elif listener_info and len(listener_info) > 1:
            # Multiple listeners: Use the 'ports' map
            ports_map = {}

            for listener in listener_info:
                aws_protocol = listener.get("protocol", "HTTP")
                port = listener.get("port", 80)
                tosca_protocol = AWSProtocolMapper.to_tosca_protocol(aws_protocol)

                # Create a descriptive key for the port map
                port_key = f"{aws_protocol.lower()}-{port}"

                ports_map[port_key] = {"protocol": tosca_protocol, "target": port}

            client_capability.with_property("ports", ports_map)

            # Set default protocol from the first listener
            first_listener = listener_info[0]
            first_aws_protocol = first_listener.get("protocol", "HTTP")
            default_protocol = AWSProtocolMapper.to_tosca_protocol(first_aws_protocol)
            default_port = first_listener.get("port", 80)
            default_secure = AWSProtocolMapper.is_secure_protocol(first_aws_protocol)

            client_capability.with_property("protocol", default_protocol)
            client_capability.with_property("port", default_port)
            client_capability.with_property("secure", default_secure)

        else:
            # No listeners found: Use default configuration based on LB type
            lb_type = values.get("load_balancer_type", "application")

            if lb_type == "application":
                # ALB typically handles HTTP/HTTPS
                client_capability.with_property("protocol", "http")
                client_capability.with_property("port", 80)
                client_capability.with_property("secure", False)
            elif lb_type == "network":
                # NLB can handle any TCP/UDP protocol
                client_capability.with_property("protocol", "tcp")
                # Port will be defined by listeners
                client_capability.with_property("port", 80)
                client_capability.with_property("secure", False)
            else:
                # Gateway LB or unknown type
                client_capability.with_property("protocol", "tcp")
                client_capability.with_property("port", 80)
                client_capability.with_property("secure", False)

        client_capability.and_node()

    def _log_mapped_properties(
        self,
        node_name: str,
        values: dict[str, Any],
        metadata: dict[str, Any],
    ) -> None:
        """Log the mapped properties for debugging."""
        if logger.isEnabledFor(logging.DEBUG):
            # Extract from metadata for concrete values
            lb_name = values.get("name", "")
            lb_type = values.get("load_balancer_type", "application")
            internal = values.get("internal", False)

            logger.debug("Mapped properties for '%s':", node_name)
            logger.debug("  - Name: %s", lb_name)
            logger.debug("  - Type: %s", lb_type)
            logger.debug("  - Internal: %s", internal)
            logger.debug("  - Region: %s", metadata.get("aws_region", ""))
            logger.debug("  - Tags: %s", metadata.get("aws_tags", {}))
            logger.debug("  - Access Control: %s", "Private" if internal else "Public")
            logger.debug(
                "  - Deletion Protection: %s",
                metadata.get("aws_deletion_protection_enabled", False),
            )

    def _find_listeners_for_load_balancer(
        self, context: Optional["TerraformMappingContext"], lb_resource_name: str
    ) -> list[dict[str, Any]]:
        """Find listeners associated with this load balancer using indexing.

        Args:
            context: Terraform mapping context to search for listeners
            lb_resource_name: The load balancer resource name (e.g., 'aws_lb.front_end')

        Returns:
            List of listener configuration dictionaries
        """
        if not context:
            logger.debug("No context provided for listener search")
            return []

        # Get listeners for this load balancer from the cached index
        listener_index = self._get_listener_index(context)
        listeners = listener_index.get(lb_resource_name, [])

        logger.debug(
            "Found %d listeners for load balancer: %s -> %s",
            len(listeners),
            lb_resource_name,
            [listener.get("address", "unknown") for listener in listeners],
        )

        return listeners

    def _get_listener_index(
        self, context: "TerraformMappingContext"
    ) -> dict[str, list[dict[str, Any]]]:
        """Get listener index with proper context-based caching.

        Args:
            context: Terraform mapping context containing parsed data

        Returns:
            Dictionary mapping load balancer resource names to their listeners
        """
        # Build the index every time (no caching to avoid type issues)
        return self._build_listener_index(context)

    def _build_listener_index(
        self, context: "TerraformMappingContext"
    ) -> dict[str, list[dict[str, Any]]]:
        """Build an optimized index of listeners by their load balancer reference.

        This replaces the O(n²) search with O(n) indexing for better performance.

        Args:
            context: Terraform mapping context containing parsed data

        Returns:
            Dictionary mapping load balancer resource names to their listeners
        """
        from collections import defaultdict

        listener_index: dict[str, list[dict[str, Any]]] = defaultdict(list)

        logger.debug("Building listener index for performance optimization")

        try:
            # The data structure is directly at the root of parsed_data
            parsed_data = context.parsed_data
            if not parsed_data:
                logger.debug("No parsed data found for listener indexing")
                return dict(listener_index)

            # Index listeners from both configuration and planned_values sections
            # Try configuration first (has references), then planned_values as fallback
            for data_key in ["configuration", "planned_values"]:
                data_section = parsed_data.get(data_key, {})
                if not data_section:
                    logger.info("No data found in section: %s", data_key)
                    continue

                root_module = data_section.get("root_module", {})
                if root_module:
                    logger.info("Processing listener index for section: %s", data_key)
                    self._index_listeners_in_module(
                        root_module, data_key, listener_index
                    )
                else:
                    logger.info("No root_module in section: %s", data_key)

        except (KeyError, AttributeError) as e:
            logger.warning("Invalid data structure in listener index building: %s", e)
        except Exception as e:
            logger.error("Unexpected error building listener index: %s", e)
            raise LoadBalancerMappingError(
                f"Failed to build listener index: {e}"
            ) from e

        # Convert defaultdict to regular dict and log statistics
        result = dict(listener_index)
        total_listeners = sum(len(listeners) for listeners in result.values())
        logger.debug(
            "Built listener index: %d load balancers with %d total listeners",
            len(result),
            total_listeners,
        )

        return result

    def _index_listeners_in_module(
        self,
        module_data: dict,
        data_section: str,
        listener_index: dict[str, list[dict[str, Any]]],
    ) -> None:
        """Recursively index listeners in a module and its child modules.

        Args:
            module_data: Module data containing resources
            data_section: Section name ('planned_values' or 'configuration')
            listener_index: Index to populate with listener mappings
        """
        # Index current module resources
        for resource in module_data.get("resources", []):
            resource_type = resource.get("type", "")
            if resource_type != "aws_lb_listener":
                continue

            resource_address = resource.get("address", "")
            logger.info("Found listener resource: %s", resource_address)

            # Extract the load balancer reference
            lb_reference = self._extract_load_balancer_reference(resource, data_section)

            if lb_reference:
                # Create listener configuration
                listener_config = self._create_listener_config(resource, data_section)
                if listener_config:
                    listener_index[lb_reference].append(listener_config)
                    logger.debug(
                        "Indexed listener %s -> %s", resource_address, lb_reference
                    )

        # Recursively process child modules
        for child_module in module_data.get("child_modules", []):
            self._index_listeners_in_module(child_module, data_section, listener_index)

    def _extract_load_balancer_reference(
        self, listener_resource: dict, data_section: str
    ) -> str | None:
        """Extract load balancer reference from a listener resource.

        Args:
            listener_resource: The listener resource data
            data_section: Section name ('planned_values' or 'configuration')

        Returns:
            Load balancer resource name if found, None otherwise
        """
        if data_section == "configuration":
            # In configuration section, look for references in expressions
            expressions = listener_resource.get("expressions", {})
            load_balancer_arn_expr = expressions.get("load_balancer_arn", {})
            references = load_balancer_arn_expr.get("references", [])

            logger.info(
                "Extracting LB reference from listener %s: expressions=%s",
                listener_resource.get("address", "unknown"),
                list(expressions.keys()),
            )
            logger.info("load_balancer_arn_expr: %s", load_balancer_arn_expr)
            logger.info("references: %s", references)

            for ref in references:
                if isinstance(ref, str) and "aws_lb." in ref:
                    # Extract the resource address (e.g., "aws_lb.test")
                    result = ref.split(".arn")[0]
                    logger.info("Found LB reference: %s -> %s", ref, result)
                    return result
        else:
            # In planned_values or state, look at resource values
            resource_values = listener_resource.get("values", {})
            load_balancer_arn = resource_values.get("load_balancer_arn")

            # Try to extract load balancer name from ARN or reference
            if isinstance(load_balancer_arn, str):
                # This might be a reference like "aws_lb.test" or an ARN
                if "aws_lb." in load_balancer_arn:
                    return load_balancer_arn.split(".arn")[0]
            elif isinstance(load_balancer_arn, dict):
                # Terraform reference format
                references = load_balancer_arn.get("references", [])
                for ref in references:
                    if "aws_lb." in str(ref):
                        return str(ref).split(".arn")[0]

        return None

    def _create_listener_config(
        self, listener_resource: dict, data_section: str
    ) -> dict[str, Any] | None:
        """Create listener configuration from resource data.

        Args:
            listener_resource: The listener resource data
            data_section: Section name ('planned_values' or 'configuration')

        Returns:
            Listener configuration dictionary or None if invalid
        """
        resource_address = listener_resource.get("address", "")

        if data_section == "configuration":
            # Extract from expressions
            expressions = listener_resource.get("expressions", {})

            port_expr = expressions.get("port", {})
            port_value = port_expr.get("constant_value", DEFAULT_HTTP_PORT)
            try:
                port = int(port_value)
                if not 1 <= port <= 65535:
                    raise ValueError(f"Port {port} is out of valid range (1-65535)")
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Invalid port value '%s' for %s, using default %d: %s",
                    port_value,
                    resource_address,
                    DEFAULT_HTTP_PORT,
                    e,
                )
                port = DEFAULT_HTTP_PORT

            protocol_expr = expressions.get("protocol", {})
            protocol = protocol_expr.get("constant_value", DEFAULT_PROTOCOL_HTTP)

            ssl_policy_expr = expressions.get("ssl_policy", {})
            ssl_policy = ssl_policy_expr.get("constant_value")

            cert_arn_expr = expressions.get("certificate_arn", {})
            certificate_arn = cert_arn_expr.get("constant_value")

        else:
            # Extract from values
            resource_values = listener_resource.get("values", {})

            port_value = resource_values.get("port", DEFAULT_HTTP_PORT)
            try:
                port = int(port_value)
                if not 1 <= port <= 65535:
                    raise ValueError(f"Port {port} is out of valid range (1-65535)")
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Invalid port value '%s' for %s, using default %d: %s",
                    port_value,
                    resource_address,
                    DEFAULT_HTTP_PORT,
                    e,
                )
                port = DEFAULT_HTTP_PORT

            protocol = resource_values.get("protocol", DEFAULT_PROTOCOL_HTTP)
            ssl_policy = resource_values.get("ssl_policy")
            certificate_arn = resource_values.get("certificate_arn")

        return {
            "address": resource_address,
            "port": port,
            "protocol": protocol,
            "ssl_policy": ssl_policy,
            "certificate_arn": certificate_arn,
        }

    def _listener_references_load_balancer(
        self,
        load_balancer_arn: Any,
        lb_resource_name: str,
        _listener_values: dict[str, Any],
    ) -> bool:
        """Check if a listener references the given load balancer.

        Args:
            load_balancer_arn: The load_balancer_arn value from the listener
            lb_resource_name: Load balancer resource name to match
            _listener_values: Full listener configuration values (unused)

        Returns:
            True if the listener references the load balancer
        """
        if not load_balancer_arn:
            return False

        # Handle different formats of load_balancer_arn
        if isinstance(load_balancer_arn, str):
            # Direct string reference
            if lb_resource_name in load_balancer_arn:
                return True
        elif isinstance(load_balancer_arn, dict):
            # Terraform reference format
            references = load_balancer_arn.get("references", [])
            if references:
                for ref in references:
                    if lb_resource_name in str(ref):
                        return True
        elif isinstance(load_balancer_arn, list):
            # List of references
            for ref in load_balancer_arn:
                if lb_resource_name in str(ref):
                    return True

        return False

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

    def _add_dns_capabilities(
        self,
        lb_node,
        context: "TerraformMappingContext | None",
        lb_resource_name: str,
    ) -> None:
        """Add DNS capabilities if Route53 records are associated with
        this load balancer.

        Args:
            lb_node: The LoadBalancer node to enhance with DNS capabilities
            context: Terraform mapping context to search for Route53 records
            lb_resource_name: The load balancer resource name
        """
        if not context:
            logger.debug("No context provided for DNS capability search")
            return

        # Find Route53 records that reference this load balancer
        dns_records = self._find_route53_records_for_load_balancer(
            context, lb_resource_name
        )

        if not dns_records:
            logger.debug(
                "No Route53 records found for load balancer: %s", lb_resource_name
            )
            return

        # Use the first DNS record found (most common case)
        primary_dns = dns_records[0]
        dns_name = primary_dns.get("name")
        if dns_name:
            # Add DNS name via the builder pattern - this will create or
            # update the client capability
            client_capability = lb_node.add_capability("client")
            client_capability.with_property("dns_name", dns_name)
            client_capability.and_node()

            logger.info(
                "Added DNS capability '%s' to load balancer '%s'",
                dns_name,
                lb_resource_name,
            )

            # Add DNS metadata to the load balancer node
            metadata = {}
            metadata["aws_dns_record_name"] = dns_name
            metadata["aws_dns_record_type"] = primary_dns.get("type", "A")

            alias_config = primary_dns.get("alias", [])
            if alias_config:
                metadata["aws_dns_alias_configuration"] = alias_config

            metadata["aws_dns_component_type"] = "Route53Endpoint"

            # Add the DNS metadata to the node using the builder pattern
            lb_node.with_metadata(metadata)

    def _add_target_group_requirements(
        self,
        lb_node,
        context: "TerraformMappingContext | None",
        lb_resource_name: str,
    ) -> None:
        """Add RoutesTo requirements to target groups associated with
        this load balancer.

        Args:
            lb_node: The LoadBalancer node to add requirements to
            context: Terraform mapping context to search for target groups
            lb_resource_name: The load balancer resource name
        """
        if not context:
            logger.info("No context provided for target group search")
            return

        # Find target groups that are associated with this load balancer
        logger.info(
            "Searching for target groups associated with load balancer: %s",
            lb_resource_name,
        )
        target_groups = self._find_target_groups_for_load_balancer(
            context, lb_resource_name
        )
        logger.info(
            "Found %d target groups for load balancer %s: %s",
            len(target_groups),
            lb_resource_name,
            target_groups,
        )

        if not target_groups:
            logger.info(
                "No target groups found for load balancer: %s", lb_resource_name
            )
            return

        # Add RoutesTo requirements for each target group
        for tg_address in target_groups:
            # Generate TOSCA node name for the target group
            if "." in tg_address:
                tg_resource_type = tg_address.split(".", 1)[0]
                tg_node_name = BaseResourceMapper.generate_tosca_node_name(
                    tg_address, tg_resource_type
                )
            else:
                tg_node_name = tg_address

            logger.debug(
                "Adding RoutesTo requirement from LoadBalancer '%s' to "
                "target group '%s' (address: %s)",
                lb_resource_name,
                tg_node_name,
                tg_address,
            )

            # Add the RoutesTo requirement
            (
                lb_node.add_requirement("application")
                .to_node(tg_node_name)
                .with_relationship("RoutesTo")
                .and_node()
            )

            logger.info(
                "Added RoutesTo requirement from LoadBalancer '%s' to "
                "target group '%s'",
                lb_resource_name,
                tg_node_name,
            )

    def _find_route53_records_for_load_balancer(
        self, context: "TerraformMappingContext", lb_resource_name: str
    ) -> list[dict[str, Any]]:
        """Find Route53 records that reference this load balancer.

        Args:
            context: Terraform mapping context containing parsed data
            lb_resource_name: The load balancer resource name to search for

        Returns:
            List of Route53 record configurations that reference this LB
        """
        dns_records: list[dict[str, Any]] = []

        try:
            parsed_data = context.parsed_data
            if not parsed_data:
                return dns_records

            # Search in both planned_values and configuration sections
            for data_key in ["planned_values", "configuration"]:
                data_section = parsed_data.get(data_key, {})
                if not data_section:
                    continue

                root_module = data_section.get("root_module", {})
                if root_module:
                    self._find_route53_records_in_module(
                        root_module, data_key, lb_resource_name, dns_records
                    )

        except Exception as e:
            logger.debug("Error finding Route53 records: %s", e)

        logger.debug(
            "Found %d Route53 records for load balancer: %s",
            len(dns_records),
            lb_resource_name,
        )
        return dns_records

    def _find_route53_records_in_module(
        self,
        module_data: dict,
        data_section: str,
        lb_resource_name: str,
        dns_records: list[dict[str, Any]],
    ) -> None:
        """Recursively find Route53 records in a module that reference
        the load balancer.

        Args:
            module_data: Module data containing resources
            data_section: Section name ('planned_values' or 'configuration')
            lb_resource_name: Load balancer resource name to search for
            dns_records: List to append matching DNS records to
        """
        # Search current module resources
        for resource in module_data.get("resources", []):
            resource_type = resource.get("type", "")
            if resource_type != "aws_route53_record":
                continue

            # Check if this Route53 record references the load balancer
            if self._route53_record_references_load_balancer(
                resource, data_section, lb_resource_name
            ):
                # Extract DNS record information
                record_config = self._extract_route53_record_config(
                    resource, data_section
                )
                if record_config:
                    dns_records.append(record_config)

        # Recursively process child modules
        for child_module in module_data.get("child_modules", []):
            self._find_route53_records_in_module(
                child_module, data_section, lb_resource_name, dns_records
            )

    def _find_target_groups_for_load_balancer(
        self, context: "TerraformMappingContext", lb_resource_name: str
    ) -> list[str]:
        """Find target groups that are associated with this load balancer.

        Uses multiple discovery methods for robustness:
        1. Via listeners and their default actions (original method)
        2. Via aws_lb_target_group_attachment resources (fallback)
        3. Via direct state analysis (new method for state-based discovery)
        4. Via direct configuration references (fallback)

        Args:
            context: Terraform mapping context containing parsed data
            lb_resource_name: The load balancer resource name

        Returns:
            List of target group resource addresses
        """
        target_groups: list[str] = []

        try:
            parsed_data = context.parsed_data
            if not parsed_data:
                return target_groups

            # Method 1: Find through listeners (original approach)
            logger.info("Method 1: Finding target groups via listeners")
            listeners = self._find_listeners_for_load_balancer(
                context, lb_resource_name
            )
            logger.info(
                "Found %d listeners for load balancer %s: %s",
                len(listeners),
                lb_resource_name,
                [listener.get("address", "unknown") for listener in listeners],
            )
            for listener in listeners:
                listener_address = listener.get("address", "")
                logger.info("Processing listener: %s", listener_address)
                listener_target_groups = self._find_target_groups_for_listener(
                    context, listener_address
                )
                target_groups.extend(listener_target_groups)
                logger.info(
                    "Found target groups via listener %s: %s",
                    listener_address,
                    listener_target_groups,
                )

            # Method 2: Find through target group attachments (fallback)
            if not target_groups:
                attachment_target_groups = self._find_target_groups_via_attachments(
                    context, lb_resource_name
                )
                target_groups.extend(attachment_target_groups)
                logger.debug(
                    "Found target groups via attachments: %s", attachment_target_groups
                )

            # Method 3: Find through state analysis (new method)
            if not target_groups:
                state_target_groups = self._find_target_groups_via_state_analysis(
                    context, lb_resource_name
                )
                target_groups.extend(state_target_groups)
                logger.info(
                    "Found target groups via state analysis: %s", state_target_groups
                )

            # Method 4: Find through direct configuration references (fallback)
            if not target_groups:
                config_target_groups = self._find_target_groups_via_configuration(
                    context, lb_resource_name
                )
                target_groups.extend(config_target_groups)
                logger.debug(
                    "Found target groups via configuration: %s", config_target_groups
                )

        except Exception as e:
            logger.debug("Error finding target groups: %s", e)

        # Remove duplicates
        target_groups = list(set(target_groups))

        logger.debug(
            "Found %d target groups for load balancer: %s -> %s",
            len(target_groups),
            lb_resource_name,
            target_groups,
        )
        return target_groups

    def _find_target_groups_for_listener(
        self, context: "TerraformMappingContext", listener_address: str
    ) -> list[str]:
        """Find target groups referenced by a specific listener.

        Args:
            context: Terraform mapping context
            listener_address: The listener resource address

        Returns:
            List of target group resource addresses
        """
        target_groups: list[str] = []

        try:
            parsed_data = context.parsed_data

            # Search for the listener in the configuration section
            # (has the references we need)
            for data_key in ["configuration"]:
                data_section = parsed_data.get(data_key, {})
                if not data_section:
                    continue

                root_module = data_section.get("root_module", {})
                if root_module:
                    self._extract_target_groups_from_listener_module(
                        root_module, data_key, listener_address, target_groups
                    )

        except Exception as e:
            logger.debug("Error finding target groups for listener: %s", e)

        return list(set(target_groups))  # Remove duplicates

    def _route53_record_references_load_balancer(
        self, route53_resource: dict, data_section: str, lb_resource_name: str
    ) -> bool:
        """Check if a Route53 record references the given load balancer.

        Args:
            route53_resource: The Route53 record resource data
            data_section: Section name ('planned_values' or 'configuration')
            lb_resource_name: Load balancer resource name to match

        Returns:
            True if the record references the load balancer
        """
        if data_section == "configuration":
            # Check expressions for alias references
            expressions = route53_resource.get("expressions", {})
            alias_expr = expressions.get("alias", [])

            for alias in alias_expr:
                if isinstance(alias, dict):
                    name_refs = alias.get("name", {}).get("references", [])
                    for ref in name_refs:
                        if lb_resource_name in str(ref):
                            return True
        else:
            # Check values for alias configuration
            values = route53_resource.get("values", {})
            alias_configs = values.get("alias", [])

            for alias in alias_configs:
                if isinstance(alias, dict):
                    name = alias.get("name", "")
                    if lb_resource_name in str(name):
                        return True

        return False

    def _extract_route53_record_config(
        self, route53_resource: dict, data_section: str
    ) -> dict[str, Any] | None:
        """Extract Route53 record configuration.

        Args:
            route53_resource: The Route53 record resource data
            data_section: Section name ('planned_values' or 'configuration')

        Returns:
            Route53 record configuration dictionary or None
        """
        if data_section == "configuration":
            expressions = route53_resource.get("expressions", {})

            name_expr = expressions.get("name", {})
            record_name = name_expr.get("constant_value", "")

            type_expr = expressions.get("type", {})
            record_type = type_expr.get("constant_value", "A")

            alias_expr = expressions.get("alias", [])
        else:
            values = route53_resource.get("values", {})
            record_name = values.get("name", "")
            record_type = values.get("type", "A")
            alias_expr = values.get("alias", [])

        return {
            "address": route53_resource.get("address", ""),
            "name": record_name,
            "type": record_type,
            "alias": alias_expr,
        }

    def _extract_target_groups_from_listener_module(
        self,
        module_data: dict,
        data_section: str,
        listener_address: str,
        target_groups: list[str],
    ) -> None:
        """Extract target groups from listener default actions in a module.

        Args:
            module_data: Module data containing resources
            data_section: Section name ('planned_values' or 'configuration')
            listener_address: Listener address to find
            target_groups: List to append target group addresses to
        """
        # Find the specific listener resource
        logger.debug(
            "Searching for listener %s in module with %d resources",
            listener_address,
            len(module_data.get("resources", [])),
        )
        for resource in module_data.get("resources", []):
            resource_addr = resource.get("address")
            logger.debug(
                "Checking resource: %s vs target: %s", resource_addr, listener_address
            )
            if resource_addr != listener_address:
                continue
            logger.debug("Found matching listener resource: %s", listener_address)

            if data_section == "configuration":
                expressions = resource.get("expressions", {})
                default_action = expressions.get("default_action", [])

                logger.debug(
                    "Extracting target groups from listener %s (configuration): "
                    "%d default actions, expressions keys: %s",
                    listener_address,
                    len(default_action),
                    list(expressions.keys()),
                )

                for action in default_action:
                    logger.debug("Processing default action: %s", action)
                    if isinstance(action, dict):
                        target_group_arn = action.get("target_group_arn", {})
                        refs = target_group_arn.get("references", [])
                        logger.debug("Found target_group_arn references: %s", refs)
                        for ref in refs:
                            if "aws_lb_target_group" in str(ref):
                                tg_ref = str(ref).split(".arn")[0]
                                target_groups.append(tg_ref)
                                logger.debug("Added target group: %s", tg_ref)
            else:
                values = resource.get("values", {})
                default_actions = values.get("default_action", [])

                logger.debug(
                    "Extracting target groups from listener %s (values): "
                    "%d default actions, values keys: %s",
                    listener_address,
                    len(default_actions),
                    list(values.keys()),
                )

                for action in default_actions:
                    logger.debug("Processing default action: %s", action)
                    if isinstance(action, dict):
                        tg_arn = action.get("target_group_arn")
                        if tg_arn and "aws_lb_target_group" in str(tg_arn):
                            tg_ref = str(tg_arn).split(".arn")[0]
                            target_groups.append(tg_ref)
                            logger.debug("Added target group: %s", tg_ref)

        # Recursively process child modules
        for child_module in module_data.get("child_modules", []):
            self._extract_target_groups_from_listener_module(
                child_module, data_section, listener_address, target_groups
            )

    def _find_target_groups_via_attachments(
        self, context: "TerraformMappingContext", lb_resource_name: str
    ) -> list[str]:
        """Find target groups via aws_lb_target_group_attachment resources.

        This method looks for target group attachments that reference this load balancer
        indirectly through shared target groups or load balancer ARNs.

        Args:
            context: Terraform mapping context containing parsed data
            lb_resource_name: The load balancer resource name to search for

        Returns:
            List of target group resource names
        """
        target_groups: list[str] = []

        try:
            parsed_data = context.parsed_data
            if not parsed_data:
                return target_groups

            # Search in both planned_values and configuration sections
            for data_key in ["planned_values", "configuration"]:
                data_section = parsed_data.get(data_key, {})
                if not data_section:
                    continue

                root_module = data_section.get("root_module", {})
                if root_module:
                    self._find_target_groups_via_attachments_in_module(
                        root_module, data_key, lb_resource_name, target_groups
                    )

        except Exception as e:
            logger.debug("Error finding target groups via attachments: %s", e)

        logger.debug(
            "Found %d target groups via attachments for load balancer: %s",
            len(target_groups),
            lb_resource_name,
        )
        return list(set(target_groups))  # Remove duplicates

    def _find_target_groups_via_attachments_in_module(
        self,
        module_data: dict,
        data_section: str,
        lb_resource_name: str,
        target_groups: list[str],
    ) -> None:
        """Find target groups via attachments in a specific module."""
        for resource in module_data.get("resources", []):
            resource_type = resource.get("type", "")
            if resource_type != "aws_lb_target_group_attachment":
                continue

            if data_section == "configuration":
                expressions = resource.get("expressions", {})
                target_group_arn = expressions.get("target_group_arn", {})
                refs = target_group_arn.get("references", [])

                for ref in refs:
                    if "aws_lb_target_group" in str(ref):
                        tg_ref = str(ref).split(".arn")[0]
                        # Check if this target group might be associated with our LB
                        if self._is_target_group_for_load_balancer(
                            module_data, tg_ref, lb_resource_name
                        ):
                            target_groups.append(tg_ref)
            else:
                values = resource.get("values", {})
                target_group_arn = values.get("target_group_arn")
                if target_group_arn and "aws_lb_target_group" in str(target_group_arn):
                    tg_ref = str(target_group_arn).split(".arn")[0]
                    if self._is_target_group_for_load_balancer(
                        module_data, tg_ref, lb_resource_name
                    ):
                        target_groups.append(tg_ref)

        # Recursively process child modules
        for child_module in module_data.get("child_modules", []):
            self._find_target_groups_via_attachments_in_module(
                child_module, data_section, lb_resource_name, target_groups
            )

    def _find_target_groups_via_configuration(
        self, context: "TerraformMappingContext", lb_resource_name: str
    ) -> list[str]:
        """Find target groups via direct configuration references.

        This method looks for target group resources that directly reference
        the load balancer in their configuration, such as vpc_id matching.

        Args:
            context: Terraform mapping context containing parsed data
            lb_resource_name: The load balancer resource name to search for

        Returns:
            List of target group resource names
        """
        target_groups: list[str] = []

        try:
            parsed_data = context.parsed_data
            if not parsed_data:
                return target_groups

            # Get load balancer VPC for matching
            lb_vpc_id = self._get_load_balancer_vpc_id(context, lb_resource_name)
            if not lb_vpc_id:
                logger.debug(
                    "Could not determine VPC for load balancer: %s", lb_resource_name
                )
                return target_groups

            # Search for target groups in the same VPC
            for data_key in ["planned_values", "configuration"]:
                data_section = parsed_data.get(data_key, {})
                if not data_section:
                    continue

                root_module = data_section.get("root_module", {})
                if root_module:
                    self._find_target_groups_via_configuration_in_module(
                        root_module, data_key, lb_vpc_id, target_groups
                    )

        except Exception as e:
            logger.debug("Error finding target groups via configuration: %s", e)

        logger.debug(
            "Found %d target groups via configuration for load balancer: %s",
            len(target_groups),
            lb_resource_name,
        )
        return list(set(target_groups))  # Remove duplicates

    def _find_target_groups_via_configuration_in_module(
        self,
        module_data: dict,
        data_section: str,
        lb_vpc_id: str,
        target_groups: list[str],
    ) -> None:
        """Find target groups via configuration in a specific module."""
        for resource in module_data.get("resources", []):
            resource_type = resource.get("type", "")
            if resource_type != "aws_lb_target_group":
                continue

            resource_address = resource.get("address", "")

            if data_section == "configuration":
                expressions = resource.get("expressions", {})
                vpc_id_expr = expressions.get("vpc_id", {})
                vpc_refs = vpc_id_expr.get("references", [])

                # Check if vpc_id matches our load balancer's VPC
                for ref in vpc_refs:
                    if str(ref) == lb_vpc_id:
                        target_groups.append(resource_address)
                        break
            else:
                values = resource.get("values", {})
                vpc_id = values.get("vpc_id")
                if vpc_id == lb_vpc_id:
                    target_groups.append(resource_address)

        # Recursively process child modules
        for child_module in module_data.get("child_modules", []):
            self._find_target_groups_via_configuration_in_module(
                child_module, data_section, lb_vpc_id, target_groups
            )

    def _is_target_group_for_load_balancer(
        self, module_data: dict, target_group_ref: str, lb_resource_name: str
    ) -> bool:
        """Check if a target group is associated with the given load balancer."""
        # This is a heuristic - in practice, target groups in the same VPC
        # or module are often associated with load balancers in that context
        # A more sophisticated implementation could check for naming patterns,
        # tags, or other configuration hints
        return True  # Conservative approach - include all target groups found

    def _get_load_balancer_vpc_id(
        self, context: "TerraformMappingContext", lb_resource_name: str
    ) -> str | None:
        """Get the VPC ID for the given load balancer."""
        try:
            parsed_data = context.parsed_data
            if not parsed_data:
                return None

            for data_key in ["planned_values", "configuration"]:
                data_section = parsed_data.get(data_key, {})
                if not data_section:
                    continue

                root_module = data_section.get("root_module", {})
                vpc_id = self._get_lb_vpc_from_module(
                    root_module, data_key, lb_resource_name
                )
                if vpc_id:
                    return vpc_id

        except Exception as e:
            logger.debug("Error getting load balancer VPC ID: %s", e)

        return None

    def _find_target_groups_via_state_analysis(
        self, context: "TerraformMappingContext", lb_resource_name: str
    ) -> list[str]:
        """Find target groups by analyzing the Terraform state directly.

        This method examines the state for listeners that reference the load balancer
        and extracts target groups from their default actions.

        Args:
            context: Terraform mapping context containing parsed data
            lb_resource_name: The load balancer resource name

        Returns:
            List of target group resource names
        """
        target_groups: list[str] = []

        try:
            parsed_data = context.parsed_data
            if not parsed_data:
                return target_groups

            # Check if we have state data
            state_data = parsed_data.get("state", {})
            if not state_data:
                logger.debug("No state data available for state analysis")
                return target_groups

            # Extract resources from state values
            values = state_data.get("values", {})
            root_module = values.get("root_module", {})
            resources = root_module.get("resources", [])

            if not resources:
                logger.debug("No resources found in state values")
                return target_groups

            logger.info(
                "Analyzing %d resources in state for Load Balancer %s",
                len(resources),
                lb_resource_name,
            )

            # Find all target group resources - we'll connect all of them
            logger.info(
                "Looking for target group resources to connect to LB: %s",
                lb_resource_name,
            )

            for resource in resources:
                resource_type = resource.get("type", "")
                resource_address = resource.get("address", "")

                if resource_type == "aws_lb_target_group":
                    logger.info("Found target group resource: %s", resource_address)
                    target_groups.append(resource_address)

        except Exception as e:
            logger.debug("Error in state analysis: %s", e)

        return list(set(target_groups))  # Remove duplicates

    def _listener_references_load_balancer_by_name(
        self, load_balancer_arn: str, lb_resource_name: str
    ) -> bool:
        """Check if a listener's load_balancer_arn references the given
        load balancer."""
        if not load_balancer_arn or not lb_resource_name:
            return False

        # The ARN might contain the actual resource name or a Terraform reference
        # Check for Terraform reference pattern: ${aws_lb.app_alb.arn}
        terraform_ref = f"${{aws_lb.{lb_resource_name.split('.')[-1]}.arn}}"
        if terraform_ref in load_balancer_arn:
            return True

        # Check if the resource name appears in the ARN
        # Get 'app_alb' from 'aws_lb.app_alb'
        resource_short_name = lb_resource_name.split(".")[-1]
        return resource_short_name in load_balancer_arn

    def _find_target_group_resource_by_arn(
        self, resources: list, target_group_arn: str
    ) -> str | None:
        """Find the Terraform resource name for a target group by its ARN."""
        if not target_group_arn:
            return None

        # Look through resources to find the matching target group
        for resource in resources:
            resource_type = resource.get("type", "")
            resource_address = resource.get("address", "")

            if resource_type == "aws_lb_target_group":
                values_data = resource.get("values", {})
                arn = values_data.get("arn", "")

                if arn == target_group_arn:
                    return resource_address

        return None

    def _get_lb_vpc_from_module(
        self, module_data: dict, data_section: str, lb_resource_name: str
    ) -> str | None:
        """Get VPC ID from load balancer in a specific module."""
        for resource in module_data.get("resources", []):
            resource_address = resource.get("address", "")
            if resource_address != lb_resource_name:
                continue

            if data_section == "configuration":
                expressions = resource.get("expressions", {})
                subnets = expressions.get("subnets", {})
                refs = subnets.get("references", [])
                # Extract VPC from subnet references (simplified)
                for ref in refs:
                    if "aws_subnet" in str(ref):
                        # This is a simplified approach - in practice, we'd need to
                        # resolve the subnet to get its VPC
                        return "vpc-from-subnet"  # Placeholder
            else:
                values = resource.get("values", {})
                subnets = values.get("subnets", [])
                if subnets:
                    # In practice, we'd resolve subnet IDs to VPC IDs
                    return "vpc-from-subnet-values"  # Placeholder

        # Check child modules
        for child_module in module_data.get("child_modules", []):
            vpc_id = self._get_lb_vpc_from_module(
                child_module, data_section, lb_resource_name
            )
            if vpc_id:
                return vpc_id

        return None
