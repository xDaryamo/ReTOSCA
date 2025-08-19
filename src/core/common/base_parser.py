"""Base implementation for source file parsers."""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..protocols import SourceFileParser

logger = logging.getLogger(__name__)


class BaseSourceFileParser(SourceFileParser, ABC):
    """
    Abstract base class for source file parsers.

    Provides common functionality for file validation, error handling, and basic
    parsing operations while keeping vendor-specific parsing logic abstract.

    Subclasses must implement:
    - get_supported_extensions(): Define which file extensions are supported
    - _parse_content(): Parse the actual file content into a structured format

    Subclasses can optionally override:
    - validate_file(): Custom file validation logic
    - _read_file(): Custom file reading logic
    - _handle_parse_error(): Custom error handling
    """

    def __init__(self, encoding: str = "utf-8"):
        """
        Initialize the parser.

        Args:
            encoding: Default file encoding to use when reading files
        """
        self.encoding = encoding
        self._logger = logger.getChild(self.__class__.__name__)

    @abstractmethod
    def get_supported_extensions(self) -> list[str]:
        """
        Returns a list of file extensions this parser supports.

        Returns:
            List of file extensions (e.g., ['.tf', '.tf.json'])
        """
        pass

    @abstractmethod
    def _parse_content(self, content: str, file_path: Path) -> dict[str, Any]:
        """
        Parse the file content into a structured Python dictionary.

        This method contains the vendor-specific parsing logic and must be
        implemented by each plugin.

        Args:
            content: The raw file content as a string
            file_path: Path to the file being parsed (for context/error reporting)

        Returns:
            Parsed data as a dictionary

        Raises:
            Any parsing-related exceptions should be raised here
        """
        pass

    def parse(self, file_path: Path) -> dict[str, Any]:
        """
        Parses a single file into a structured Python dictionary.

        This method orchestrates the parsing process by:
        1. Validating the file
        2. Reading the file content
        3. Parsing the content using vendor-specific logic
        4. Handling any errors that occur

        Args:
            file_path: Path to the file to parse

        Returns:
            Parsed data as a dictionary

        Raises:
            FileNotFoundError: If the file doesn't exist
            ValueError: If the file is not supported or invalid
            Exception: Any parsing errors from the specific implementation
        """
        self._logger.info(f"Parsing file: {file_path}")

        # Validate file before processing
        self.validate_file(file_path)

        try:
            # Read file content
            content = self._read_file(file_path)

            # Parse content using vendor-specific logic
            result = self._parse_content(content, file_path)

            self._logger.debug(f"Successfully parsed {file_path}")
            return result

        except Exception as e:
            return self._handle_parse_error(e, file_path)

    def validate_file(self, file_path: Path) -> None:
        """
        Validate that the file exists and has a supported extension.

        Subclasses can override this method to add custom validation logic.

        Args:
            file_path: Path to the file to validate

        Raises:
            FileNotFoundError: If the file doesn't exist
            ValueError: If the file extension is not supported
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        supported_extensions = self.get_supported_extensions()
        if supported_extensions and file_path.suffix not in supported_extensions:
            raise ValueError(
                f"Unsupported file extension '{file_path.suffix}'. "
                f"Supported extensions: {supported_extensions}"
            )

    def _read_file(self, file_path: Path) -> str:
        """
        Reads the file content as text.

        Subclasses may override to handle special cases
        (e.g., encodings, compressed files).

        Args:
            file_path: Path of the file to read.

        Returns:
            Content of the file as a string.

        Raises:
            UnicodeDecodeError: If decoding fails.
            IOError: If reading the file fails.
        """

        try:
            return file_path.read_text(encoding=self.encoding)
        except UnicodeDecodeError:
            self._logger.error(
                f"Failed to decode file {file_path} with encoding {self.encoding}"
            )
            raise
        except OSError as e:
            self._logger.error(f"Failed to read file {file_path}: {e}")
            raise

    def _handle_parse_error(self, error: Exception, file_path: Path) -> dict[str, Any]:
        """
        Handle parsing errors.

        Subclasses can override this method to implement custom error handling
        (e.g., logging, error recovery, partial parsing, etc.).

        Args:
            error: The exception that occurred during parsing
            file_path: Path to the file that failed to parse

        Returns:
            Recovery data or re-raises the exception

        Raises:
            Exception: Re-raises the original exception by default
        """
        self._logger.error(f"Failed to parse {file_path}: {error}")
        raise error

    def can_parse(self, file_path: Path) -> bool:
        """
        Check if this parser can handle the given file.

        Useful for plugin discovery and automatic parser selection.

        Args:
            file_path: Path to the file to check

        Returns:
            True if this parser can handle the file, False otherwise
        """
        try:
            if not (file_path.exists() and file_path.is_file()):
                return False

            supported_extensions = self.get_supported_extensions()
            if not supported_extensions:
                return True

            # Check for exact suffix match first
            if file_path.suffix in supported_extensions:
                return True

            # Check for multi-part extensions (e.g., .tf.json)
            for ext in supported_extensions:
                if file_path.name.endswith(ext):
                    return True

            return False
        except Exception:
            return False

    def get_parser_info(self) -> dict[str, Any]:
        """
        Get information about this parser.

        Useful for debugging and plugin introspection.

        Returns:
            Dictionary containing parser information
        """
        return {
            "class_name": self.__class__.__name__,
            "module": self.__class__.__module__,
            "supported_extensions": self.get_supported_extensions(),
            "encoding": self.encoding,
        }
