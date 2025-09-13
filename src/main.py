"""
Command-line interface for translating Terraform configurations to TOSCA 2.0 models.

This module provides a user-friendly CLI for the ReTOSCA tool.
"""

import argparse
import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from src.core.pipeline_runner import PipelineRunner
from src.core.plugin_registry import get_global_registry, register_builtin_plugins
from src.core.protocols import PhasePlugin
from src.plugins.provisioning.terraform.exceptions import (
    OutputMappingError,
    ReferenceResolutionError,
    ResourceMappingError,
    TerraformDataError,
    TerraformPluginError,
    ValidationError,
    VariableExtractionError,
)


@dataclass
class SourceSpec:
    """Specification for a source input with its plugin type."""

    plugin_type: str
    source_path: Path


def parse_source_argument(source_arg: str) -> SourceSpec:
    """
    Parse a source argument in TYPE:PATH format.

    Args:
        source_arg: Source argument string (e.g., 'terraform:/path/to/source')

    Returns:
        SourceSpec with parsed plugin type and path

    Raises:
        ValueError: If the argument format is invalid
    """
    if ":" not in source_arg:
        raise ValueError(
            f"Invalid source format: '{source_arg}'. "
            "Expected format: TYPE:PATH (e.g., 'terraform:/path/to/source')"
        )

    plugin_type, path_str = source_arg.split(":", 1)

    if not plugin_type.strip():
        raise ValueError(
            f"Empty plugin type in source: '{source_arg}'. "
            "Expected format: TYPE:PATH (e.g., 'terraform:/path/to/source')"
        )

    if not path_str.strip():
        raise ValueError(
            f"Empty path in source: '{source_arg}'. "
            "Expected format: TYPE:PATH (e.g., 'terraform:/path/to/source')"
        )

    return SourceSpec(
        plugin_type=plugin_type.strip().lower(), source_path=Path(path_str.strip())
    )


def show_available_plugins() -> NoReturn:
    """Show available plugin types and exit."""
    show_banner()

    # Ensure built-in plugins are registered
    register_builtin_plugins()

    registry = get_global_registry()
    available_types = registry.get_available_types()

    print("Available Plugin Types:")
    print("=" * 50)

    if not available_types:
        print("No plugins registered.")
        sys.exit(0)

    for plugin_type in available_types:
        try:
            plugin_info = registry.get_plugin_info(plugin_type)
            description = plugin_info.get("description", "No description available")
            print(f"  {plugin_type:<12} - {description}")

            # Show supported extensions if available
            extensions = plugin_info.get("supported_extensions")
            if extensions:
                print(f"               Supported files: {', '.join(extensions)}")

        except Exception as e:
            print(f"  {plugin_type:<12} - Error getting plugin info: {e}")

        print()  # Empty line between plugins

    sys.exit(0)


def show_banner() -> None:
    """Display the TOSCA banner."""
    banner = """    ____     __________  _____ _________
   / __ \\___/_  __/ __ \\/ ___// ____/   |
  / /_/ / _ \\/ / / / / /\\__ \\/ /   / /| |
 / _, _/  __/ / / /_/ /___/ / /___/ ___ |
/_/ |_|\\___/_/  \\____//____/\\____/_/  |_|
                                         """
    print(banner)
    print()


def configure_logging(debug: bool = False, verbose: bool = False) -> None:
    """Configure application logging.

    Args:
        debug: Enable debug-level logging if True.
        verbose: Enable verbose logging from plugins if True.
    """
    # Determine logging level
    if debug:
        level = logging.DEBUG
        format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    elif verbose:
        level = logging.INFO
        format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    else:
        level = logging.INFO
        format_str = "%(levelname)s: %(message)s"

    logging.basicConfig(
        level=level,
        format=format_str,
        stream=sys.stdout,
        force=True,  # Override existing configuration
    )

    # Configure plugin loggers based on verbose setting
    if not verbose and not debug:
        # In quiet mode, be very aggressive about hiding plugin details
        # Set root logger to WARNING to suppress most plugin chatter
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.WARNING)

        # Allow main application INFO logs through
        main_logger = logging.getLogger(__name__)
        main_logger.setLevel(logging.INFO)

        # Allow validation logs through
        validation_logger = logging.getLogger("__main__")
        validation_logger.setLevel(logging.INFO)

        # Set environment variables to make Terraform quieter
        import os

        os.environ["TF_IN_AUTOMATION"] = "1"
        os.environ["TF_INPUT"] = "0"
        # Signal to plugins that we're in quiet mode
        os.environ["TOSCA_QUIET_MODE"] = "1"


