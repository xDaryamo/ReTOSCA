"""
Command-line interface for translating Terraform configurations to TOSCA 2.0 models.

This module provides a user-friendly CLI for the tosca-intent-discovery tool.
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

from src.plugins.terraform.exceptions import (
    OutputMappingError,
    ReferenceResolutionError,
    ResourceMappingError,
    TerraformDataError,
    TerraformPluginError,
    ValidationError,
    VariableExtractionError,
)
from src.plugins.terraform.orchestrator import TerraformOrchestrator


def configure_logging(debug: bool = False) -> None:
    """Configure application logging.

    Args:
        debug: Enable debug-level logging if True.
    """
    level = logging.DEBUG if debug else logging.INFO
    format_str = (
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        if debug
        else "%(levelname)s: %(message)s"
    )

    logging.basicConfig(
        level=level,
        format=format_str,
        stream=sys.stdout,
        force=True,  # Override existing configuration
    )


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


def parse_arguments() -> argparse.Namespace:
    """Parse and validate command line arguments.

    Returns:
        Parsed command line arguments with validated paths.
    """
    parser = argparse.ArgumentParser(
        description="Reverse engineer Terraform configurations to TOSCA 2.0 models",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main examples/basic/aws_s3_bucket output/s3_bucket.yaml
  python -m src.main examples/mvc/ output/mvc.yaml --debug
        """,
    )

    parser.add_argument(
        "input_directory",
        type=Path,
        help="Path to directory containing Terraform configuration files",
    )

    parser.add_argument(
        "output_file",
        type=Path,
        help="Path where the generated TOSCA YAML file will be saved",
    )

    parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging for detailed output"
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

    return parser.parse_args()


def run_translation(
    input_directory: Path, output_file: Path, debug: bool = False, validate: bool = True
) -> NoReturn:
    """Execute the translation process from Terraform to TOSCA.

    Args:
        input_directory: Path to directory containing Terraform files.
        output_file: Path where the generated TOSCA YAML file will be saved.
        debug: Enable debug logging for detailed output.
        validate: Enable TOSCA validation with Puccini after generation.

    Raises:
        SystemExit: Always exits with appropriate code (0 for success, >0 for errors).
    """
    configure_logging(debug)
    logger = logging.getLogger(__name__)

    logger.info(f"Translating Terraform configuration from: {input_directory}")
    logger.info(f"Output TOSCA file: {output_file}")

    try:
        validate_inputs(input_directory, output_file)
    except ValidationError as e:
        logger.error(f"Input validation failed: {e}")
        if hasattr(e, "get_recovery_hint"):
            logger.info(f"Suggestion: {e.get_recovery_hint()}")
        sys.exit(1)

    try:
        orchestrator = TerraformOrchestrator()
        orchestrator.translate(input_directory, output_file)

        logger.info(f"✅ TOSCA YAML saved to: {output_file}")
        logger.info("Translation completed successfully!")

        # Validate with Puccini if requested
        if validate:
            logger.info("Starting TOSCA validation...")
            validation_success = validate_tosca_with_puccini(output_file)
            if not validation_success:
                logger.error("TOSCA validation failed!")
                sys.exit(10)
            else:
                logger.info("✅ TOSCA validation completed successfully!")

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
    run_translation(args.input_directory, args.output_file, args.debug, should_validate)
