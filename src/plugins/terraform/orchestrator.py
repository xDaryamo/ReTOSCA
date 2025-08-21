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

        # Register the mapper for AWS S3 Bucket
        from .mappers.aws.aws_s3_bucket import AWSS3BucketMapper

        self._mapper.register_mapper("aws_s3_bucket", AWSS3BucketMapper())

        # Register the mapper for AWS EBS Volume
        from .mappers.aws.aws_ebs_volume import AWSEBSVolumeMapper

        self._mapper.register_mapper("aws_ebs_volume", AWSEBSVolumeMapper())

        # Register the mapper for AWS DB Instance
        from .mappers.aws.aws_db_instance import AWSDBInstanceMapper

        self._mapper.register_mapper("aws_db_instance", AWSDBInstanceMapper())

        # Register the mapper for AWS Internet Gateway
        from .mappers.aws.aws_internet_gateway import AWSInternetGatewayMapper

        self._mapper.register_mapper("aws_internet_gateway", AWSInternetGatewayMapper())

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
