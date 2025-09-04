"""Terraform parser using tflocal and LocalStack for complete resource deployment."""

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any

from src.core.common.base_parser import BaseSourceFileParser

logger = logging.getLogger(__name__)


class TerraformParser(BaseSourceFileParser):
    """
    Terraform parser that uses tflocal to deploy and extract complete resource state.

    This parser executes Terraform commands through tflocal to deploy resources
    to LocalStack, then extracts the complete state with all computed attributes
    and relationships for TOSCA mapping.
    """

    def __init__(self, encoding: str = "utf-8"):
        """
        Initialize the Terraform parser.

        Args:
            encoding: File encoding to use when reading files
        """
        super().__init__(encoding)
        self._logger = logger.getChild(self.__class__.__name__)

    def get_supported_extensions(self) -> list[str]:
        """
        Return supported Terraform file extensions.

        Returns:
            List of supported file extensions
        """
        return [".tf", ".tf.json"]

    def can_parse(self, file_path: Path) -> bool:
        """
        Check if this parser can handle the given path.

        For Terraform, we expect a directory containing .tf files.

        Args:
            file_path: Path to check (should be a directory)

        Returns:
            True if the path is a directory containing .tf files
        """
        if not file_path.exists():
            return False

        # If it's a directory, check for .tf files
        if file_path.is_dir():
            tf_files = list(file_path.glob("*.tf")) + list(file_path.glob("*.tf.json"))
            return len(tf_files) > 0

        # If it's a file, check the extension
        return file_path.suffix in self.get_supported_extensions()

    def _parse_content(self, content: str, file_path: Path) -> dict[str, Any]:
        """
        Parse Terraform content by deploying with tflocal and extracting state.

        Note: For Terraform directories, this method is called with empty content
        since we work with the directory directly.

        Args:
            content: File content (unused for directory-based parsing)
            file_path: Path to the Terraform directory or file

        Returns:
            Consolidated state data containing all deployed resources
        """
        # For Terraform, we work with directories, not individual files
        if file_path.is_file():
            terraform_dir = file_path.parent
        else:
            terraform_dir = file_path

        return self._deploy_and_extract_state(terraform_dir)

    def _deploy_and_extract_state(self, terraform_dir: Path) -> dict[str, Any]:
        """
        Deploy Terraform configuration and extract both plan and state data.
        Falls back to plan-only data if deployment fails due to unsupported services.

        Args:
            terraform_dir: Directory containing Terraform files

        Returns:
            Combined data with both plan and state information, or plan-only data
        """
        self._logger.info(f"Starting Terraform deployment for: {terraform_dir}")

        try:
            # Change to the Terraform directory
            original_cwd = Path.cwd()

            # Clean up any stale state that might reference non-existent
            # LocalStack resources
            self._cleanup_stale_state(terraform_dir)

            # Execute Terraform commands in sequence
            self._run_terraform_init(terraform_dir)
            self._run_terraform_plan(terraform_dir)

            # Extract plan JSON (contains variable definitions and references)
            plan_data = self._extract_plan_json(terraform_dir)

            try:
                self._run_terraform_apply(terraform_dir)

                # Extract the complete state (contains resolved values)
                state_data = self._extract_complete_state(terraform_dir)

                # Combine plan and state data in structured format
                combined_data = {
                    "plan": plan_data,
                    "state": state_data,
                }

                self._logger.info(
                    "Successfully deployed and extracted Terraform plan and state"
                )
                return combined_data

            except subprocess.CalledProcessError as apply_error:
                # Check if it's a LocalStack license/service issue
                if self._is_localstack_service_error(apply_error):
                    self._logger.warning(
                        "Terraform apply failed due to LocalStack service limitations. "
                        "Proceeding with plan-only data for mapping."
                    )
                    return self._create_plan_only_data(plan_data)
                else:
                    # Re-raise for other apply errors
                    raise

        except subprocess.CalledProcessError as e:
            self._logger.error(f"Terraform command failed: {e}")
            raise ValueError(f"Terraform deployment failed: {e}") from e
        except Exception as e:
            self._logger.error(f"Failed to deploy Terraform: {e}")
            raise
        finally:
            # Always return to original directory
            if "original_cwd" in locals():
                try:
                    original_cwd.cwd()
                except Exception:
                    pass

    def _is_localstack_service_error(
        self, error: subprocess.CalledProcessError
    ) -> bool:
        """
        Check if the error is due to LocalStack service limitations.

        Args:
            error: The subprocess error from terraform apply

        Returns:
            True if the error is due to LocalStack service/license limitations
        """
        error_text = ""

        # Check both stderr and stdout for error messages
        if error.stderr:
            error_text += error.stderr
        if error.stdout:
            error_text += error.stdout

        if not error_text:
            return False

        error_indicators = [
            "not included in your current license plan",
            "has not yet been emulated by LocalStack",
            "InternalFailure",
            "api error InternalFailure",
        ]

        return any(indicator in error_text for indicator in error_indicators)

    def _create_plan_only_data(self, plan_data: dict[str, Any]) -> dict[str, Any]:
        """
        Create a data structure compatible with the mapper using only plan data.

        Args:
            plan_data: The plan JSON data from terraform

        Returns:
            Data structure that mimics state format for mapper compatibility
        """
        self._logger.info("Creating plan-only data structure for mapping")

        # Extract planned values and convert to state-like format
        planned_values = plan_data.get("planned_values", {})

        # Create a state-like structure with planned values
        synthetic_state = {
            "format_version": "1.0",
            "values": planned_values,
        }

        # Combine plan and synthetic state data in structured format
        combined_data = {
            "plan": plan_data,
            "state": synthetic_state,
        }

        return combined_data

    def _run_terraform_init(self, terraform_dir: Path) -> None:
        """
        Run terraform init to initialize the working directory.

        Args:
            terraform_dir: Directory containing Terraform files
        """
        self._logger.info("Running tflocal init...")

        cmd = ["tflocal", "init"]
        self._run_command(cmd, terraform_dir)

    def _run_terraform_plan(self, terraform_dir: Path) -> None:
        """
        Run terraform plan to create execution plan.

        Args:
            terraform_dir: Directory containing Terraform files
        """
        self._logger.info("Running tflocal plan...")

        cmd = ["tflocal", "plan"]
        self._run_command(cmd, terraform_dir)

    def _run_terraform_apply(self, terraform_dir: Path) -> None:
        """
        Run terraform apply to deploy resources.

        Args:
            terraform_dir: Directory containing Terraform files

        Raises:
            subprocess.CalledProcessError: If apply fails
        """
        self._logger.info("Running tflocal apply...")

        cmd = ["tflocal", "apply", "-auto-approve"]
        # Always capture output for apply to check error messages
        self._run_command(cmd, terraform_dir, capture_output=True)

    def _extract_plan_json(self, terraform_dir: Path) -> dict[str, Any]:
        """
        Extract plan JSON information with variable definitions and references.

        Args:
            terraform_dir: Directory containing Terraform files

        Returns:
            Complete plan data with variables and configuration
        """
        self._logger.info("Extracting Terraform plan JSON...")

        # First, destroy the existing resources to get a fresh plan
        self._logger.debug("Destroying existing resources for clean plan...")
        try:
            destroy_cmd = ["tflocal", "destroy", "-auto-approve"]
            self._run_command(destroy_cmd, terraform_dir)
        except subprocess.CalledProcessError:
            self._logger.warning("Destroy failed, continuing with plan extraction")

        # Get the plan in JSON format with -out to save plan file
        plan_file = "terraform.plan"  # Use relative filename
        cmd = ["tflocal", "plan", "-out", plan_file]
        self._run_command(cmd, terraform_dir)

        # Extract JSON from the saved plan
        cmd = ["tflocal", "show", "-json", plan_file]
        result = self._run_command(cmd, terraform_dir, capture_output=True)

        try:
            plan_data = json.loads(result.stdout)
            configuration = plan_data.get("configuration", {})
            root_module = configuration.get("root_module", {})
            variables = root_module.get("variables", {})
            self._logger.debug(f"Extracted plan with {len(variables)} variables")

            # Clean up the plan file
            plan_file_path = terraform_dir / plan_file
            if plan_file_path.exists():
                plan_file_path.unlink()

            return plan_data
        except json.JSONDecodeError as e:
            self._logger.error(f"Failed to parse plan JSON: {e}")
            raise ValueError(f"Invalid JSON in Terraform plan: {e}") from e

    def _extract_complete_state(self, terraform_dir: Path) -> dict[str, Any]:
        """
        Extract complete state information after deployment.

        Args:
            terraform_dir: Directory containing Terraform files

        Returns:
            Complete state data with all resources
        """
        self._logger.info("Extracting complete Terraform state...")

        # Get the state in JSON format
        cmd = ["tflocal", "show", "-json"]
        result = self._run_command(cmd, terraform_dir, capture_output=True)

        try:
            state_data = json.loads(result.stdout)
            values = state_data.get("values", {})
            root_module = values.get("root_module", {})
            resources = root_module.get("resources", [])
            self._logger.debug(f"Extracted state with {len(resources)} resources")
            return state_data
        except json.JSONDecodeError as e:
            self._logger.error(f"Failed to parse state JSON: {e}")
            raise ValueError(f"Invalid JSON in Terraform state: {e}") from e

    def _run_command(
        self, cmd: list[str], working_dir: Path, capture_output: bool = False
    ) -> subprocess.CompletedProcess:
        """
        Run a shell command in the specified directory.

        Args:
            cmd: Command to run as list of strings
            working_dir: Directory to run command in
            capture_output: Whether to capture stdout/stderr

        Returns:
            CompletedProcess object

        Raises:
            subprocess.CalledProcessError: If command fails
        """
        self._logger.debug(f"Running command: {' '.join(cmd)} in {working_dir}")

        try:
            result = subprocess.run(
                cmd,
                cwd=working_dir,
                check=True,
                capture_output=capture_output,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            if capture_output:
                self._logger.debug(f"Command output: {result.stdout[:500]}...")

            return result

        except subprocess.TimeoutExpired as e:
            self._logger.error(f"Command timed out: {' '.join(cmd)}")
            raise ValueError(f"Terraform command timed out: {' '.join(cmd)}") from e
        except subprocess.CalledProcessError as e:
            self._logger.error(
                f"Command failed with exit code {e.returncode}: {' '.join(cmd)}"
            )
            if e.stderr:
                self._logger.error(f"Error output: {e.stderr}")
            raise

    def validate_file(self, file_path: Path) -> None:
        """
        Validate that the path exists and contains Terraform files.

        Args:
            file_path: Path to validate

        Raises:
            FileNotFoundError: If path doesn't exist
            ValueError: If path doesn't contain valid Terraform files
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Path not found: {file_path}")

        # For directories, check for .tf files
        if file_path.is_dir():
            tf_files = list(file_path.glob("*.tf")) + list(file_path.glob("*.tf.json"))
            if not tf_files:
                raise ValueError(f"No Terraform files found in directory: {file_path}")
            return

        # For files, use parent validation
        super().validate_file(file_path)

    def parse(self, file_path: Path) -> dict[str, Any]:
        """
        Parse Terraform directory by deploying and extracting state.

        Args:
            file_path: Path to Terraform directory or file

        Returns:
            Complete state data with all deployed resources
        """
        self._logger.info(f"Parsing Terraform configuration: {file_path}")

        # Validate the path
        self.validate_file(file_path)

        # For Terraform, we work with directories
        if file_path.is_file():
            terraform_dir = file_path.parent
        else:
            terraform_dir = file_path

        try:
            # Deploy and extract state
            state_data = self._deploy_and_extract_state(terraform_dir)

            self._logger.info(
                f"Successfully parsed Terraform configuration: {terraform_dir}"
            )
            return state_data

        except Exception as e:
            return self._handle_parse_error(e, file_path)

    def _handle_parse_error(self, error: Exception, file_path: Path) -> dict[str, Any]:
        """
        Handle parsing errors with cleanup.

        Args:
            error: The exception that occurred
            file_path: Path that failed to parse

        Raises:
            Exception: Re-raises the original exception
        """
        self._logger.error(f"Failed to parse {file_path}: {error}")

        # Attempt cleanup on error
        try:
            if file_path.is_file():
                terraform_dir = file_path.parent
            else:
                terraform_dir = file_path

            self._cleanup_on_error(terraform_dir)
        except Exception as cleanup_error:
            self._logger.warning(f"Cleanup failed: {cleanup_error}")

        raise error

    def _cleanup_on_error(self, terraform_dir: Path) -> None:
        """
        Cleanup Terraform state on error.

        Args:
            terraform_dir: Directory to cleanup
        """
        self._logger.info("Attempting to cleanup Terraform state on error...")

        try:
            cmd = ["tflocal", "destroy", "-auto-approve"]
            self._run_command(cmd, terraform_dir)
            self._logger.info("Successfully cleaned up Terraform state")
        except Exception as e:
            self._logger.warning(f"Cleanup failed, manual cleanup may be required: {e}")

    def _cleanup_stale_state(self, terraform_dir: Path) -> None:
        """
        Clean up stale Terraform state that might reference non-existent
        LocalStack resources.

        This is necessary because LocalStack doesn't persist state between
        restarts, but Terraform state files do persist and can reference
        resources that no longer exist.

        Args:
            terraform_dir: Directory containing Terraform files
        """
        state_file = terraform_dir / "terraform.tfstate"
        backup_file = terraform_dir / "terraform.tfstate.backup"

        if state_file.exists():
            self._logger.info(
                "Found existing Terraform state, checking for stale references..."
            )

            # Try to validate state by doing a refresh
            try:
                cmd = ["tflocal", "refresh"]
                self._run_command(cmd, terraform_dir, capture_output=True)
                self._logger.debug("State refresh successful, no cleanup needed")
                return
            except subprocess.CalledProcessError:
                # If refresh fails, it's likely due to stale state
                self._logger.warning(
                    "State refresh failed, likely due to LocalStack restart. "
                    "Cleaning up stale state..."
                )

                # Move current state to backup
                if state_file.exists():
                    backup_name = f"terraform.tfstate.backup.{int(time.time())}"
                    backup_path = terraform_dir / backup_name
                    state_file.rename(backup_path)
                    self._logger.info(f"Backed up stale state to: {backup_name}")

                # Remove backup file if it exists
                if backup_file.exists():
                    backup_file.unlink()
                    self._logger.debug("Removed stale backup file")

                self._logger.info("Stale state cleanup completed")
        else:
            self._logger.debug("No existing state file found, no cleanup needed")
