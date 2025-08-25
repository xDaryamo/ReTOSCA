import inspect
import logging
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper
from src.plugins.terraform.mapper import TerraformMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder

logger = logging.getLogger(__name__)


class AWSLoadBalancerMapper(SingleResourceMapper):
    """Map Terraform AWS Load Balancer (aws_lb) resources to TOSCA LoadBalancer nodes.

    Supports all AWS Load Balancer types:
    - Application Load Balancer (ALB)
    - Network Load Balancer (NLB)
    - Gateway Load Balancer (GWLB)
    """

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Return True for AWS Load Balancer resource types."""
        return resource_type in ["aws_lb"]

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
    ) -> None:
        """Translate AWS Load Balancer resources into TOSCA LoadBalancer nodes.

        Args:
            resource_name: resource name (e.g. 'aws_lb.test')
            resource_type: resource type ('aws_lb')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
        """
        logger.info("Mapping AWS Load Balancer resource: '%s'", resource_name)

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

        # Create the Load Balancer node
        lb_node = builder.add_node(name=node_name, node_type="LoadBalancer")

        # Extract key properties
        lb_name = values.get("name", "")
        lb_type = values.get("load_balancer_type", "application")
        internal = values.get("internal", False)
        ip_address_type = values.get("ip_address_type", "ipv4")

        # Build metadata with Terraform and AWS information
        metadata = self._build_metadata(
            resource_type, clean_name, resource_data, values, lb_type, internal
        )

        # Attach metadata to the node
        lb_node.with_metadata(metadata)

        # Set LoadBalancer properties
        self._set_load_balancer_properties(lb_node, values, lb_type, lb_name)

        # Add capabilities based on load balancer type and configuration
        self._add_load_balancer_capabilities(lb_node, values, internal, ip_address_type)

        # Add dependencies (VPC, subnets, security groups)
        self._add_dependencies(lb_node, resource_data, node_name)

        logger.debug("AWS Load Balancer node '%s' created successfully.", node_name)

        # Debug: mapped properties
        self._log_mapped_properties(node_name, values, metadata)

    def _build_metadata(
        self,
        resource_type: str,
        clean_name: str,
        resource_data: dict[str, Any],
        values: dict[str, Any],
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
        if lb_type == "application":
            metadata["description"] = (
                "AWS Application Load Balancer (ALB) for HTTP/HTTPS traffic "
                "distribution"
            )
        elif lb_type == "network":
            metadata["description"] = (
                "AWS Network Load Balancer (NLB) for TCP/UDP traffic distribution"
            )
        elif lb_type == "gateway":
            metadata["description"] = (
                "AWS Gateway Load Balancer (GWLB) for third-party virtual appliances"
            )
        else:
            metadata["description"] = "AWS Load Balancer for traffic distribution"

        # Provider information
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # AWS specific properties
        region = values.get("region")
        if region:
            metadata["aws_region"] = region

        # Access logs configuration
        access_logs = values.get("access_logs", [])
        if access_logs:
            metadata["aws_access_logs"] = access_logs

        # Connection logs (ALB only)
        connection_logs = values.get("connection_logs", [])
        if connection_logs:
            metadata["aws_connection_logs"] = connection_logs

        # Tags
        tags = values.get("tags", {})
        if tags:
            metadata["aws_tags"] = tags

        tags_all = values.get("tags_all", {})
        if tags_all and tags_all != tags:
            metadata["aws_tags_all"] = tags_all

        # Advanced settings
        deletion_protection = values.get("enable_deletion_protection", False)
        if deletion_protection:
            metadata["aws_deletion_protection_enabled"] = deletion_protection

        # ALB specific features
        if lb_type == "application":
            http2_enabled = values.get("enable_http2", True)
            metadata["aws_http2_enabled"] = http2_enabled

            drop_invalid_headers = values.get("drop_invalid_header_fields", False)
            if drop_invalid_headers:
                metadata["aws_drop_invalid_header_fields"] = drop_invalid_headers

            idle_timeout = values.get("idle_timeout", 60)
            if idle_timeout != 60:
                metadata["aws_idle_timeout"] = idle_timeout

        # Cross-zone load balancing
        cross_zone = values.get("enable_cross_zone_load_balancing")
        if cross_zone is not None:
            metadata["aws_cross_zone_load_balancing"] = cross_zone

        # IP address type
        ip_address_type = values.get("ip_address_type", "ipv4")
        if ip_address_type != "ipv4":
            metadata["aws_ip_address_type"] = ip_address_type

        return metadata

    def _set_load_balancer_properties(
        self,
        lb_node,
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
        lb_node,
        values: dict[str, Any],
        internal: bool,
        ip_address_type: str,
    ) -> None:
        """Add appropriate capabilities to the LoadBalancer node."""
        # Add client capability - this is where clients connect to the LB
        client_capability = lb_node.add_capability("client")

        # Configure endpoint properties based on internal/external and IP type
        if not internal:
            # External load balancer - accessible from internet
            client_capability.with_property("network_name", "PUBLIC")
        else:
            # Internal load balancer - only accessible from VPC
            client_capability.with_property("network_name", "PRIVATE")

        # Configure protocol and security based on load balancer type
        lb_type = values.get("load_balancer_type", "application")

        if lb_type == "application":
            # ALB typically handles HTTP/HTTPS
            client_capability.with_property("protocol", "http")
            client_capability.with_property("port", 80)
            # Can be overridden by HTTPS listeners
            client_capability.with_property("secure", False)
        elif lb_type == "network":
            # NLB can handle any TCP/UDP protocol
            client_capability.with_property("protocol", "tcp")
            # Port will be defined by listeners
        else:
            # Gateway LB or unknown type
            client_capability.with_property("protocol", "tcp")

        client_capability.and_node()

    def _add_dependencies(
        self,
        lb_node,
        resource_data: dict[str, Any],
        node_name: str,
    ) -> None:
        """Add dependency relationships to VPC, subnets, and security groups."""
        # Access the full plan via the TerraformMapper instance
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
            logger.warning(
                "Unable to access Terraform plan data to detect dependencies for '%s'",
                node_name,
            )
            return

        if not parsed_data:
            return

        # Extract Terraform references
        terraform_refs = TerraformMapper.extract_terraform_references(
            resource_data, parsed_data
        )

        added_dependencies = set()

        for prop_name, target_ref, _relationship_type in terraform_refs:
            # Subnet dependencies
            if prop_name in ["subnets", "subnet_id"] and "aws_subnet" in target_ref:
                target_node_name = BaseResourceMapper.generate_tosca_node_name(
                    target_ref, "aws_subnet"
                )

                if target_node_name not in added_dependencies:
                    lb_node.add_requirement("dependency").to_node(
                        target_node_name
                    ).with_relationship("DependsOn").and_node()

                    added_dependencies.add(target_node_name)
                    logger.debug(
                        "Added subnet dependency: %s -> %s",
                        node_name,
                        target_node_name,
                    )

            # Security group dependencies (ALB and NLB only)
            elif prop_name == "security_groups" and "aws_security_group" in target_ref:
                target_node_name = BaseResourceMapper.generate_tosca_node_name(
                    target_ref, "aws_security_group"
                )

                if target_node_name not in added_dependencies:
                    lb_node.add_requirement("dependency").to_node(
                        target_node_name
                    ).with_relationship("DependsOn").and_node()

                    added_dependencies.add(target_node_name)
                    logger.debug(
                        "Added security group dependency: %s -> %s",
                        node_name,
                        target_node_name,
                    )

        # Add VPC dependency through subnet references
        # (Load balancers don't directly reference VPC, but inherit it through subnets)
        logger.debug(
            "Load balancer dependencies added: %d total", len(added_dependencies)
        )

    def _log_mapped_properties(
        self,
        node_name: str,
        values: dict[str, Any],
        metadata: dict[str, Any],
    ) -> None:
        """Log the mapped properties for debugging."""
        if logger.isEnabledFor(logging.DEBUG):
            lb_name = values.get("name", "")
            lb_type = values.get("load_balancer_type", "application")
            internal = values.get("internal", False)
            region = values.get("region", "")
            tags = values.get("tags", {})

            logger.debug(
                "Mapped properties for '%s':\n"
                "  - Name: %s\n"
                "  - Type: %s\n"
                "  - Internal: %s\n"
                "  - Region: %s\n"
                "  - Tags: %s\n"
                "  - Access Control: %s\n"
                "  - Deletion Protection: %s",
                node_name,
                lb_name,
                lb_type,
                internal,
                region,
                tags,
                "Private" if internal else "Public",
                metadata.get("aws_deletion_protection_enabled", False),
            )
