"""
Terraform Plugin Exception Classes

Custom exceptions for better error handling and debugging in the Terraform plugin.
"""

from typing import Any


class TerraformPluginError(Exception):
    """Base exception for all Terraform plugin errors."""

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.context = context or {}

    def __str__(self) -> str:
        base_msg = super().__str__()
        if self.error_code:
            base_msg = f"[{self.error_code}] {base_msg}"
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            base_msg = f"{base_msg} (Context: {context_str})"
        return base_msg


class TerraformDataError(TerraformPluginError):
    """Raised when Terraform data is invalid or missing required fields."""

    def __init__(
        self,
        message: str,
        resource_name: str | None = None,
        missing_field: str | None = None,
    ) -> None:
        context = {}
        if resource_name:
            context["resource_name"] = resource_name
        if missing_field:
            context["missing_field"] = missing_field
        super().__init__(message, "TERRAFORM_DATA_ERROR", context)

    def get_recovery_hint(self) -> str:
        """Provide a helpful hint for fixing the data error."""
        if "missing_field" in self.context:
            field = self.context["missing_field"]
            return (
                f"Ensure the '{field}' field is present in the Terraform configuration"
            )
        return "Check the Terraform configuration for missing or invalid data"


class VariableExtractionError(TerraformPluginError):
    """Raised when variable extraction fails."""

    def __init__(
        self,
        message: str,
        variable_name: str | None = None,
        extraction_phase: str | None = None,
    ) -> None:
        context = {}
        if variable_name:
            context["variable_name"] = variable_name
        if extraction_phase:
            context["extraction_phase"] = extraction_phase
        super().__init__(message, "VARIABLE_EXTRACTION_ERROR", context)


class ResourceMappingError(TerraformPluginError):
    """Raised when resource mapping encounters an error."""

    def __init__(
        self,
        message: str,
        resource_name: str | None = None,
        resource_type: str | None = None,
        mapping_phase: str | None = None,
    ) -> None:
        context = {}
        if resource_name:
            context["resource_name"] = resource_name
        if resource_type:
            context["resource_type"] = resource_type
        if mapping_phase:
            context["mapping_phase"] = mapping_phase
        super().__init__(message, "RESOURCE_MAPPING_ERROR", context)


class ReferenceResolutionError(TerraformPluginError):
    """Raised when Terraform reference resolution fails."""

    def __init__(
        self,
        message: str,
        reference: str | None = None,
        target_resource: str | None = None,
    ) -> None:
        context = {}
        if reference:
            context["reference"] = reference
        if target_resource:
            context["target_resource"] = target_resource
        super().__init__(message, "REFERENCE_RESOLUTION_ERROR", context)


class OutputMappingError(TerraformPluginError):
    """Raised when output mapping encounters an error."""

    def __init__(
        self,
        message: str,
        output_name: str | None = None,
        output_type: str | None = None,
    ) -> None:
        context = {}
        if output_name:
            context["output_name"] = output_name
        if output_type:
            context["output_type"] = output_type
        super().__init__(message, "OUTPUT_MAPPING_ERROR", context)


class ValidationError(TerraformPluginError):
    """Raised when input validation fails."""

    def __init__(
        self,
        message: str,
        field_name: str | None = None,
        expected_type: type | None = None,
        actual_value: Any = None,
    ) -> None:
        context = {}
        if field_name:
            context["field_name"] = field_name
        if expected_type:
            context["expected_type"] = expected_type.__name__
        if actual_value is not None:
            context["actual_value"] = str(actual_value)
        super().__init__(message, "VALIDATION_ERROR", context)

    def get_recovery_hint(self) -> str:
        """Provide a helpful hint for fixing the validation error."""
        if "field_name" in self.context and "expected_type" in self.context:
            field = self.context["field_name"]
            expected = self.context["expected_type"]
            return f"Ensure '{field}' is of type {expected}"
        return "Check the input data format and required fields"
