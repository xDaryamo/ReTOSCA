"""Utility functions and classes for AWS Terraform mappers."""

import logging

logger = logging.getLogger(__name__)


class AWSProtocolMapper:
    """Handles AWS to TOSCA protocol mapping for load balancers and listeners."""

    # AWS to TOSCA protocol mapping
    _PROTOCOL_MAP: dict[str, str] = {
        "HTTP": "http",
        "HTTPS": "https",
        "TCP": "tcp",
        "TLS": "tcp",  # TLS over TCP
        "UDP": "udp",
        "TCP_UDP": "tcp",  # Primary protocol
        "GENEVE": "tcp",  # GENEVE typically over UDP but represents as TCP
    }

    @classmethod
    def to_tosca_protocol(cls, aws_protocol: str) -> str:
        """Map AWS listener protocol to TOSCA endpoint protocol.

        Args:
            aws_protocol: AWS listener protocol (e.g., "HTTP", "HTTPS", "TCP")

        Returns:
            TOSCA-compatible protocol name (e.g., "http", "https", "tcp")
        """
        if not aws_protocol:
            logger.warning("Empty AWS protocol provided, defaulting to 'tcp'")
            return "tcp"

        mapped_protocol = cls._PROTOCOL_MAP.get(aws_protocol.upper())
        if mapped_protocol:
            return mapped_protocol

        # If no mapping found, log warning and return lowercase version
        logger.warning(
            "Unknown AWS protocol '%s', returning lowercase version", aws_protocol
        )
        return aws_protocol.lower()

    @classmethod
    def is_secure_protocol(cls, aws_protocol: str) -> bool:
        """Check if the AWS protocol is secure (encrypted).

        Args:
            aws_protocol: AWS listener protocol

        Returns:
            True if the protocol is secure (HTTPS, TLS)
        """
        return aws_protocol.upper() in {"HTTPS", "TLS"}

    @classmethod
    def get_default_port(cls, aws_protocol: str) -> int:
        """Get the default port for an AWS protocol.

        Args:
            aws_protocol: AWS listener protocol

        Returns:
            Default port number for the protocol
        """
        default_ports = {
            "HTTP": 80,
            "HTTPS": 443,
            "TCP": 80,
            "TLS": 443,
            "UDP": 53,  # Common UDP port (DNS)
        }

        return default_ports.get(aws_protocol.upper(), 80)
