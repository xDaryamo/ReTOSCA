import logging
from pathlib import Path
from typing import TYPE_CHECKING

# Import base classes
from src.core.common.base_orchestrator import BaseOrchestrator
from src.core.protocols import ResourceMapper, SourceFileParser

# Type checking imports (kept separate to avoid runtime cycles)
if TYPE_CHECKING:
    pass

# Import plugin-specific components
from .mapper import TerraformMapper

# Import all single-mappers you want to register
from .mappers.aws.aws_instance import AWSInstanceMapper
from .mappers.aws.aws_security_group import AWSSecurityGroupMapper
from .mappers.aws.aws_subnet import AWSSubnetMapper
from .mappers.aws.aws_vpc import AWSVPCMapper
from .mappers.aws.aws_vpc_security_group_egress_rule import (
    AWSVPCSecurityGroupEgressRuleMapper,
)
from .mappers.aws.aws_vpc_security_group_ingress_rule import (
    AWSVPCSecurityGroupIngressRuleMapper,
)
from .parser import TerraformParser

logger = logging.getLogger(__name__)


class TerraformOrchestrator(BaseOrchestrator):
    """
    Orchestrator for the Terraform plugin.

    Connects the TerraformParser with the TerraformMapper.
    """

    def __init__(self):
        super().__init__()
        self._parser = TerraformParser()
        self._mapper = TerraformMapper()

        # --- Mapper registration ---
        # Central place to enable support for individual resources.
        self._register_mappers()

    def get_parser(self) -> SourceFileParser:
        """Return the Terraform parser instance."""
        return self._parser

    def get_mapper(self) -> ResourceMapper:
        """Return the Terraform mapper instance."""
        return self._mapper

    def _register_mappers(self):
        """Register all available single-mappers."""
        self._logger.info("Registering Terraform resource mappers...")

        # Register the mapper for AWS instances
        self._mapper.register_mapper("aws_instance", AWSInstanceMapper())

        # Register the mapper for AWS VPC
        self._mapper.register_mapper("aws_vpc", AWSVPCMapper())

        # Register the mapper for AWS subnet
        self._mapper.register_mapper("aws_subnet", AWSSubnetMapper())

        # Register the mapper for AWS security group
        self._mapper.register_mapper("aws_security_group", AWSSecurityGroupMapper())

        # Register the mappers for AWS security group rules
        self._mapper.register_mapper(
            "aws_vpc_security_group_ingress_rule",
            AWSVPCSecurityGroupIngressRuleMapper(),
        )
        self._mapper.register_mapper(
            "aws_vpc_security_group_egress_rule",
            AWSVPCSecurityGroupEgressRuleMapper(),
        )

        # Register the mapper for AWS S3 Bucket
        from .mappers.aws.aws_s3_bucket import AWSS3BucketMapper

        self._mapper.register_mapper("aws_s3_bucket", AWSS3BucketMapper())

        # Register the mapper for AWS EBS Volume
        from .mappers.aws.aws_ebs_volume import AWSEBSVolumeMapper

        self._mapper.register_mapper("aws_ebs_volume", AWSEBSVolumeMapper())

        # Register the mapper for AWS Volume Attachment
        from .mappers.aws.aws_volume_attachment import AWSVolumeAttachmentMapper

        self._mapper.register_mapper(
            "aws_volume_attachment", AWSVolumeAttachmentMapper()
        )

        # Register the mapper for AWS Route Table Association
        from .mappers.aws.aws_route_table_association import (
            AWSRouteTableAssociationMapper,
        )

        self._mapper.register_mapper(
            "aws_route_table_association", AWSRouteTableAssociationMapper()
        )

        # Register the mapper for AWS DB Instance
        from .mappers.aws.aws_db_instance import AWSDBInstanceMapper

        self._mapper.register_mapper("aws_db_instance", AWSDBInstanceMapper())

        # Register the mapper for AWS DB Subnet Group
        from .mappers.aws.aws_db_subnet_group import AWSDBSubnetGroupMapper

        self._mapper.register_mapper("aws_db_subnet_group", AWSDBSubnetGroupMapper())

        # Register the mapper for AWS Internet Gateway
        # (supports both standard and egress-only)
        from .mappers.aws.aws_internet_gateway import AWSInternetGatewayMapper

        internet_gateway_mapper = AWSInternetGatewayMapper()
        self._mapper.register_mapper("aws_internet_gateway", internet_gateway_mapper)
        self._mapper.register_mapper(
            "aws_egress_only_internet_gateway", internet_gateway_mapper
        )

        # Register the mapper for AWS Route Table
        from .mappers.aws.aws_route_table import AWSRouteTableMapper

        self._mapper.register_mapper("aws_route_table", AWSRouteTableMapper())

        # Register the mapper for AWS IAM Role
        from .mappers.aws.aws_iam_role import AWSIAMRoleMapper

        self._mapper.register_mapper("aws_iam_role", AWSIAMRoleMapper())

        # Register the mapper for AWS IAM Policy
        from .mappers.aws.aws_iam_policy import AWSIAMPolicyMapper

        self._mapper.register_mapper("aws_iam_policy", AWSIAMPolicyMapper())

        # Register the mapper for AWS Load Balancer
        from .mappers.aws.aws_lb import AWSLoadBalancerMapper

        aws_lb_mapper = AWSLoadBalancerMapper()
        self._mapper.register_mapper("aws_lb", aws_lb_mapper)

        # Register the mapper for AWS Elastic IP
        from .mappers.aws.aws_eip import AWSEIPMapper

        self._mapper.register_mapper("aws_eip", AWSEIPMapper())

        # Register the mapper for AWS NAT Gateway
        from .mappers.aws.aws_nat_gateway import AWSNATGatewayMapper

        self._mapper.register_mapper("aws_nat_gateway", AWSNATGatewayMapper())

        # Register the mapper for AWS Route
        from .mappers.aws.aws_route import AWSRouteMapper

        self._mapper.register_mapper("aws_route", AWSRouteMapper())

        # Register the mapper for AWS VPC IPv4 CIDR Block Association
        from .mappers.aws.aws_vpc_ipv4_cidr_block_association import (
            AWSVPCIpv4CidrBlockAssociationMapper,
        )

        self._mapper.register_mapper(
            "aws_vpc_ipv4_cidr_block_association",
            AWSVPCIpv4CidrBlockAssociationMapper(),
        )

        self._logger.info("Registration completed.")

    def find_source_files(self, source_path: Path) -> list[Path]:
        """
        Override to handle Terraform projects.

        Because our parser operates on a directory, we don't search for .tf files.
        Instead verify that the provided path is a valid project directory.
        """
        parser = self.get_parser()
        if source_path.is_dir() and parser.can_parse(source_path):
            self._logger.info(f"Found valid Terraform project directory: {source_path}")
            return [source_path]

        self._logger.warning(
            "The path '%s' is not a valid Terraform project directory. "
            "No files to process.",
            source_path,
        )

        return []
