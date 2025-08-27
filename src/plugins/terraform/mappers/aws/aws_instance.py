import logging
import re
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper
from src.core.protocols import SingleResourceMapper
from src.plugins.terraform.terraform_mapper_base import TerraformResourceMapperMixin

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder

logger = logging.getLogger(__name__)


class AWSInstanceMapper(TerraformResourceMapperMixin, SingleResourceMapper):
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
        cpu_options = values.get("cpu_options", [])

        # Infer compute capabilities from the AWS instance type and cpu_options
        self._add_compute_capabilities(compute_node, instance_type, ami, cpu_options)

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
            metadata["aws_tags_all"] = tags_all

        # Update the node metadata with the additional information
        compute_node.with_metadata(metadata)

        # Add subnet dependency if present
        self._add_subnet_dependency(compute_node, resource_data, node_name)

        # Add security group dependencies if present
        self._add_security_group_dependencies(compute_node, resource_data, node_name)

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
        cpu_options: list[dict[str, Any]] | None = None,
    ) -> None:
        """Add capabilities to the Compute node based on the instance type.

        Args:
            compute_node: The TOSCA compute node to enhance
            instance_type: AWS instance type (e.g., 'c6a.2xlarge')
            ami: AMI ID for OS capability inference
            cpu_options: List of CPU option dictionaries from Terraform

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
        os_props = self._infer_os_from_ami(ami)
        if os_props:
            os_capability = compute_node.add_capability("os")
            for prop_name, prop_value in os_props.items():
                os_capability.with_property(prop_name, prop_value)
            os_capability.and_node()

        # Do not add empty capabilities (endpoint, scalable, binding)

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

    def _infer_os_from_ami(self, ami: str | None) -> dict[str, str]:
        """Infer operating system properties from the AMI.

        First tries to extract detailed info from the Terraform plan data,
        then falls back to basic pattern matching on the AMI ID.

        Returns:
            A dict with OS properties, empty if unable to infer.
        """
        if not ami:
            return {}

        # Try to get detailed AMI data from Terraform plan
        os_props = self._extract_ami_data_from_plan(ami)
        if os_props:
            return os_props

        # Fallback to basic pattern matching
        return self._infer_os_from_ami_pattern(ami)

    def _extract_ami_data_from_plan(self, ami: str) -> dict[str, str]:
        """Extract OS information from AMI data in the Terraform plan.

        Returns:
            A dict with OS properties extracted from plan data.
        """
        # Import here to avoid circular imports
        import inspect

        from src.plugins.terraform.mapper import TerraformMapper

        # Access the full plan via the TerraformMapper instance found on the call stack
        parsed_data: dict[str, Any] = {}
        for frame_info in inspect.stack():
            frame_locals = frame_info.frame.f_locals
            if "self" in frame_locals and isinstance(
                frame_locals["self"], TerraformMapper
            ):
                parsed_data = frame_locals["self"].get_current_parsed_data()
                break
        else:
            logger.debug("Could not access parsed_data for AMI information extraction")
            return {}

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

    def _add_subnet_dependency(
        self,
        compute_node,
        resource_data: dict[str, Any],
        node_name: str,
    ) -> None:
        """Add dependency relationship to the subnet if detected."""
        # Import here to avoid circular imports
        import inspect

        from src.plugins.terraform.mapper import TerraformMapper

        # Access the full plan via the TerraformMapper instance found on the call stack
        parsed_data: dict[str, Any] = {}
        for frame_info in inspect.stack():
            frame_locals = frame_info.frame.f_locals
            if "self" in frame_locals and isinstance(
                frame_locals["self"], TerraformMapper
            ):
                parsed_data = frame_locals["self"].get_current_parsed_data()
                break
        else:
            logger.debug("Could not access parsed_data for dependency detection")
            return

        # Extract Terraform references using the static method
        references = TerraformMapper.extract_terraform_references(
            resource_data, parsed_data
        )

        # Look for subnet dependency
        subnet_dependency_added = False
        for prop_name, target_resource, relationship_type in references:
            if prop_name == "subnet_id" and "aws_subnet" in target_resource:
                # Convert aws_subnet.example -> aws_subnet_example for TOSCA node name
                target_node_name = BaseResourceMapper.generate_tosca_node_name(
                    target_resource, "aws_subnet"
                )

                logger.debug(
                    "Adding subnet dependency: %s -> %s (%s)",
                    node_name,
                    target_node_name,
                    relationship_type,
                )

                # Add the requirement to connect to the subnet
                compute_node.add_requirement("dependency").to_node(
                    target_node_name
                ).with_relationship("DependsOn").and_node()

                subnet_dependency_added = True
                break

        if not subnet_dependency_added:
            logger.debug("No subnet dependency detected for instance '%s'", node_name)

    def _add_security_group_dependencies(
        self,
        compute_node,
        resource_data: dict[str, Any],
        node_name: str,
    ) -> None:
        """Add dependency relationships to security groups if detected."""
        # Import here to avoid circular imports
        import inspect

        from src.plugins.terraform.mapper import TerraformMapper

        # Access the full plan via the TerraformMapper instance found on the call stack
        parsed_data: dict[str, Any] = {}
        for frame_info in inspect.stack():
            frame_locals = frame_info.frame.f_locals
            if "self" in frame_locals and isinstance(
                frame_locals["self"], TerraformMapper
            ):
                parsed_data = frame_locals["self"].get_current_parsed_data()
                break
        else:
            logger.debug(
                "Could not access parsed_data for security group dependency detection"
            )
            return

        # Extract Terraform references using the static method
        references = TerraformMapper.extract_terraform_references(
            resource_data, parsed_data
        )

        # Look for security group dependencies
        security_group_dependencies_added = 0
        added_security_groups = set()  # Keep track of already added security groups
        for prop_name, target_resource, relationship_type in references:
            # Check for security group properties
            sg_props = [
                "vpc_security_group_ids",
                "security_groups",
                "security_group_ids",
            ]
            if prop_name in sg_props and "aws_security_group" in target_resource:
                # Convert aws_security_group.web-sg -> aws_security_group_web_sg
                # for TOSCA node name
                target_node_name = BaseResourceMapper.generate_tosca_node_name(
                    target_resource, "aws_security_group"
                )

                # Avoid adding the same security group dependency multiple times
                if target_node_name in added_security_groups:
                    logger.debug(
                        "Security group dependency already added: %s -> %s, skipping",
                        node_name,
                        target_node_name,
                    )
                    continue

                logger.debug(
                    "Adding security group dependency: %s -> %s (%s)",
                    node_name,
                    target_node_name,
                    relationship_type,
                )

                # Add the requirement to connect to the security group
                compute_node.add_requirement("dependency").to_node(
                    target_node_name
                ).with_relationship("DependsOn").and_node()

                added_security_groups.add(target_node_name)
                security_group_dependencies_added += 1

        if security_group_dependencies_added == 0:
            logger.debug(
                "No security group dependencies detected for instance '%s'", node_name
            )
        else:
            logger.info(
                "Added %d security group dependencies for instance '%s'",
                security_group_dependencies_added,
                node_name,
            )

    def _generate_mount_point(self, device_name: str) -> str:
        """Generate a logical mount point from a device name.

        Args:
            device_name: Device name like '/dev/sdh', '/dev/xvdf', etc.

        Returns:
            A placeholder string indicating the mount point is unspecified.
        """
        return "unspecified"
