import logging
import re
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder
    from src.plugins.terraform.context import TerraformMappingContext

logger = logging.getLogger(__name__)


class AWSInstanceMapper(SingleResourceMapper):
    """Map a Terraform 'aws_instance' resource to a TOSCA Compute node."""

    def __init__(self):
        """Initialize the mapper with AWS instance type specifications.

        The database is a small reference of instance sizes used to infer
        capabilities (vCPU, memory) when possible.
        """
        super().__init__()
        # Database of AWS instance type specifications
        # Based on: https://aws.amazon.com/ec2/instance-types/
        self._instance_specs = {
            # T2 instances - Burstable Performance (previous generation)
            "t2.nano": {
                "vcpu": 1,
                "memory_gb": 0.5,
                "network_performance": "Low to Moderate",
            },
            "t2.micro": {
                "vcpu": 1,
                "memory_gb": 1,
                "network_performance": "Low to Moderate",
            },
            "t2.small": {
                "vcpu": 1,
                "memory_gb": 2,
                "network_performance": "Low to Moderate",
            },
            "t2.medium": {
                "vcpu": 2,
                "memory_gb": 4,
                "network_performance": "Low to Moderate",
            },
            "t2.large": {
                "vcpu": 2,
                "memory_gb": 8,
                "network_performance": "Low to Moderate",
            },
            "t2.xlarge": {
                "vcpu": 4,
                "memory_gb": 16,
                "network_performance": "Moderate",
            },
            "t2.2xlarge": {
                "vcpu": 8,
                "memory_gb": 32,
                "network_performance": "Moderate",
            },
            # T3 instances - Burstable Performance
            "t3.nano": {
                "vcpu": 2,
                "memory_gb": 0.5,
                "network_performance": "Up to 5 Gigabit",
            },
            "t3.micro": {
                "vcpu": 2,
                "memory_gb": 1,
                "network_performance": "Up to 5 Gigabit",
            },
            "t3.small": {
                "vcpu": 2,
                "memory_gb": 2,
                "network_performance": "Up to 5 Gigabit",
            },
            "t3.medium": {
                "vcpu": 2,
                "memory_gb": 4,
                "network_performance": "Up to 5 Gigabit",
            },
            "t3.large": {
                "vcpu": 2,
                "memory_gb": 8,
                "network_performance": "Up to 5 Gigabit",
            },
            "t3.xlarge": {
                "vcpu": 4,
                "memory_gb": 16,
                "network_performance": "Up to 5 Gigabit",
            },
            "t3.2xlarge": {
                "vcpu": 8,
                "memory_gb": 32,
                "network_performance": "Up to 5 Gigabit",
            },
            # T4g instances - ARM-based Graviton2
            "t4g.nano": {
                "vcpu": 2,
                "memory_gb": 0.5,
                "network_performance": "Up to 5 Gigabit",
            },
            "t4g.micro": {
                "vcpu": 2,
                "memory_gb": 1,
                "network_performance": "Up to 5 Gigabit",
            },
            "t4g.small": {
                "vcpu": 2,
                "memory_gb": 2,
                "network_performance": "Up to 5 Gigabit",
            },
            "t4g.medium": {
                "vcpu": 2,
                "memory_gb": 4,
                "network_performance": "Up to 5 Gigabit",
            },
            "t4g.large": {
                "vcpu": 2,
                "memory_gb": 8,
                "network_performance": "Up to 5 Gigabit",
            },
            "t4g.xlarge": {
                "vcpu": 4,
                "memory_gb": 16,
                "network_performance": "Up to 5 Gigabit",
            },
            "t4g.2xlarge": {
                "vcpu": 8,
                "memory_gb": 32,
                "network_performance": "Up to 5 Gigabit",
            },
            # M6i instances - General Purpose (Intel)
            "m6i.large": {
                "vcpu": 2,
                "memory_gb": 8,
                "network_performance": "Up to 12.5 Gigabit",
            },
            "m6i.xlarge": {
                "vcpu": 4,
                "memory_gb": 16,
                "network_performance": "Up to 12.5 Gigabit",
            },
            "m6i.2xlarge": {
                "vcpu": 8,
                "memory_gb": 32,
                "network_performance": "Up to 12.5 Gigabit",
            },
            "m6i.4xlarge": {
                "vcpu": 16,
                "memory_gb": 64,
                "network_performance": "Up to 12.5 Gigabit",
            },
            "m6i.8xlarge": {
                "vcpu": 32,
                "memory_gb": 128,
                "network_performance": "12.5 Gigabit",
            },
            "m6i.12xlarge": {
                "vcpu": 48,
                "memory_gb": 192,
                "network_performance": "18.75 Gigabit",
            },
            "m6i.16xlarge": {
                "vcpu": 64,
                "memory_gb": 256,
                "network_performance": "25 Gigabit",
            },
            "m6i.24xlarge": {
                "vcpu": 96,
                "memory_gb": 384,
                "network_performance": "37.5 Gigabit",
            },
            "m6i.32xlarge": {
                "vcpu": 128,
                "memory_gb": 512,
                "network_performance": "50 Gigabit",
            },
            # C6i instances - Compute Optimized (Intel)
            "c6i.large": {
                "vcpu": 2,
                "memory_gb": 4,
                "network_performance": "Up to 12.5 Gigabit",
            },
            "c6i.xlarge": {
                "vcpu": 4,
                "memory_gb": 8,
                "network_performance": "Up to 12.5 Gigabit",
            },
            "c6i.2xlarge": {
                "vcpu": 8,
                "memory_gb": 16,
                "network_performance": "Up to 12.5 Gigabit",
            },
            "c6i.4xlarge": {
                "vcpu": 16,
                "memory_gb": 32,
                "network_performance": "Up to 12.5 Gigabit",
            },
            "c6i.8xlarge": {
                "vcpu": 32,
                "memory_gb": 64,
                "network_performance": "12.5 Gigabit",
            },
            "c6i.12xlarge": {
                "vcpu": 48,
                "memory_gb": 96,
                "network_performance": "18.75 Gigabit",
            },
            "c6i.16xlarge": {
                "vcpu": 64,
                "memory_gb": 128,
                "network_performance": "25 Gigabit",
            },
            "c6i.24xlarge": {
                "vcpu": 96,
                "memory_gb": 192,
                "network_performance": "37.5 Gigabit",
            },
            "c6i.32xlarge": {
                "vcpu": 128,
                "memory_gb": 256,
                "network_performance": "50 Gigabit",
            },
            # C6a instances - Compute Optimized (AMD)
            "c6a.large": {
                "vcpu": 2,
                "memory_gb": 4,
                "network_performance": "Up to 12.5 Gigabit",
            },
            "c6a.xlarge": {
                "vcpu": 4,
                "memory_gb": 8,
                "network_performance": "Up to 12.5 Gigabit",
            },
            "c6a.2xlarge": {
                "vcpu": 8,
                "memory_gb": 16,
                "network_performance": "Up to 12.5 Gigabit",
            },
            "c6a.4xlarge": {
                "vcpu": 16,
                "memory_gb": 32,
                "network_performance": "Up to 12.5 Gigabit",
            },
            "c6a.8xlarge": {
                "vcpu": 32,
                "memory_gb": 64,
                "network_performance": "12.5 Gigabit",
            },
            "c6a.12xlarge": {
                "vcpu": 48,
                "memory_gb": 96,
                "network_performance": "18.75 Gigabit",
            },
            "c6a.16xlarge": {
                "vcpu": 64,
                "memory_gb": 128,
                "network_performance": "25 Gigabit",
            },
            "c6a.24xlarge": {
                "vcpu": 96,
                "memory_gb": 192,
                "network_performance": "37.5 Gigabit",
            },
            "c6a.32xlarge": {
                "vcpu": 128,
                "memory_gb": 256,
                "network_performance": "50 Gigabit",
            },
            # R6i instances - Memory Optimized (Intel)
            "r6i.large": {
                "vcpu": 2,
                "memory_gb": 16,
                "network_performance": "Up to 12.5 Gigabit",
            },
            "r6i.xlarge": {
                "vcpu": 4,
                "memory_gb": 32,
                "network_performance": "Up to 12.5 Gigabit",
            },
            "r6i.2xlarge": {
                "vcpu": 8,
                "memory_gb": 64,
                "network_performance": "Up to 12.5 Gigabit",
            },
            "r6i.4xlarge": {
                "vcpu": 16,
                "memory_gb": 128,
                "network_performance": "Up to 12.5 Gigabit",
            },
            "r6i.8xlarge": {
                "vcpu": 32,
                "memory_gb": 256,
                "network_performance": "12.5 Gigabit",
            },
            "r6i.12xlarge": {
                "vcpu": 48,
                "memory_gb": 384,
                "network_performance": "18.75 Gigabit",
            },
            "r6i.16xlarge": {
                "vcpu": 64,
                "memory_gb": 512,
                "network_performance": "25 Gigabit",
            },
            "r6i.24xlarge": {
                "vcpu": 96,
                "memory_gb": 768,
                "network_performance": "37.5 Gigabit",
            },
            "r6i.32xlarge": {
                "vcpu": 128,
                "memory_gb": 1024,
                "network_performance": "50 Gigabit",
            },
        }

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """Mapper specific to the resource type 'aws_instance'."""
        return resource_type == "aws_instance"

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Translate an aws_instance into a TOSCA Compute node.

        Args:
            resource_name: resource name (e.g. 'aws_instance.web')
            resource_type: resource type (always 'aws_instance')
            resource_data: resource data from the Terraform plan
            builder: ServiceTemplateBuilder used to build the TOSCA template
            context: TerraformMappingContext for variable resolution
        """
        logger.info(f"Mapping EC2 Instance resource: '{resource_name}'")

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

        # Create the main Compute node
        compute_node = builder.add_node(name=node_name, node_type="Compute")

        # Extract relevant AWS instance properties
        ami = values.get("ami")
        instance_type = values.get("instance_type")
        cpu_options = values.get("cpu_options", [])

        # Infer compute capabilities from the AWS instance type and cpu_options
        if instance_type:
            self._add_compute_capabilities(
                compute_node, instance_type, ami, cpu_options, context
            )

        # Get resolved values specifically for metadata (always concrete values)
        if context:
            metadata_values = context.get_resolved_values(resource_data, "metadata")
        else:
            metadata_values = resource_data.get("values", {})

        # Add endpoint capabilities for services running on the instance
        self._add_endpoint_capabilities(compute_node, values, metadata_values, context)

        # Build comprehensive metadata with Terraform and AWS information
        metadata: dict[str, Any] = {}

        # Original resource information
        # Only the name, without the aws_instance prefix
        metadata["original_resource_type"] = resource_type
        metadata["original_resource_name"] = clean_name

        # Information from resource_data if available
        provider_name = resource_data.get("provider_name")
        if provider_name:
            metadata["aws_provider"] = provider_name

        # AWS information extracted from metadata values for concrete resolution
        metadata_region = metadata_values.get("region")
        if metadata_region:
            metadata["aws_region"] = metadata_region

        metadata_instance_type = metadata_values.get("instance_type")
        if metadata_instance_type:
            metadata["aws_instance_type"] = metadata_instance_type

        metadata_ami = metadata_values.get("ami")
        if metadata_ami:
            metadata["aws_ami"] = metadata_ami

        # Additional AWS info for extra metadata - use metadata values for
        # concrete resolution
        metadata_user_data = metadata_values.get("user_data")
        if metadata_user_data:
            metadata["aws_user_data"] = metadata_user_data

        metadata_monitoring = metadata_values.get("monitoring")
        if metadata_monitoring is not None:
            metadata["aws_monitoring"] = metadata_monitoring

        metadata_get_password_data = metadata_values.get("get_password_data", False)
        if metadata_get_password_data:
            metadata["aws_get_password_data"] = metadata_get_password_data

        metadata_source_dest_check = metadata_values.get("source_dest_check", True)
        if not metadata_source_dest_check:
            metadata["aws_source_dest_check"] = metadata_source_dest_check

        metadata_hibernation = metadata_values.get("hibernation")
        if metadata_hibernation is not None:
            metadata["aws_hibernation"] = metadata_hibernation

        # Credit specification for burstable instances (t2, t3, t4g, etc.)
        metadata_credit_specification = metadata_values.get("credit_specification", [])
        if metadata_credit_specification:
            metadata["aws_credit_specification"] = metadata_credit_specification

        # Launch template if specified
        metadata_launch_template = metadata_values.get("launch_template", [])
        if metadata_launch_template:
            metadata["aws_launch_template"] = metadata_launch_template

        # Volume tags
        metadata_volume_tags = metadata_values.get("volume_tags")
        if metadata_volume_tags:
            metadata["aws_volume_tags"] = metadata_volume_tags

        # Timeouts
        metadata_timeouts = metadata_values.get("timeouts")
        if metadata_timeouts:
            metadata["terraform_timeouts"] = metadata_timeouts

        # Tags
        metadata_tags = metadata_values.get("tags", {})
        if metadata_tags:
            metadata["aws_tags"] = metadata_tags

        # tags_all (all tags including provider-level tags)
        metadata_tags_all = metadata_values.get("tags_all", {})
        if metadata_tags_all and metadata_tags_all != metadata_tags:
            metadata["aws_tags_all"] = metadata_tags_all

        # Add all collected metadata to the node
        compute_node.with_metadata(metadata)

        # Add dependencies using injected context with filtering
        if context:
            # Create dependency filter to exclude AMI references
            from src.plugins.terraform.context import DependencyFilter

            dependency_filter = DependencyFilter(
                exclude_properties={"ami", "source_ami", "image_id"}
            )

            terraform_refs = context.extract_filtered_terraform_references(
                resource_data, dependency_filter
            )
            logger.debug(
                f"Found {len(terraform_refs)} terraform references for "
                f"{resource_name} (AMI references filtered out)"
            )

            for prop_name, target_ref, relationship_type in terraform_refs:
                logger.debug(
                    "Processing reference: %s -> %s (%s)",
                    prop_name,
                    target_ref,
                    relationship_type,
                )

                if "." in target_ref:
                    # target_ref like "aws_subnet.main" or "aws_security_group.web-sg"
                    target_resource_type = target_ref.split(".", 1)[0]
                    target_node_name = BaseResourceMapper.generate_tosca_node_name(
                        target_ref, target_resource_type
                    )

                    # Add requirement with the property name as the requirement name
                    requirement_name = (
                        prop_name if prop_name not in ["dependency"] else "dependency"
                    )

                    (
                        compute_node.add_requirement(requirement_name)
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

        logger.debug("EC2 Compute node '%s' created successfully.", node_name)

        # Debug: mapped properties - use metadata values for concrete display
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Mapped properties for '%s':", node_name)
            logger.debug("  - AMI: %s", metadata_ami)
            logger.debug("  - Instance Type: %s", metadata_instance_type)
            logger.debug("  - Region: %s", metadata_region)
            logger.debug("  - Tags: %s", metadata_tags)
            if metadata_user_data:
                if len(str(metadata_user_data)) > 100:
                    logger.debug("  - User Data: %s...", str(metadata_user_data)[:100])
                else:
                    logger.debug("  - User Data: %s", metadata_user_data)

    def _add_compute_capabilities(
        self,
        compute_node,
        instance_type: str,
        ami: str | None = None,
        cpu_options: list[dict[str, Any]] | None = None,
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Add capabilities to the Compute node based on the instance type.

        Args:
            compute_node: The TOSCA compute node to enhance
            instance_type: AWS instance type (e.g., 'c6a.2xlarge')
            ami: AMI ID for OS capability inference
            cpu_options: List of CPU option dictionaries from Terraform
            context: TerraformMappingContext for AMI data extraction

        Only capabilities with meaningful properties are added. Empty
        capabilities are omitted.
        """
        # Capability "host" with instance specifications (always present)
        if instance_type and instance_type in self._instance_specs:
            specs = self._instance_specs[instance_type]

            # Calculate actual vCPU count considering cpu_options override
            actual_vcpu = self._calculate_actual_vcpu(specs["vcpu"], cpu_options)

            # Use GB instead of MB for readability
            memory_gb = specs["memory_gb"]
            if memory_gb < 1:
                mem_size = f"{int(memory_gb * 1024)} MB"
            else:
                mem_size = f"{memory_gb} GB"

            (
                compute_node.add_capability("host")
                .with_property("num_cpus", actual_vcpu)
                .with_property("mem_size", mem_size)
                .and_node()
            )

            logger.debug(
                "Configured capabilities for '%s': %s vCPU, %s GB RAM",
                instance_type,
                actual_vcpu,
                memory_gb,
            )
        else:
            logger.warning(
                "Specs not found for instance type '%s'. Using default capabilities.",
                instance_type,
            )
            (
                compute_node.add_capability("host")
                .with_property("num_cpus", 1)
                .with_property("mem_size", "1 GB")
                .and_node()
            )

        # Capability "os" with information inferred from the AMI (if any)
        # Pass context for AMI data extraction, fallback to pattern matching if
        # context unavailable
        os_props = self._infer_os_from_ami(ami, context)
        if os_props:
            os_capability = compute_node.add_capability("os")
            for prop_name, prop_value in os_props.items():
                os_capability.with_property(prop_name, prop_value)
            os_capability.and_node()

        # Do not add empty capabilities (scalable, binding)

    def _add_endpoint_capabilities(
        self,
        compute_node,
        values: dict[str, Any],
        metadata_values: dict[str, Any],
        context: "TerraformMappingContext | None" = None,
    ) -> None:
        """Add endpoint capabilities for services running on the instance.

        Args:
            compute_node: The TOSCA compute node to enhance
            values: Instance configuration values (resolved for properties)
            metadata_values: Instance configuration values (resolved for metadata)
            context: TerraformMappingContext for additional analysis
        """
        # Detect service ports from various sources
        service_ports = self._detect_service_ports(values, metadata_values, context)

        # Create endpoint capabilities for each detected service port
        for port_info in service_ports:
            port = port_info["port"]
            protocol = port_info.get("protocol", "http")
            service_name = port_info.get("service_name", f"service-{port}")

            logger.debug(
                "Adding endpoint capability for service '%s' on port %d (%s)",
                service_name,
                port,
                protocol,
            )

            # Create TOSCA-compliant endpoint capability name
            if port == 22:
                endpoint_name = "admin_endpoint"
            else:
                endpoint_name = "endpoint"

            (
                compute_node.add_capability(endpoint_name)
                .with_property("protocol", protocol)
                .with_property("port", port)
                .with_property("secure", protocol == "https")
                .and_node()
            )

            logger.info(
                "Added endpoint capability '%s' for port %d on instance",
                endpoint_name,
                port,
            )

    def _detect_service_ports(
        self,
        values: dict[str, Any],
        metadata_values: dict[str, Any],
        context: "TerraformMappingContext | None" = None,
    ) -> list[dict[str, Any]]:
        """Detect service ports from user_data, security groups, and
        target group attachments.

        Args:
            values: Instance configuration values (resolved for properties)
            metadata_values: Instance configuration values (resolved for metadata)
            context: TerraformMappingContext for additional analysis

        Returns:
            List of dictionaries with port information
        """
        detected_ports = []

        # 1. Analyze user_data for service ports
        user_data = metadata_values.get("user_data") or values.get("user_data")
        if user_data:
            user_data_ports = self._extract_ports_from_user_data(user_data)
            detected_ports.extend(user_data_ports)

        # 2. Analyze security group rules (if available via context)
        if context:
            sg_ports = self._extract_ports_from_security_groups(values, context)
            detected_ports.extend(sg_ports)

        # 3. Analyze target group attachments (if available via context)
        if context:
            tg_ports = self._extract_ports_from_target_group_attachments(
                context, values
            )
            detected_ports.extend(tg_ports)

        # Remove duplicates and return
        unique_ports = []
        seen_ports = set()
        for port_info in detected_ports:
            port = port_info["port"]
            if port not in seen_ports:
                unique_ports.append(port_info)
                seen_ports.add(port)

        logger.debug("Detected service ports: %s", unique_ports)
        return unique_ports

    def _extract_ports_from_user_data(self, user_data: str) -> list[dict[str, Any]]:
        """Extract service ports from EC2 user_data script.

        Args:
            user_data: User data script content

        Returns:
            List of port information dictionaries
        """
        ports = []

        # Common patterns for port specifications in scripts
        patterns = [
            r"-p\s+(\d+)",  # nc -l -p 8080, netcat style
            r"--port\s+(\d+)",  # --port 8080
            r"port\s*=\s*(\d+)",  # port=8080
            r":(\d+)",  # :8080 in URLs or bind addresses
            r"listen\s+(\d+)",  # listen 8080
            r"PORT\s*=\s*(\d+)",  # PORT=8080 environment variable
        ]

        for pattern in patterns:
            matches = re.findall(pattern, user_data, re.IGNORECASE)
            for match in matches:
                try:
                    port = int(match)
                    # Filter reasonable port ranges
                    if 1024 <= port <= 65535:  # Non-privileged ports
                        # Infer protocol based on common port conventions
                        protocol = "http"
                        if port == 443 or port == 8443:
                            protocol = "https"
                        elif port in [3306, 5432, 6379, 27017]:  # Database ports
                            protocol = "tcp"

                        service_name = f"service-{port}"
                        # Try to infer service name from context
                        if port == 8080:
                            service_name = "web-service"
                        elif port == 3000:
                            service_name = "node-app"
                        elif port == 8000:
                            service_name = "django-app"

                        ports.append(
                            {
                                "port": port,
                                "protocol": protocol,
                                "service_name": service_name,
                                "source": "user_data",
                            }
                        )

                        logger.debug(
                            "Detected port %d from user_data (%s)", port, service_name
                        )
                except ValueError:
                    continue  # Skip invalid port numbers

        return ports

    def _extract_ports_from_security_groups(
        self, values: dict[str, Any], context: "TerraformMappingContext"
    ) -> list[dict[str, Any]]:
        """Extract service ports from security group ingress rules.

        Args:
            values: Instance configuration values
            context: TerraformMappingContext for security group lookup

        Returns:
            List of port information dictionaries
        """
        ports: list[dict[str, Any]] = []

        # Get security group IDs from the instance
        security_group_ids = values.get("vpc_security_group_ids", [])
        if not security_group_ids:
            return ports

        # Look up security groups in the parsed data
        parsed_data = context.parsed_data

        # Search in both planned_values and configuration sections
        for data_key in ["planned_values", "configuration"]:
            data_section = parsed_data.get(data_key, {})
            if not data_section:
                continue

            root_module = data_section.get("root_module", {})
            if not root_module:
                continue

            for resource in root_module.get("resources", []):
                if resource.get("type") != "aws_security_group":
                    continue

                # Check if this security group is attached to our instance
                sg_address = resource.get("address", "")
                sg_values = resource.get("values", {})

                # Extract ingress rules
                if data_key == "configuration":
                    # In configuration, ingress rules are in expressions
                    expressions = resource.get("expressions", {})
                    ingress_rules = expressions.get("ingress", [])
                else:
                    # In planned_values, ingress rules are in values
                    ingress_rules = sg_values.get("ingress", [])

                for rule in ingress_rules:
                    if isinstance(rule, dict):
                        from_port = rule.get("from_port")
                        to_port = rule.get("to_port")
                        protocol = rule.get("protocol", "tcp")

                        if from_port and to_port and from_port == to_port:
                            port = from_port if isinstance(from_port, int) else None
                            if port and 1024 <= port <= 65535:
                                ports.append(
                                    {
                                        "port": port,
                                        "protocol": (
                                            "http"
                                            if protocol == "tcp"
                                            and port in [80, 8080, 3000, 8000]
                                            else "tcp"
                                        ),
                                        "service_name": f"sg-service-{port}",
                                        "source": f"security_group_{sg_address}",
                                    }
                                )

        return ports

    def _extract_ports_from_target_group_attachments(
        self, context: "TerraformMappingContext", instance_values: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Extract service ports from target group attachments that
        reference this instance.

        Args:
            context: TerraformMappingContext for target group attachment lookup
            instance_values: Instance configuration values

        Returns:
            List of port information dictionaries
        """
        ports: list[dict[str, Any]] = []

        # This would require looking up target group attachments that
        # reference this instance
        # For now, we'll implement a simple version that looks for common
        # web service ports
        # A more complete implementation would traverse the terraform references

        parsed_data = context.parsed_data

        # Look for target group attachments in the configuration
        config_section = parsed_data.get("configuration", {})
        if config_section:
            root_module = config_section.get("root_module", {})
            for resource in root_module.get("resources", []):
                if resource.get("type") == "aws_lb_target_group_attachment":
                    expressions = resource.get("expressions", {})
                    port_expr = expressions.get("port", {})
                    port_value = port_expr.get("constant_value")

                    if isinstance(port_value, int) and 1024 <= port_value <= 65535:
                        ports.append(
                            {
                                "port": port_value,
                                "protocol": "http",
                                "service_name": f"target-group-service-{port_value}",
                                "source": "target_group_attachment",
                            }
                        )

        return ports

    def _calculate_actual_vcpu(
        self,
        default_vcpu: int,
        cpu_options: list[dict[str, Any]] | None,
    ) -> int:
        """Calculate actual vCPU count considering cpu_options override.

        Args:
            default_vcpu: Default vCPU count for the instance type
            cpu_options: List of CPU option dictionaries from Terraform

        Returns:
            Actual vCPU count (core_count * threads_per_core)
        """
        if not cpu_options or len(cpu_options) == 0:
            return default_vcpu

        # AWS cpu_options is typically a single element list
        cpu_config = cpu_options[0] if isinstance(cpu_options, list) else cpu_options

        # Extract core_count and threads_per_core
        core_count = cpu_config.get("core_count")
        threads_per_core = cpu_config.get("threads_per_core")

        if core_count is not None and threads_per_core is not None:
            actual_vcpu = core_count * threads_per_core
            logger.debug(
                "CPU options override: %s cores × %s threads = %s vCPU",
                core_count,
                threads_per_core,
                actual_vcpu,
            )
            return actual_vcpu

        logger.debug("No valid cpu_options found, using default vCPU: %s", default_vcpu)
        return default_vcpu

    def _infer_os_from_ami(
        self, ami: str | None, context: "TerraformMappingContext | None" = None
    ) -> dict[str, str]:
        """Infer operating system properties from the AMI.

        First tries to extract detailed info from the Terraform plan data,
        then falls back to basic pattern matching on the AMI ID.

        Returns:
            A dict with OS properties, empty if unable to infer.
        """
        if not ami:
            return {}

        # Try to get detailed AMI data from Terraform plan if context is available
        os_props = self._extract_ami_data_from_plan(ami, context)
        if os_props:
            return os_props

        # Fallback to basic pattern matching
        return self._infer_os_from_ami_pattern(ami)

    def _extract_ami_data_from_plan(
        self, ami: str, context: "TerraformMappingContext | None" = None
    ) -> dict[str, str]:
        """Extract OS information from AMI data in the Terraform plan.

        Returns:
            A dict with OS properties extracted from plan data.
        """
        if not context:
            logger.debug("No context provided for AMI information extraction")
            return {}

        parsed_data = context.parsed_data

        # Look for AMI data in prior_state (where data sources are stored)
        prior_state = parsed_data.get("prior_state", {})
        root_module = prior_state.get("values", {}).get("root_module", {})
        resources = root_module.get("resources", [])

        ami_data = None
        for resource in resources:
            if (
                resource.get("type") == "aws_ami"
                and resource.get("values", {}).get("id") == ami
            ):
                ami_data = resource.get("values", {})
                break

        if not ami_data:
            logger.debug("No detailed AMI data found in plan for AMI '%s'", ami)
            return {}

        os_props: dict[str, str] = {}

        # Extract architecture
        architecture = ami_data.get("architecture")
        if architecture:
            os_props["architecture"] = architecture

        # Extract platform information
        platform_details = ami_data.get("platform_details", "")
        platform = ami_data.get("platform", "")

        if platform_details:
            if "Windows" in platform_details:
                os_props["type"] = "windows"
            elif "Linux" in platform_details or "UNIX" in platform_details:
                os_props["type"] = "linux"

        # Extract distribution and version from name and description
        name = ami_data.get("name", "")
        description = ami_data.get("description", "")
        image_location = ami_data.get("image_location", "")

        # Parse Amazon Linux information
        if (
            "al2023" in name.lower()
            or "amazon linux 2023" in description.lower()
            or "amazon/" in image_location.lower()
        ):
            os_props["type"] = "linux"
            os_props["distribution"] = "amazon"

            # Extract version from name like
            # "al2023-ami-2023.8.20250818.0-kernel-6.1-x86_64"
            version_match = re.search(r"2023\.(\d+)\.(\d+)", name)
            if version_match:
                major, minor = version_match.groups()
                os_props["version"] = f"2023.{major}.{minor}"
            else:
                os_props["version"] = "2023.0.0"

        # Parse Ubuntu information
        elif "ubuntu" in name.lower() or "ubuntu" in description.lower():
            os_props["type"] = "linux"
            os_props["distribution"] = "ubuntu"

            # Extract Ubuntu version
            version_match = re.search(r"(\d{2})\.(\d{2})", name)
            if version_match:
                major, minor = version_match.groups()
                os_props["version"] = f"{major}.{minor}.0"

        # Parse RHEL information
        elif (
            "rhel" in name.lower()
            or "red hat" in description.lower()
            or "redhat" in description.lower()
        ):
            os_props["type"] = "linux"
            os_props["distribution"] = "rhel"

        # Parse CentOS information
        elif "centos" in name.lower() or "centos" in description.lower():
            os_props["type"] = "linux"
            os_props["distribution"] = "centos"

        # Parse Debian information
        elif "debian" in name.lower() or "debian" in description.lower():
            os_props["type"] = "linux"
            os_props["distribution"] = "debian"

        # Parse Windows information
        elif (
            "windows" in name.lower()
            or "windows" in description.lower()
            or platform == "windows"
        ):
            os_props["type"] = "windows"

            # Try to extract Windows version
            if "2022" in name or "2022" in description:
                os_props["version"] = "2022"
            elif "2019" in name or "2019" in description:
                os_props["version"] = "2019"
            elif "2016" in name or "2016" in description:
                os_props["version"] = "2016"

        # Additional metadata that might be useful are available in AMI data
        # (hypervisor, boot_mode, ena_support, sriov_net_support) but are not
        # part of TOSCA OperatingSystem capability standard

        if os_props:
            logger.debug(
                "Extracted OS properties from AMI data for '%s': %s", ami, os_props
            )

        return os_props

    def _infer_os_from_ami_pattern(self, ami: str) -> dict[str, str]:
        """Fallback method to infer OS from AMI ID pattern.

        Returns:
            A dict with OS properties inferred from patterns.
        """
        os_props: dict[str, str] = {}

        # Patterns to recognize different AMI types
        ami_lower = ami.lower()

        if "amazon" in ami_lower or "al2023" in ami_lower or "amzn" in ami_lower:
            os_props["type"] = "linux"
            os_props["distribution"] = "amazon"
            if "al2023" in ami_lower or "2023" in ami_lower:
                # semantic format major.minor.fix
                os_props["version"] = "2023.0.0"
        elif "ubuntu" in ami_lower:
            os_props["type"] = "linux"
            os_props["distribution"] = "ubuntu"
        elif "rhel" in ami_lower or "red-hat" in ami_lower:
            os_props["type"] = "linux"
            os_props["distribution"] = "rhel"
        elif "centos" in ami_lower:
            os_props["type"] = "linux"
            os_props["distribution"] = "centos"
        elif "debian" in ami_lower:
            os_props["type"] = "linux"
            os_props["distribution"] = "debian"
        elif "windows" in ami_lower:
            os_props["type"] = "windows"

        # Architecture
        if "x86_64" in ami_lower or "amd64" in ami_lower:
            os_props["architecture"] = "x86_64"
        elif "arm64" in ami_lower or "aarch64" in ami_lower:
            os_props["architecture"] = "arm64"
        else:
            # Default for modern AWS instances
            os_props["architecture"] = "x86_64"

        if os_props:
            logger.debug(
                "Inferred OS properties from AMI pattern '%s': %s", ami, os_props
            )

        return os_props

    def _generate_mount_point(self, device_name: str) -> str:
        """Generate a logical mount point from a device name.

        Args:
            device_name: Device name like '/dev/sdh', '/dev/xvdf', etc.

        Returns:
            A placeholder string indicating the mount point is unspecified.
        """
        return "unspecified"
