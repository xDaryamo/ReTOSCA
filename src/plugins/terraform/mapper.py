import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from src.core.common.base_mapper import BaseResourceMapper

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder

logger = logging.getLogger(__name__)


class TerraformMapper(BaseResourceMapper):
    """
    Terraform-specific mapper.

    Knows how to navigate the JSON produced by
    `terraform show -json` to find all resources defined in the plan.
    """

    def __init__(self) -> None:
        super().__init__()
        # Keep the plan data available for sub-mappers
        self._current_parsed_data: dict[str, Any] | None = None

    def map(
        self,
        parsed_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
    ) -> None:
        """
        Override to keep parsed_data available to sub-mappers and handle
        two-pass processing.
        """
        self._current_parsed_data = parsed_data

        # First pass: create all nodes (excluding associations)
        self._logger.info("Starting first pass: creating all primary resources")
        resources = list(self._extract_resources(parsed_data))

        # Separate association resources from primary resources
        primary_resources = []
        association_resources = []

        for resource_name, resource_type, resource_data in resources:
            association_types = ["aws_route_table_association", "aws_volume_attachment"]
            if resource_type in association_types:
                association_resources.append(
                    (resource_name, resource_type, resource_data)
                )
            else:
                primary_resources.append((resource_name, resource_type, resource_data))

        # Process primary resources first
        for resource_name, resource_type, resource_data in primary_resources:
            self._process_single_resource(
                resource_name, resource_type, resource_data, builder
            )

        # Second pass: process associations after all nodes are created
        if association_resources:
            self._logger.info(
                "Starting second pass: processing associations and relationships"
            )
            for resource_name, resource_type, resource_data in association_resources:
                self._process_single_resource(
                    resource_name, resource_type, resource_data, builder
                )

        self._logger.info("Resource mapping process completed.")

    def _process_single_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: "ServiceTemplateBuilder",
    ) -> None:
        """Process a single resource using the appropriate mapper."""
        mapper_strategy = self._mappers.get(resource_type)

        if mapper_strategy:
            # Uses can_map for a finer check
            if mapper_strategy.can_map(resource_type, resource_data):
                self._logger.debug(
                    f"Mapping resource '{resource_name}' ({resource_type})"
                )
                # Delegates work to the specific strategy class
                mapper_strategy.map_resource(
                    resource_name, resource_type, resource_data, builder
                )
            else:
                self._logger.warning(
                    f"The mapper for '{resource_type}' cannot handle "
                    f"the specific configuration of '{resource_name}'. "
                    "Skipping."
                )
        else:
            self._logger.warning(
                f"No mapper registered for resource type: '{resource_type}'. "
                "Skipping."
            )

    def get_current_parsed_data(self) -> dict[str, Any]:
        """Return current plan data for sub-mappers."""
        return self._current_parsed_data or {}

    @staticmethod
    def extract_terraform_references(
        resource_data: dict[str, Any],
        parsed_data: dict[str, Any] | None = None,
    ) -> list[tuple[str, str, str]]:
        """
        Extract all Terraform references from a resource to create TOSCA
        requirements.

        Args:
            resource_data: Single resource data (from planned_values).
            parsed_data: Full plan dict (needed to access `configuration`).

        Returns:
            List of tuples (property_name, target_resource_address, relationship_type),
            e.g., [("vpc_id", "aws_vpc.main", "DependsOn")].
        """
        references: list[tuple[str, str, str]] = []

        # Without parsed_data we can't inspect `configuration`
        if not parsed_data:
            return references

        # Address of the current resource
        resource_address = resource_data.get("address")
        if not resource_address:
            return references

        # Find the matching configuration entry
        configuration = parsed_data.get("configuration", {})
        root_module = configuration.get("root_module", {})
        config_resources = root_module.get("resources", [])

        config_resource: dict[str, Any] | None = None
        for config_res in config_resources:
            if config_res.get("address") == resource_address:
                config_resource = config_res
                break

        if not config_resource:
            return references

        # Extract references from the resource's expressions
        expressions = config_resource.get("expressions", {})
        for prop_name, expr_data in expressions.items():
            if isinstance(expr_data, dict) and "references" in expr_data:
                terraform_refs = expr_data["references"]
                for ref in set(terraform_refs):  # avoid duplicates
                    if ref and ref.endswith(".id"):
                        # Strip `.id` to get the clean reference
                        clean_ref = ref[:-3]
                        rel = TerraformMapper._determine_terraform_relationship_type(
                            prop_name, clean_ref
                        )
                        references.append((prop_name, clean_ref, rel))
                    elif ref:
                        rel = TerraformMapper._determine_terraform_relationship_type(
                            prop_name, ref
                        )
                        references.append((prop_name, ref, rel))

        return references

    @staticmethod
    def _determine_terraform_relationship_type(
        property_name: str, target_resource: str
    ) -> str:
        """
        Determine the TOSCA relationship type based on a Terraform property
        name and the target resource.
        """
        # Common AWS/Terraform patterns
        if property_name in ["vpc_id", "subnet_id", "subnet_ids"]:
            return "DependsOn"
        if property_name in ["security_group_ids", "security_groups"]:
            # Could be ConnectsTo in some cases
            return "DependsOn"
        if "network" in property_name.lower():
            if "aws_network" in target_resource or "aws_subnet" in target_resource:
                return "LinksTo"  # network connections
            return "DependsOn"
        if property_name in ["load_balancer", "target_group", "load_balancer_arn"]:
            return "ConnectsTo"
        if property_name in ["instance_id", "instance_ids"]:
            return "HostedOn"  # compute-container relationship
        # Generic default
        return "DependsOn"

    def _extract_resources(
        self, parsed_data: dict[str, Any]
    ) -> Iterable[tuple[str, str, dict[str, Any]]]:
        """
        Extract all resources from a Terraform plan JSON.

        Yields:
            (resource_full_address, resource_type, resource_data)
        """
        self._logger.info("Inizio estrazione delle risorse dal piano Terraform.")

        planned_values = parsed_data.get("planned_values")
        if not planned_values:
            self._logger.warning(
                "Nessuna chiave 'planned_values' trovata nel JSON. "
                "Nessuna risorsa da mappare."
            )
            return

        root_module = planned_values.get("root_module")
        if not root_module:
            self._logger.warning("Nessun 'root_module' trovato in 'planned_values'.")
            return

        # Recurse through modules
        yield from self._find_resources_in_module(root_module)

    def _find_resources_in_module(
        self, module_data: dict[str, Any]
    ) -> Iterable[tuple[str, str, dict[str, Any]]]:
        """Recursively extract resources from a module and its submodules."""
        # 1) Resources in this module
        for resource in module_data.get("resources", []):
            resource_type = resource.get("type")
            resource_name = resource.get("name")
            full_address = resource.get("address")  # e.g., "aws_instance.app_server"

            if not (resource_type and resource_name and full_address):
                continue

            self._logger.debug(
                f"Trovata risorsa: {full_address} (Tipo: {resource_type})"
            )
            # Return full address as name, type, and raw data
            yield full_address, resource_type, resource

        # 2) Recurse into child modules
        for child in module_data.get("child_modules", []):
            yield from self._find_resources_in_module(child)
