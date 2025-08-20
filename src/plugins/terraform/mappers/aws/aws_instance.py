import logging
from typing import TYPE_CHECKING, Any

from src.core.protocols import SingleResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder

logger = logging.getLogger(__name__)


class AWSInstanceMapper(SingleResourceMapper):
    """Map a Terraform 'aws_instance' resource to a TOSCA Compute node."""

    def __init__(self):
        """Initialize the mapper with AWS instance type specifications.

        The database is a small reference of instance sizes used to infer
        capabilities (vCPU, memory) when possible.
        """
        # Database of AWS instance type specifications
        # Based on: https://aws.amazon.com/ec2/instance-types/
        self._instance_specs = {
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
    ) -> None:
        """Translate an aws_instance into a TOSCA Compute node."""
        logger.info(f"Mapping EC2 Instance resource: '{resource_name}'")

        # The actual values are in the 'values' key of the plan JSON
        values = resource_data.get("values", {})
        if not values:
            logger.warning(
                "Resource '%s' has no 'values' section. Skipping.", resource_name
            )
            return

        # Generate a unique TOSCA node name using the utility function
        from core.common.base_mapper import BaseResourceMapper

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
        region = values.get("region")

        # Infer compute capabilities from the AWS instance type
        self._add_compute_capabilities(compute_node, instance_type, ami)

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

        # AWS information extracted from values
        if region:
            metadata["aws_region"] = region
        if instance_type:
            metadata["aws_instance_type"] = instance_type
        if ami:
            metadata["aws_ami"] = ami

        # Add all collected metadata to the node
        compute_node.with_metadata(metadata)

        # Additional AWS info for extra metadata
        user_data = values.get("user_data")
        monitoring = values.get("monitoring")
        get_password_data = values.get("get_password_data", False)
        source_dest_check = values.get("source_dest_check", True)
        hibernation = values.get("hibernation")
        tags = values.get("tags", {})

        if user_data:
            metadata["aws_user_data"] = user_data
        if monitoring is not None:
            metadata["aws_monitoring"] = monitoring
        if get_password_data:
            metadata["aws_get_password_data"] = get_password_data
        if not source_dest_check:
            metadata["aws_source_dest_check"] = source_dest_check
        if hibernation is not None:
            metadata["aws_hibernation"] = hibernation

        # Credit specification for burstable instances (t2, t3, t4g, etc.)
        credit_specification = values.get("credit_specification", [])
        if credit_specification:
            metadata["aws_credit_specification"] = credit_specification

        # Launch template if specified
        launch_template = values.get("launch_template", [])
        if launch_template:
            metadata["aws_launch_template"] = launch_template

        # Volume tags
        volume_tags = values.get("volume_tags")
        if volume_tags:
            metadata["aws_volume_tags"] = volume_tags

        # Timeouts
        timeouts = values.get("timeouts")
        if timeouts:
            metadata["terraform_timeouts"] = timeouts

        # tags_all (all tags including provider-level tags)
        tags_all = values.get("tags_all", {})
        if tags_all and tags_all != tags:
            metadata["terraform_tags_all"] = tags_all

        # Update the node metadata with the additional information
        compute_node.with_metadata(metadata)
        logger.debug("EC2 Compute node '%s' created successfully.", node_name)

        # Debug: mapped properties
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("Mapped properties for '%s':", node_name)
            logger.debug("  - AMI: %s", ami)
            logger.debug("  - Instance Type: %s", instance_type)
            logger.debug("  - Region: %s", region)
            logger.debug("  - Tags: %s", tags)
            if user_data:
                if len(str(user_data)) > 100:
                    logger.debug("  - User Data: %s...", str(user_data)[:100])
                else:
                    logger.debug("  - User Data: %s", user_data)

    def _add_compute_capabilities(
        self,
        compute_node,
        instance_type: str,
        ami: str | None = None,
    ) -> None:
        """Add capabilities to the Compute node based on the instance type.

        Only capabilities with meaningful properties are added. Empty
        capabilities are omitted.
        """
        # Capability "host" with instance specifications (always present)
        if instance_type and instance_type in self._instance_specs:
            specs = self._instance_specs[instance_type]

            # Use GB instead of MB for readability
            memory_gb = specs["memory_gb"]
            if memory_gb < 1:
                mem_size = f"{int(memory_gb * 1024)} MB"
            else:
                mem_size = f"{memory_gb} GB"

            (
                compute_node.add_capability("host")
                .with_property("num_cpus", specs["vcpu"])
                .with_property("mem_size", mem_size)
                .and_node()
            )

            logger.debug(
                "Configured capabilities for '%s': %s vCPU, %s GB RAM",
                instance_type,
                specs["vcpu"],
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
        os_props = self._infer_os_from_ami(ami)
        if os_props:
            os_capability = compute_node.add_capability("os")
            for prop_name, prop_value in os_props.items():
                os_capability.with_property(prop_name, prop_value)
            os_capability.and_node()

        # Do not add empty capabilities (endpoint, scalable, binding)

    def _infer_os_from_ami(self, ami: str | None) -> dict[str, str]:
        """Infer operating system properties from the AMI.

        Returns:
            A dict with OS properties, empty if unable to infer.
        """
        if not ami:
            return {}

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
            logger.debug("Inferred OS properties from AMI '%s': %s", ami, os_props)

        return os_props
