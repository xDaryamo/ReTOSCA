"""Pipeline runner for orchestrating multiple phase plugins."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.models.v2_0.builder import ServiceTemplateBuilder

from .protocols import PhasePlugin

logger = logging.getLogger(__name__)


class PipelineRunner:
    """
    Coordinates the execution of multiple phase plugins in sequence.

    The PipelineRunner manages the shared ServiceTemplateBuilder state object
    that flows through the pipeline, enabling incremental enrichment of the
    TOSCA model from multiple IaC sources.
    """

    def __init__(self, plugins: list[PhasePlugin] | None = None):
        """
        Initialize the pipeline runner.

        Args:
            plugins: List of phase plugins to execute in order
        """
        self._logger = logger.getChild(self.__class__.__name__)
        self._plugins: list[PhasePlugin] = plugins or []

    def add_plugin(self, plugin: PhasePlugin) -> "PipelineRunner":
        """
        Add a plugin to the pipeline.

        Args:
            plugin: The phase plugin to add

        Returns:
            Self for method chaining
        """
        self._plugins.append(plugin)
        return self

    def clear_plugins(self) -> "PipelineRunner":
        """
        Clear all plugins from the pipeline.

        Returns:
            Self for method chaining
        """
        self._plugins.clear()
        return self

    def get_plugins(self) -> list[PhasePlugin]:
        """
        Get the current list of plugins.

        Returns:
            List of configured plugins
        """
        return self._plugins.copy()

    def execute(
        self,
        source_inputs: list[tuple[Path, PhasePlugin]] | None = None,
        output_file: Path | None = None,
    ) -> "ServiceTemplateBuilder":
        """
        Execute the pipeline with the configured plugins.

        Args:
            source_inputs: List of (source_path, plugin) tuples to process.
                          If None, uses configured plugins with auto-discovery.
            output_file: Optional output file path. If provided, saves TOSCA to file.

        Returns:
            The populated ServiceTemplateBuilder

        Raises:
            ValueError: If no plugins are configured or source inputs provided
            RuntimeError: If pipeline execution fails
        """
        if not source_inputs and not self._plugins:
            raise ValueError("No plugins configured and no source inputs provided")

        self._logger.info("Starting pipeline execution")

        try:
            # Create shared ServiceTemplateBuilder
            builder = self._create_builder()

            # Process source inputs if provided, otherwise use configured plugins
            if source_inputs:
                self._execute_with_source_inputs(source_inputs, builder)
            else:
                self._execute_with_configured_plugins(builder)

            # Save output if requested
            if output_file:
                self._save_output(builder, output_file)
                self._logger.info(f"Pipeline output saved to: {output_file}")

            self._logger.info("Pipeline execution completed successfully")
            return builder

        except Exception as e:
            self._logger.error(f"Pipeline execution failed: {e}")
            raise RuntimeError(f"Pipeline execution failed: {e}") from e

    def execute_simple(
        self, source_path: Path, output_file: Path
    ) -> "ServiceTemplateBuilder":
        """
        Execute a simple pipeline with auto-discovered plugins for a single source.

        This method provides backward compatibility and simplified usage for
        single-source scenarios.

        Args:
            source_path: Path to source directory or file
            output_file: Path where to save the TOSCA output file

        Returns:
            The populated ServiceTemplateBuilder

        Raises:
            ValueError: If no compatible plugins found for source
        """
        # Find compatible plugins for the source path
        compatible_plugins = [
            plugin for plugin in self._plugins if plugin.can_handle(source_path)
        ]

        if not compatible_plugins:
            raise ValueError(f"No compatible plugins found for source: {source_path}")

        # Use the first compatible plugin
        plugin = compatible_plugins[0]
        if len(compatible_plugins) > 1:
            self._logger.warning(
                f"Multiple plugins can handle {source_path}, "
                f"using {plugin.__class__.__name__}"
            )

        # Execute with single source input
        source_inputs = [(source_path, plugin)]
        return self.execute(source_inputs, output_file)

    def _execute_with_source_inputs(
        self,
        source_inputs: list[tuple[Path, PhasePlugin]],
        builder: "ServiceTemplateBuilder",
    ) -> None:
        """
        Execute pipeline with specific source input and plugin pairs.

        Args:
            source_inputs: List of (source_path, plugin) tuples
            builder: ServiceTemplateBuilder to enrich
        """
        for i, (source_path, plugin) in enumerate(source_inputs):
            self._logger.info(
                f"Executing plugin {i + 1}/{len(source_inputs)}: "
                f"{plugin.__class__.__name__}"
            )

            try:
                plugin.execute(source_path, builder)
                self._logger.debug(
                    f"Plugin {plugin.__class__.__name__} completed successfully"
                )
            except Exception as e:
                self._logger.error(f"Plugin {plugin.__class__.__name__} failed: {e}")
                raise

    def _execute_with_configured_plugins(
        self, builder: "ServiceTemplateBuilder"
    ) -> None:
        """
        Execute pipeline with configured plugins (requires external source discovery).

        Args:
            builder: ServiceTemplateBuilder to enrich

        Note:
            This method is a placeholder for future auto-discovery functionality.
            Currently raises NotImplementedError.
        """
        raise NotImplementedError(
            "Auto-discovery mode not yet implemented. "
            "Use execute() with source_inputs parameter."
        )

    def _create_builder(self) -> "ServiceTemplateBuilder":
        """
        Create a new ServiceTemplateBuilder instance.

        Returns:
            A new ServiceTemplateBuilder instance
        """
        from src.models.v2_0.builder import ServiceTemplateBuilder

        return ServiceTemplateBuilder()

    def _save_output(
        self, builder: "ServiceTemplateBuilder", output_file: Path
    ) -> None:
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

            # Copy all node data from source to target
            self._copy_node_data(node_builder, target_node)

        # Copy groups, policies, workflows if present
        self._copy_service_template_collections(source_builder, target_builder)

    def _copy_node_data(self, source_node: Any, target_node: Any) -> None:
        """Copy node data from source to target node builder."""
        # Copy basic node properties
        if "description" in source_node._data:
            target_node.with_description(source_node._data["description"])

        if "metadata" in source_node._data:
            target_node.with_metadata(source_node._data["metadata"])

        if "directives" in source_node._data:
            target_node.with_directives(*source_node._data["directives"])

        if "properties" in source_node._data:
            target_node.with_properties(source_node._data["properties"])

        if "attributes" in source_node._data:
            target_node.with_attributes(source_node._data["attributes"])

        if "count" in source_node._data:
            target_node.with_count(source_node._data["count"])

        if "copy" in source_node._data:
            target_node.with_copy(source_node._data["copy"])

        # Copy capabilities
        if "capabilities" in source_node._data:
            for cap_name, cap_assignment in source_node._data["capabilities"].items():
                cap_builder = target_node.add_capability(cap_name)

                if hasattr(cap_assignment, "properties") and cap_assignment.properties:
                    cap_builder.with_properties(cap_assignment.properties)

                if hasattr(cap_assignment, "directives") and cap_assignment.directives:
                    cap_builder.with_directives(*cap_assignment.directives)

                cap_builder.and_node()

        # Copy requirements
        if "requirements" in source_node._data:
            for req_dict in source_node._data["requirements"]:
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

                    if hasattr(req_assignment, "optional") and req_assignment.optional:
                        req_builder.optional(req_assignment.optional)

                    req_builder.and_node()

    def _copy_service_template_collections(
        self,
        source_builder: "ServiceTemplateBuilder",
        target_builder: "ServiceTemplateBuilder",
    ) -> None:
        """Copy groups, policies, and workflows from source to target."""
        # Copy groups
        if "groups" in source_builder._data:
            for group_name, group_def in source_builder._data["groups"].items():
                group_builder = target_builder.add_group(group_name, group_def.type)

                if hasattr(group_def, "members") and group_def.members:
                    group_builder.with_members(*group_def.members)

                if hasattr(group_def, "properties") and group_def.properties:
                    for prop_name, prop_value in group_def.properties.items():
                        group_builder.with_property(prop_name, prop_value)

                group_builder.and_service()

        # Copy policies
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

                    if hasattr(policy_def, "metadata") and policy_def.metadata:
                        policy_builder.with_metadata(policy_def.metadata)

                    policy_builder.and_service()

        # Copy workflows
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

    def get_pipeline_info(self) -> dict[str, Any]:
        """
        Get information about the current pipeline configuration.

        Returns:
            Dictionary with pipeline metadata and plugin information
        """
        plugin_info = []
        for plugin in self._plugins:
            try:
                info = plugin.get_plugin_info()
                plugin_info.append(info)
            except Exception as e:
                self._logger.warning(
                    f"Could not get info for plugin {plugin.__class__.__name__}: {e}"
                )
                plugin_info.append({"name": plugin.__class__.__name__, "error": str(e)})

        return {
            "runner_class": self.__class__.__name__,
            "plugin_count": len(self._plugins),
            "plugins": plugin_info,
        }
