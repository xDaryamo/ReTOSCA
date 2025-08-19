from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder


class SourceFileParser(Protocol):
    """Defines the contract for parsing a source IaC file."""

    def get_supported_extensions(self) -> list[str]:
        """
        Returns the list of file extensions supported
        (e.g., [".tf", ".tf.json"]).
        """

        ...

    def can_parse(self, file_path: Path) -> bool:
        """
        Checks whether this parser can handle the given file or directory.

        Args:
            file_path: Path to file or directory to check

        Returns:
            True if the parser can handle this path, False otherwise
        """
        ...

    def parse(self, file_path: Path) -> dict[str, Any]:
        """Parses a single file into a structured Python dictionary."""
        ...


class SingleResourceMapper(Protocol):
    """Defines the contract for mapping a single resource type to TOSCA."""

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        """
        Checks whether this mapper can handle the given resource.

        Args:
            resource_type: Resource type (e.g., "aws_instance").
            resource_data: Configuration data of the resource.

        Returns:
            True if the resource is supported, False otherwise.
        """

        ...

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
    ) -> None:
        """
        Map a single resource to TOSCA using the builder.

        Args:
            resource_name: The name/identifier of the resource
            resource_type: The type/kind of resource (e.g., 'aws_instance')
            resource_data: The resource configuration data
            builder: The ServiceTemplateBuilder to populate with TOSCA resources
        """
        ...


class ResourceMapper(Protocol):
    """Defines the contract for mapping parsed resources to TOSCA."""

    def map(
        self, parsed_data: dict[str, Any], builder: "ServiceTemplateBuilder"
    ) -> None:
        """
        Iterates through parsed data and maps resources to TOSCA nodes.
        This method modifies the builder object directly.
        """
        ...

    def register_mapper(self, resource_type: str, mapper: SingleResourceMapper) -> None:
        """
        Register a single resource mapper for a specific resource type.

        Args:
            resource_type: The resource type to handle (e.g., 'aws_instance')
            mapper: The mapper instance that can handle this resource type
        """
        ...

    def get_registered_mappers(self) -> dict[str, SingleResourceMapper]:
        """
        Get all registered mappers.

        Returns:
            Dictionary mapping resource types to their mappers
        """
        ...


class Orchestrator(Protocol):
    """Defines the contract for the main plugin execution flow."""

    def translate(
        self, source_path: Path, output_file: Path
    ) -> "ServiceTemplateBuilder":
        """
        Orchestrates the entire translation process:
        1. Find and parse source files.
        2. Map parsed resources to a TOSCA model using the builder.
        3. Save the final TOSCA file.
        """
        ...
