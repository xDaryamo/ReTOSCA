"""
Terraform Plugin Exception Classes

Custom exceptions for better error handling and debugging in the Terraform plugin.
"""


class TerraformPluginError(Exception):
    """Base exception for all Terraform plugin errors."""

    pass


class TerraformDataError(TerraformPluginError):
    """Raised when Terraform data is invalid or missing required fields."""

    pass


class VariableExtractionError(TerraformPluginError):
    """Raised when variable extraction fails."""

    pass


class ResourceMappingError(TerraformPluginError):
    """Raised when resource mapping encounters an error."""

    pass


class ReferenceResolutionError(TerraformPluginError):
    """Raised when Terraform reference resolution fails."""

    pass


class OutputMappingError(TerraformPluginError):
    """Raised when output mapping encounters an error."""

    pass


class ValidationError(TerraformPluginError):
    """Raised when input validation fails."""

    pass