def validate_tosca_with_puccini(tosca_file: Path) -> bool:
    """Validate TOSCA file using Puccini compiler.

    Args:
        tosca_file: Path to the TOSCA file to validate.

    Returns:
        True if validation succeeds, False otherwise.
    """
    logger = logging.getLogger(__name__)

    try:
        # Check if puccini-tosca is available
        result = subprocess.run(
            ["puccini-tosca", "version"], capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            logger.warning("Puccini TOSCA compiler not found, skipping validation")
            return True

    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.warning("Puccini TOSCA compiler not found, skipping validation")
        return True

    logger.info("🔍 Validating TOSCA syntax with Puccini...")

    # Validate TOSCA syntax
    try:
        result = subprocess.run(
            ["puccini-tosca", "parse", str(tosca_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode == 0:
            logger.info("✅ TOSCA syntax is valid")

            # Try to compile to clout for complete validation
            logger.info("🔧 Compiling TOSCA to clout format...")
            compile_result = subprocess.run(
                ["puccini-tosca", "compile", "-c", str(tosca_file)],
                capture_output=True,
                text=True,
                timeout=120,
            )

            if compile_result.returncode == 0:
                logger.info("✅ TOSCA compilation successful!")
                return True
            else:
                logger.warning("⚠️ TOSCA compilation had warnings:")
                if compile_result.stderr:
                    logger.warning(compile_result.stderr)
                return True  # Syntax is valid even if compilation has warnings
        else:
            logger.error("❌ TOSCA validation failed:")
            if result.stderr:
                logger.error(result.stderr)
            if result.stdout:
                logger.error(result.stdout)
            return False

    except subprocess.TimeoutExpired:
        logger.error("❌ TOSCA validation timed out")
        return False
    except Exception as e:
        logger.error(f"❌ TOSCA validation error: {e}")
        return False


def validate_inputs(input_directory: Path, output_file: Path) -> None:
    """Validate command line inputs.

    Args:
        input_directory: Input directory path to validate.
        output_file: Output file path to validate.

    Raises:
        ValidationError: If inputs are invalid.
    """
    if not input_directory.exists():
        raise ValidationError(
            f"Input directory does not exist: {input_directory}",
            field_name="input_directory",
        )

    if not input_directory.is_dir():
        raise ValidationError(
            f"Input path is not a directory: {input_directory}",
            field_name="input_directory",
        )

    # Validate output file extension
    if output_file.suffix.lower() not in {".yaml", ".yml"}:
        raise ValidationError(
            f"Output file must have .yaml or .yml extension, got: {output_file.suffix}",
            field_name="output_file",
        )

    # Check if output directory can be created/is writable
    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)
    except PermissionError as e:
        raise ValidationError(
            f"Cannot create output directory: {e}", field_name="output_file"
        ) from e


def process_source_arguments(
    source_args: list[str],
) -> list[tuple[Path, "PhasePlugin"]]:
    """
    Process source arguments and create plugin instances.

    Args:
        source_args: List of source argument strings in TYPE:PATH format

    Returns:
        List of (source_path, plugin_instance) tuples for PipelineRunner.execute()

    Raises:
        ValueError: If source format is invalid or plugin type is unknown
        ValidationError: If source paths are invalid
    """
    if not source_args:
        raise ValueError("No source arguments provided")

    # Ensure built-in plugins are registered
    register_builtin_plugins()
    registry = get_global_registry()

    source_inputs = []

    for source_arg in source_args:
        try:
            # Parse the source argument
            source_spec = parse_source_argument(source_arg)

            # Validate that the plugin type exists
            if not registry.is_type_available(source_spec.plugin_type):
                available_types = registry.get_available_types()
                available_list = (
                    ", ".join(available_types) if available_types else "none"
                )
                plugin_type = source_spec.plugin_type
                raise ValueError(
                    f"Unknown plugin type '{plugin_type}' in source '{source_arg}'. "
                    f"Available types: {available_list}"
                )

            # Validate that the source path exists
            if not source_spec.source_path.exists():
                raise ValidationError(
                    f"Source path does not exist: {source_spec.source_path}",
                    field_name="source_path",
                )

            # Create plugin instance
            try:
                plugin_instance = registry.create_plugin_instance(
                    source_spec.plugin_type
                )
            except Exception as e:
                plugin_type = source_spec.plugin_type
                raise ValueError(
                    f"Failed to create plugin instance for type '{plugin_type}': {e}"
                ) from e

            # Verify the plugin can handle this source
            if not plugin_instance.can_handle(source_spec.source_path):
                plugin_type = source_spec.plugin_type
                source_path = source_spec.source_path
                raise ValueError(
                    f"Plugin '{plugin_type}' cannot handle source path: {source_path}"
                )

            source_inputs.append((source_spec.source_path, plugin_instance))

        except ValueError:
            raise  # Re-raise ValueError as-is
        except Exception as e:
            raise ValueError(f"Error processing source '{source_arg}': {e}") from e

    return source_inputs


def _format_available_plugins(available_types: list[str]) -> str:
    """Format the list of available plugin types for help text."""
    if not available_types:
        return "  No plugins available"

    plugin_lines = []
    for ptype in available_types:
        line = f"  {ptype:<12} - Process {ptype.title()} configuration files"
        plugin_lines.append(line)

    return chr(10).join(plugin_lines)


def parse_arguments() -> argparse.Namespace:
    """Parse and validate command line arguments.

    Returns:
        Parsed command line arguments with validated paths.
    """
    # Ensure built-in plugins are registered for help text
    register_builtin_plugins()
    registry = get_global_registry()
    available_types = registry.get_available_types()

    parser = argparse.ArgumentParser(
        description=(
            "Reverse engineer Infrastructure as Code configurations to TOSCA 2.0 models"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available Plugin Types:
{_format_available_plugins(available_types)}

Examples:
  # Process Terraform infrastructure
  python -m src.main --source terraform:examples/basic/aws_s3_bucket \\
    output/s3_bucket.yaml

  # Process with verbose plugin logging
  python -m src.main --source terraform:examples/mvc --verbose output/mvc.yaml

  # Process with debug output
  python -m src.main --source terraform:examples/mvc --debug output/mvc.yaml

  # List available plugins
  python -m src.main --list-plugins

Source Path Requirements:
  - Terraform sources should point to directories containing .tf files
  - Paths can be absolute or relative
  - Directory must be readable and contain valid configuration files
        """,
    )

    # New source-based arguments
    parser.add_argument(
        "-s",
        "--source",
        action="append",
        dest="sources",
        metavar="TYPE:PATH",
        help="IaC source to process (format: type:path, repeatable). "
        f"Available types: {', '.join(available_types) if available_types else 'none'}",
    )
    parser.add_argument(
        "--list-plugins",
        action="store_true",
        help="List available plugin types and exit",
    )

    # Output file - required for translation
    parser.add_argument(
        "output_file",
        nargs="?",  # Optional for --list-plugins
        type=Path,
        help="Path where the generated TOSCA YAML file will be saved",
    )

    # Options
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging for detailed output"
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging from plugins (shows all plugin activity)",
    )

    parser.add_argument(
        "--validate",
        action="store_true",
        default=True,
        help="Validate generated TOSCA with Puccini (default: enabled)",
    )

    parser.add_argument(
        "--no-validate", action="store_true", help="Skip TOSCA validation with Puccini"
    )

    args = parser.parse_args()

    # Handle --list-plugins
    if args.list_plugins:
        show_available_plugins()

    # Validate required arguments
    if args.sources:
        # --source TYPE:PATH ... output_file format
        if not args.output_file:
            parser.error("Output file is required when using --source")
    else:
        # No sources provided
        parser.error("Must specify either --source TYPE:PATH or use --list-plugins")

    return args


def run_translation(
    source_args: list[str],
    output_file: Path,
    debug: bool = False,
    verbose: bool = False,
    validate: bool = True,
) -> NoReturn:
    """Execute the translation process from IaC sources to TOSCA.

    Args:
        source_args: List of source argument strings in TYPE:PATH format.
        output_file: Path where the generated TOSCA YAML file will be saved.
        debug: Enable debug logging for detailed output.
        verbose: Enable verbose logging from plugins.
        validate: Enable TOSCA validation with Puccini after generation.

    Raises:
        SystemExit: Always exits with appropriate code (0 for success, >0 for errors).
    """
    show_banner()
    configure_logging(debug, verbose)
    logger = logging.getLogger(__name__)

    if verbose or debug:
        logger.info(f"Processing {len(source_args)} source(s)")
        for source_arg in source_args:
            logger.info(f"  - {source_arg}")
        logger.info(f"Output TOSCA file: {output_file}")
    else:
        # Quiet mode - just show what's happening
        print(f"🔄 Processing {len(source_args)} Terraform source(s)...")

    try:
        # Process source arguments and create plugin instances
        source_inputs = process_source_arguments(source_args)

        # Create pipeline runner and execute
        pipeline_runner = PipelineRunner()
        pipeline_runner.execute(source_inputs, output_file)

        if verbose or debug:
            logger.info(f"✅ TOSCA YAML saved to: {output_file}")
            logger.info("Translation completed successfully!")
        else:
            print(f"✅ Generated TOSCA model: {output_file}")

        # Validate with Puccini if requested
        if validate:
            if verbose or debug:
                logger.info("Starting TOSCA validation...")
            else:
                print("🔍 Validating TOSCA...")

            validation_success = validate_tosca_with_puccini(output_file)
            if not validation_success:
                print("❌ TOSCA validation failed!")
                sys.exit(10)
            else:
                if verbose or debug:
                    logger.info("✅ TOSCA validation completed successfully!")
                else:
                    print("✅ Validation successful!")

        if verbose or debug:
            logger.info(f"TOSCA file saved to: {output_file.resolve()}")

        sys.exit(0)

    except ValidationError as e:
        logger.error(f"Input validation failed: {e}")
        if hasattr(e, "get_recovery_hint"):
            logger.info(f"Suggestion: {e.get_recovery_hint()}")
        sys.exit(1)
    except TerraformDataError as e:
        logger.error(f"Terraform data error: {e}")
        if hasattr(e, "get_recovery_hint"):
            logger.info(f"Suggestion: {e.get_recovery_hint()}")
        sys.exit(2)
    except VariableExtractionError as e:
        logger.error(f"Variable extraction error: {e}")
        sys.exit(3)
    except ResourceMappingError as e:
        logger.error(f"Resource mapping error: {e}")
        sys.exit(4)
    except ReferenceResolutionError as e:
        logger.error(f"Reference resolution error: {e}")
        sys.exit(5)
    except OutputMappingError as e:
        logger.error(f"Output mapping error: {e}")
        sys.exit(6)
    except TerraformPluginError as e:
        logger.error(f"Terraform plugin error: {e}")
        sys.exit(7)
    except (PermissionError, FileNotFoundError, OSError) as e:
        logger.error(f"File system error: {e}")
        sys.exit(8)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        if debug:
            logger.exception("Full traceback:")
        sys.exit(9)


if __name__ == "__main__":
    args = parse_arguments()
    # Determine validation setting
    should_validate = args.validate and not args.no_validate
    run_translation(
        args.sources, args.output_file, args.debug, args.verbose, should_validate
    )
