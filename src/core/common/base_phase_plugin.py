"""Base implementation for phase plugins."""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from ..protocols import PhasePlugin, ResourceMapper, SourceFileParser

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder


logger = logging.getLogger(__name__)


class BasePhasePlugin(PhasePlugin, ABC):
    """
    Abstract base class for phase plugins.

    Provides common functionality for file discovery and plugin coordination
    while keeping vendor-specific parser and mapper logic abstract.

    Subclasses must implement:
    - get_parser(): Return the vendor-specific parser
    - get_mapper(): Return the vendor-specific mapper
    - get_plugin_info(): Return plugin metadata

    Subclasses can optionally override:
    - find_source_files(): Custom file discovery logic
    - can_handle(): Custom source path compatibility checking
    """

    def __init__(self):
        """Initialize the phase plugin."""
        self._logger = logger.getChild(self.__class__.__name__)

    @abstractmethod
    def get_parser(self) -> SourceFileParser:
        """
        Get the parser for this technology.

        This method must be implemented by each plugin to return
        the appropriate parser instance.

        Returns:
            The parser instance for this technology
        """
        pass

    @abstractmethod
    def get_mapper(self) -> ResourceMapper:
        """
        Get the mapper for this technology.

        This method must be implemented by each plugin to return
        the appropriate mapper instance.

        Returns:
            The mapper instance for this technology
        """
        pass

    @abstractmethod
    def get_plugin_info(self) -> dict:
        """
        Get information about this plugin.

        Returns:
            Dictionary with plugin metadata (name, phase, supported_types, etc.)
        """
        pass

    def execute(self, source_path: Path, builder: "ServiceTemplateBuilder") -> None:
        """
        Execute this plugin's phase, enriching the provided builder.

        This method coordinates the plugin workflow:
        1. Find source files for this plugin
        2. Parse each source file
        3. Map parsed resources to TOSCA nodes using the builder

        Args:
            source_path: Path to the source directory or file for this plugin
            builder: ServiceTemplateBuilder to enrich with TOSCA nodes
        """
        self._logger.info(f"Executing {self.__class__.__name__} on: {source_path}")

        try:
            # Step 1: Find source files
            source_files = self.find_source_files(source_path)
            if not source_files:
                self._logger.warning(
                    f"No supported source files found in {source_path}"
                )
                return

            self._logger.info(f"Found {len(source_files)} source files")

            # Step 2: Get components
            parser = self.get_parser()
            mapper = self.get_mapper()

            # Step 3: Parse and map each source file
            for source_file in source_files:
                self._logger.debug(f"Processing file: {source_file}")

                # Parse the file
                parsed_data = parser.parse(source_file)

                # Map to TOSCA using the provided builder
                mapper.map(parsed_data, builder)

            self._logger.info("Plugin execution completed successfully")

        except Exception as e:
            self._logger.error(f"Plugin execution failed: {e}")
            raise

    def can_handle(self, source_path: Path) -> bool:
        """
        Check if this plugin can handle the given source path.

        Default implementation checks if the parser can parse the source path.

        Args:
            source_path: Path to check for compatibility

        Returns:
            True if plugin can handle this source, False otherwise
        """
        if not source_path.exists():
            return False

        try:
            parser = self.get_parser()
            return parser.can_parse(source_path)
        except Exception as e:
            self._logger.debug(f"Error checking compatibility for {source_path}: {e}")
            return False

    def find_source_files(self, source_path: Path) -> list[Path]:
        """
        Find all supported source files in the given path.

        Subclasses can override this method to implement custom file discovery logic.

        Args:
            source_path: Path to search for source files (file or directory)

        Returns:
            List of source files found

        Raises:
            ValueError: If source_path doesn't exist
        """
        if not source_path.exists():
            raise ValueError(f"Source path does not exist: {source_path}")

        parser = self.get_parser()
        supported_extensions = parser.get_supported_extensions()

        source_files = []

        if source_path.is_file():
            # Single file
            if parser.can_parse(source_path):
                source_files.append(source_path)
        else:
            # Directory - find all supported files
            for ext in supported_extensions:
                source_files.extend(source_path.rglob(f"*{ext}"))

        # Filter files that the parser can actually handle
        return [f for f in source_files if parser.can_parse(f)]
