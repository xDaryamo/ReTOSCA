import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

# Import the base class from core
from core.common.base_parser import BaseSourceFileParser

logger = logging.getLogger(__name__)


class TerraformParser(BaseSourceFileParser):
    """
    A parser for Terraform projects that leverages the Terraform CLI.

    This parser does not read .tf files directly. Instead, it runs
    'terraform plan' and 'terraform show -json' to obtain a single
    JSON object representing the planned state of the entire
    infrastructure. This approach is much more robust because it
    automatically handles variables, modules, and Terraform's internal logic.
    """

    def __init__(self, terraform_binary: str = "terraform", **kwargs):
        """
        Initializes the Terraform parser.

        Args:
            terraform_binary: Path to the terraform binary (default: "terraform")
        """
        super().__init__(**kwargs)
        self.terraform_binary = terraform_binary

    def get_supported_extensions(self) -> list[str]:
        """
        Indicates that this parser is interested in .tf files for discovery,
        even though it will operate on the containing directory.
        """
        return [".tf"]

    def can_parse(self, path: Path) -> bool:
        """
        Checks whether the path is a directory containing Terraform files.
        """
        if not path.is_dir():
            return False
        # Checks if there are any .tf files in the directory
        return any(path.glob("*.tf"))

    def parse(self, project_path: Path) -> dict[str, Any]:
        """
        Orchestrates the execution of Terraform commands to get the plan in JSON format.

        Args:
            project_path: The path to the main Terraform project directory.

        Returns:
            A Python dictionary representing the Terraform plan.

        Raises:
            FileNotFoundError: If the project directory does not exist.
            RuntimeError: If the 'terraform' command is not installed or if
                          the 'init', 'plan', or 'show' commands fail.
        """
        self._logger.info(f"Starting parsing of Terraform project in: {project_path}")

        if not self.can_parse(project_path):
            raise ValueError(
                f"The path '{project_path}' is not a valid Terraform directory."
            )

        # Check for existing cached JSON plan
        json_plan_file = project_path / "terraform-plan.json"
        if json_plan_file.exists():
            self._logger.info(
                "Found existing JSON plan file: %s, loading from cache",
                json_plan_file.name,
            )
            try:
                with json_plan_file.open("r", encoding="utf-8") as f:
                    cached_plan = json.load(f)
                self._logger.info("Successfully loaded plan from cached JSON file")
                return cached_plan
            except (OSError, json.JSONDecodeError) as e:
                self._logger.warning(
                    f"Failed to load cached JSON plan: {e}. Will regenerate."
                )
                # Continue to regenerate the plan

        # 1. Check that the Terraform CLI is installed
        self._check_terraform_binary()

        try:
            # Check if there's already a plan file (tfplan, plan.tfplan, etc.)
            existing_plan_files = list(project_path.glob("*.tfplan"))
            if existing_plan_files:
                # Use the first existing plan file
                plan_file = existing_plan_files[0]
                self._logger.info(f"Found existing plan file: {plan_file.name}")
            else:
                # Create a new plan file
                import time

                timestamp = int(time.time())
                plan_file = project_path / f"tf-parser-plan-{timestamp}.tfplan"

                # 2. Run 'terraform init'
                self._logger.debug(f"Running 'terraform init' in {project_path}")
                self._run_command(
                    ["terraform", "init", "-input=false", "-no-color"], cwd=project_path
                )

                # 3. Run 'terraform plan'
                self._logger.debug(f"Running 'terraform plan' in {project_path}")
                self._run_command(
                    [
                        "terraform",
                        "plan",
                        f"-out={plan_file}",
                        "-input=false",
                        "-no-color",
                    ],
                    cwd=project_path,
                )

            # 4. Run 'terraform show -json'
            self._logger.debug(
                f"Running 'terraform show' to extract JSON from {plan_file.name}"
            )
            json_output = self._run_command(
                ["terraform", "show", "-json", str(plan_file)], cwd=project_path
            )

            # 5. Save the JSON output to file for future use with proper formatting
            try:
                # Parse and re-format the JSON for better readability
                parsed_json = json.loads(json_output)
                with json_plan_file.open("w", encoding="utf-8") as f:
                    json.dump(
                        parsed_json, f, indent=2, ensure_ascii=False, sort_keys=True
                    )
                self._logger.info(
                    f"Saved formatted JSON plan to: {json_plan_file.name}"
                )
            except (OSError, json.JSONDecodeError) as e:
                self._logger.warning(f"Failed to save JSON plan to file: {e}")
                # Fallback: save raw output if JSON parsing fails
                try:
                    with json_plan_file.open("w", encoding="utf-8") as f:
                        f.write(json_output)
                    self._logger.info(f"Saved raw JSON plan to: {json_plan_file.name}")
                except OSError:
                    pass  # Give up on saving

            # 6. Clean up the plan file only if we created it (not existing ones)
            if plan_file.name.startswith("tf-parser-plan-"):
                try:
                    plan_file.unlink()
                except Exception as e:
                    self._logger.warning(f"Unable to remove plan file {plan_file}: {e}")

            self._logger.info(
                "Parsing of the Terraform project completed successfully."
            )
            return json.loads(json_output)

        except (
            subprocess.CalledProcessError,
            json.JSONDecodeError,
            FileNotFoundError,
        ) as e:
            # Cleanup plan file even in case of error
            try:
                if "plan_file" in locals() and plan_file.exists():
                    plan_file.unlink()
            except Exception:
                pass  # Ignore cleanup errors

            # Use the base class's error handler to log and re-raise
            return self._handle_parse_error(e, project_path)
        except Exception as e:
            self._logger.error(
                f"Unexpected error during parsing of {project_path}: {e}"
            )
            raise

    def _check_terraform_binary(self) -> None:
        """Checks that the Terraform binary is available and working."""
        if not shutil.which(self.terraform_binary):
            self._logger.error(
                "Command '%s' not found. Make sure it is installed and in your PATH.",
                self.terraform_binary,
            )
            raise RuntimeError(f"Terraform CLI '{self.terraform_binary}' not found.")

        # Quick version check
        try:
            result = subprocess.run(
                [self.terraform_binary, "version"],
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8",
            )
            if result.returncode == 0:
                self._logger.debug(
                    f"Terraform available: {result.stdout.strip().splitlines()[0]}"
                )
            else:
                raise RuntimeError(f"Terraform check failed: {result.stderr}")
        except subprocess.TimeoutExpired as err:
            raise RuntimeError("Timeout during Terraform check") from err

    def _run_command(self, command: list[str], cwd: Path, timeout: int = 300) -> str:
        """
        Helper to run a shell command and handle errors.

        Args:
            command: List of command components
            cwd: Working directory
            timeout: Timeout in seconds (default: 5 minutes)
        """
        try:
            process = subprocess.run(
                command,
                cwd=str(cwd),
                check=True,  # Raise exception if command fails
                capture_output=True,
                text=True,  # Decode stdout/stderr as text
                encoding="utf-8",
                timeout=timeout,
            )
            return process.stdout
        except subprocess.TimeoutExpired as err:
            self._logger.error(
                f"Command timed out after {timeout}s: {' '.join(command)}"
            )
            raise RuntimeError(f"Command timeout: {' '.join(command)}") from err
        except subprocess.CalledProcessError as e:
            self._logger.error(f"Command failed: {' '.join(command)}")
            self._logger.error(f"Error: {e.stderr}")
            raise

    # --- Override base class methods not applicable ---

    def _read_file(self, file_path: Path) -> str:
        """Not applicable for this parser, logic is in `parse`."""
        raise NotImplementedError(
            "TerraformParser operates on directories, not single files."
        )

    def _parse_content(self, content: str, file_path: Path) -> dict[str, Any]:
        """Not applicable for this parser, logic is in `parse`."""
        raise NotImplementedError(
            "TerraformParser does not parse content of single files."
        )

    def validate_file(self, file_path: Path) -> None:
        """
        Override validation to handle directories instead of files.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Path not found: {file_path}")

        if not file_path.is_dir():
            raise ValueError(
                f"TerraformParser requires a directory, received: {file_path}"
            )

        if not self.can_parse(file_path):
            raise ValueError(f"Directory does not contain Terraform files: {file_path}")

    def clear_plan_cache(self, project_path: Path) -> bool:
        """
        Removes the cached JSON plan file to force regeneration on next parse.

        Args:
            project_path: The path to the Terraform project directory.

        Returns:
            True if cache was cleared, False if no cache existed.
        """
        json_plan_file = project_path / "terraform-plan.json"
        if json_plan_file.exists():
            try:
                json_plan_file.unlink()
                self._logger.info(f"Cleared cached JSON plan: {json_plan_file.name}")
                return True
            except OSError as e:
                self._logger.error(f"Failed to clear cached JSON plan: {e}")
                raise
        else:
            self._logger.debug("No cached JSON plan to clear")
            return False
