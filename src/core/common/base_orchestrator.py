"""Base implementation for orchestrators."""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from ..protocols import Orchestrator, ResourceMapper, SourceFileParser

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder


logger = logging.getLogger(__name__)


class BaseOrchestrator(Orchestrator, ABC):
    """
    Abstract base class for orchestrators.

    Provides common functionality for file discovery, orchestration flow, and output
    generation while keeping vendor-specific parser and mapper logic abstract.

    Subclasses must implement:
    - get_parser(): Return the vendor-specific parser
    - get_mapper(): Return the vendor-specific mapper

    Subclasses can optionally override:
    - find_source_files(): Custom file discovery logic
    - create_builder(): Custom builder creation
    - save_output(): Custom output saving logic
    """

    def __init__(self):
        """Initialize the orchestrator."""
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

    def translate(
        self, source_path: Path, output_file: Path
    ) -> "ServiceTemplateBuilder":
        """
        Orchestrates the entire translation process.

        This method coordinates the full workflow:
        1. Find and parse source files
        2. Map parsed resources to a TOSCA model using the builder
        3. Save the final TOSCA file

        Args:
            source_path: Path to the source directory or file
            output_file: Path where to save the TOSCA output file
        """
        self._logger.info(f"Starting translation: {source_path} -> {output_file}")

        try:
            # Step 1: Find source files
            source_files = self.find_source_files(source_path)
            if not source_files:
                raise ValueError(f"No supported source files found in {source_path}")

            self._logger.info(f"Found {len(source_files)} source files")

            # Step 2: Create builder and get components
            builder = self.create_builder()
            parser = self.get_parser()
            mapper = self.get_mapper()

            # Step 3: Parse and map each source file
            for source_file in source_files:
                self._logger.debug(f"Processing file: {source_file}")

                # Parse the file
                parsed_data = parser.parse(source_file)

                # Map to TOSCA using the builder
                mapper.map(parsed_data, builder)

            # Step 4: Save the final TOSCA file
            self.save_output(builder, output_file)

            self._logger.info(f"Translation completed successfully: {output_file}")

            return builder

        except Exception as e:
            self._logger.error(f"Translation failed: {e}")
            raise

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

    def create_builder(self) -> "ServiceTemplateBuilder":
        """
        Create a ServiceTemplateBuilder instance.

        Subclasses can override this method to customize builder creation.

        Returns:
            A new ServiceTemplateBuilder instance
        """
        from src.models.v2_0.builder import ServiceTemplateBuilder

        return ServiceTemplateBuilder()

    def save_output(self, builder: "ServiceTemplateBuilder", output_file: Path) -> None:
        """
        Save the TOSCA service template to file with proper TOSCA 2.0 structure.

        Creates a complete TOSCA file with:
        - TOSCA 2.0 version declaration
        - Standard imports for TOSCA Simple Profile
        - Service template with all nodes and configurations

        Args:
            builder: The populated ServiceTemplateBuilder
            output_file: Path where to save the output
        """
        # Ensure output directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Create a complete TOSCA file using ToscaFileBuilder
        from src.models.v2_0.builder import ToscaFileBuilder

        tosca_file_builder = ToscaFileBuilder("tosca_2_0")

        # Add standard imports for TOSCA Simple Profile
        tosca_file_builder.with_import(
            {
                "url": "https://raw.githubusercontent.com/xDaryamo/tosca-community-contributions/refs/heads/master/profiles/org/oasis-open/simple/2.0/profile.yaml"
            }
        )

        # Add the service template
        service_template_builder = tosca_file_builder.add_service_template()

        # Copy all data from the provided builder to the new service template
        self._copy_service_template_data(builder, service_template_builder)

        # Save the complete TOSCA file using the builder's YAML capabilities
        tosca_file_builder.save_yaml(str(output_file))

        self._logger.debug(f"Complete TOSCA 2.0 file saved to: {output_file}")

    def _copy_service_template_data(
        self,
        source_builder: "ServiceTemplateBuilder",
        target_builder: "ServiceTemplateBuilder",
    ) -> None:
        """
        Copy all data from source ServiceTemplateBuilder to target.

        Args:
            source_builder: Source builder with the data
            target_builder: Target builder to receive the data
        """
        # Copy basic service template data
        if "description" in source_builder._data:
            target_builder.with_description(source_builder._data["description"])

        if "metadata" in source_builder._data:
            target_builder.with_metadata(source_builder._data["metadata"])

        if "inputs" in source_builder._data:
            for input_name, input_def in source_builder._data["inputs"].items():
                param_type = input_def.get("type", "string")
                # Extract other properties
                other_props = {k: v for k, v in input_def.items() if k != "type"}
                target_builder.with_input(input_name, param_type, **other_props)

        if "outputs" in source_builder._data:
            for output_name, output_def in source_builder._data["outputs"].items():
                target_builder.with_output(output_name, **output_def)

        # Copy node builders
        for node_name, node_builder in source_builder._node_builders.items():
            # Create new node in target
            target_node = target_builder.add_node(node_name, node_builder._data["type"])

            # Copy all node data
            if "description" in node_builder._data:
                target_node.with_description(node_builder._data["description"])

            if "metadata" in node_builder._data:
                target_node.with_metadata(node_builder._data["metadata"])

            if "directives" in node_builder._data:
                target_node.with_directives(*node_builder._data["directives"])

            if "properties" in node_builder._data:
                target_node.with_properties(node_builder._data["properties"])

            if "attributes" in node_builder._data:
                target_node.with_attributes(node_builder._data["attributes"])

            if "count" in node_builder._data:
                target_node.with_count(node_builder._data["count"])

            if "copy" in node_builder._data:
                target_node.with_copy(node_builder._data["copy"])

            # Copy capabilities
            if "capabilities" in node_builder._data:
                for cap_name, cap_assignment in node_builder._data[
                    "capabilities"
                ].items():
                    cap_builder = target_node.add_capability(cap_name)

                    if (
                        hasattr(cap_assignment, "properties")
                        and cap_assignment.properties
                    ):
                        cap_builder.with_properties(cap_assignment.properties)

                    if (
                        hasattr(cap_assignment, "directives")
                        and cap_assignment.directives
                    ):
                        cap_builder.with_directives(*cap_assignment.directives)

                    cap_builder.and_node()

            # Copy requirements
            if "requirements" in node_builder._data:
                for req_dict in node_builder._data["requirements"]:
                    for req_name, req_assignment in req_dict.items():
                        req_builder = target_node.add_requirement(req_name)

                        if hasattr(req_assignment, "node") and req_assignment.node:
                            req_builder.to_node(req_assignment.node)

                        if (
                            hasattr(req_assignment, "capability")
                            and req_assignment.capability
                        ):
                            req_builder.to_capability(req_assignment.capability)

                        if (
                            hasattr(req_assignment, "relationship")
                            and req_assignment.relationship
                        ):
                            req_builder.with_relationship(req_assignment.relationship)

                        if hasattr(req_assignment, "count") and req_assignment.count:
                            req_builder.with_count(req_assignment.count)

                        if (
                            hasattr(req_assignment, "optional")
                            and req_assignment.optional
                        ):
                            req_builder.optional(req_assignment.optional)

                        req_builder.and_node()

        # Copy groups, policies, workflows if present
        if "groups" in source_builder._data:
            for group_name, group_def in source_builder._data["groups"].items():
                group_builder = target_builder.add_group(group_name, group_def.type)

                if hasattr(group_def, "members") and group_def.members:
                    group_builder.with_members(*group_def.members)

                if hasattr(group_def, "properties") and group_def.properties:
                    for prop_name, prop_value in group_def.properties.items():
                        group_builder.with_property(prop_name, prop_value)

                group_builder.and_service()

        if "policies" in source_builder._data:
            for policy_dict in source_builder._data["policies"]:
                for policy_name, policy_def in policy_dict.items():
                    policy_builder = target_builder.add_policy(
                        policy_name, policy_def.type
                    )

                    if hasattr(policy_def, "targets") and policy_def.targets:
                        policy_builder.with_targets(*policy_def.targets)

                    if hasattr(policy_def, "properties") and policy_def.properties:
                        for prop_name, prop_value in policy_def.properties.items():
                            policy_builder.with_property(prop_name, prop_value)

                    # Copy metadata if present
                    if hasattr(policy_def, "metadata") and policy_def.metadata:
                        policy_builder.with_metadata(policy_def.metadata)

                    policy_builder.and_service()

        if "workflows" in source_builder._data:
            for workflow_name, workflow_def in source_builder._data[
                "workflows"
            ].items():
                workflow_builder = target_builder.add_workflow(workflow_name)

                if hasattr(workflow_def, "inputs") and workflow_def.inputs:
                    for input_name, input_def in workflow_def.inputs.items():
                        param_type = input_def.get("type", "string")
                        other_props = {
                            k: v for k, v in input_def.items() if k != "type"
                        }
                        workflow_builder.with_input(
                            input_name, param_type, **other_props
                        )

                if hasattr(workflow_def, "steps") and workflow_def.steps:
                    for step_name, step_def in workflow_def.steps.items():
                        workflow_builder.with_step(step_name, step_def)

                workflow_builder.and_service()

    def get_orchestrator_info(self) -> dict:
        """
        Get information about this orchestrator.

        Useful for debugging and plugin introspection.

        Returns:
            Dictionary containing orchestrator information
        """
        parser = self.get_parser()
        mapper = self.get_mapper()

        return {
            "class_name": self.__class__.__name__,
            "module": self.__class__.__module__,
            "parser": {
                "class_name": parser.__class__.__name__,
                "supported_extensions": parser.get_supported_extensions(),
            },
            "mapper": {"class_name": mapper.__class__.__name__},
        }
