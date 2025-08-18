import datetime
import os
from io import StringIO
from typing import Any

from pydantic import BaseModel
from ruamel.yaml import YAML

from .artifact_definition import ArtifactDefinition
from .capability_assignment import CapabilityAssignment
from .group_definition import GroupDefinition
from .interface_assignment import InterfaceAssignment
from .node_template import NodeTemplate
from .policy_definition import PolicyDefinition
from .requirement_assignment import RequirementAssignment
from .service_template import ServiceTemplate
from .tosca_file import ToscaFile
from .workflow_definition import WorkflowDefinition


class NodeTemplateBuilder:
    """Fluent builder for creating NodeTemplate objects"""

    def __init__(self, name: str, node_type: str):
        self.name = name
        self._data: dict[str, Any] = {"type": node_type}

    def with_description(self, description: str) -> "NodeTemplateBuilder":
        """Adds a description to the node"""
        self._data["description"] = description
        return self

    def with_metadata(self, metadata: dict[str, Any]) -> "NodeTemplateBuilder":
        """Adds metadata to the node"""
        self._data["metadata"] = metadata
        return self

    def with_directives(self, *directives: str) -> "NodeTemplateBuilder":
        """Adds directives to the node (create, select, substitute)"""
        self._data["directives"] = list(directives)
        return self

    def with_property(self, name: str, value: Any) -> "NodeTemplateBuilder":
        """Adds a single property"""
        if "properties" not in self._data:
            self._data["properties"] = {}
        self._data["properties"][name] = value
        return self

    def with_properties(self, properties: dict[str, Any]) -> "NodeTemplateBuilder":
        """Adds multiple properties"""
        if "properties" not in self._data:
            self._data["properties"] = {}
        self._data["properties"].update(properties)
        return self

    def with_attribute(self, name: str, value: Any) -> "NodeTemplateBuilder":
        """Adds a single attribute"""
        if "attributes" not in self._data:
            self._data["attributes"] = {}
        self._data["attributes"][name] = value
        return self

    def with_attributes(self, attributes: dict[str, Any]) -> "NodeTemplateBuilder":
        """Adds multiple attributes"""
        if "attributes" not in self._data:
            self._data["attributes"] = {}
        self._data["attributes"].update(attributes)
        return self

    def with_count(self, count: int) -> "NodeTemplateBuilder":
        """Sets the count to create multiple instances"""
        self._data["count"] = count
        return self

    def with_copy(self, template_name: str) -> "NodeTemplateBuilder":
        """Copies from another template"""
        self._data["copy"] = template_name
        return self

    def add_requirement(self, name: str) -> "RequirementBuilder":
        """Adds a requirement and returns a builder to configure it"""
        return RequirementBuilder(self, name)

    def add_capability(self, name: str) -> "CapabilityBuilder":
        """Adds a capability and returns a builder to configure it"""
        return CapabilityBuilder(self, name)

    def add_interface(self, name: str) -> "InterfaceBuilder":
        """Adds an interface and returns a builder to configure it"""
        return InterfaceBuilder(self, name)

    def add_artifact(
        self, name: str, artifact_type: str, file_path: str
    ) -> "ArtifactBuilder":
        """Adds an artifact and returns a builder to configure it"""
        return ArtifactBuilder(self, name, artifact_type, file_path)

    def build(self) -> NodeTemplate:
        """Builds the final NodeTemplate object"""
        return NodeTemplate(**self._data)


class RequirementBuilder:
    """Builder for requirement assignment"""

    def __init__(self, parent: NodeTemplateBuilder, req_name: str):
        self.parent = parent
        self.req_name = req_name
        self._data: dict[str, Any] = {}

    def to_node(self, node_name: str) -> "RequirementBuilder":
        """Specifies the target node"""
        self._data["node"] = node_name
        return self

    def to_capability(self, capability: str) -> "RequirementBuilder":
        """Specifies the target capability"""
        self._data["capability"] = capability
        return self

    def with_relationship(
        self, relationship: str | dict[str, Any]
    ) -> "RequirementBuilder":
        """Specifies the relationship"""
        self._data["relationship"] = relationship
        return self

    def with_count(self, count: int) -> "RequirementBuilder":
        """Specifies the count for the requirement"""
        self._data["count"] = count
        return self

    def optional(self, is_optional: bool = True) -> "RequirementBuilder":
        """Marks the requirement as optional"""
        self._data["optional"] = is_optional
        return self

    def and_node(self) -> NodeTemplateBuilder:
        """Finalizes the requirement and returns to the node builder"""
        if "requirements" not in self.parent._data:
            self.parent._data["requirements"] = []

        req_assignment = RequirementAssignment(**self._data)
        # Add the requirement with its name as a dict entry
        req_dict = {self.req_name: req_assignment}
        self.parent._data["requirements"].append(req_dict)
        return self.parent


class CapabilityBuilder:
    """Builder for capability assignment"""

    def __init__(self, parent: NodeTemplateBuilder, cap_name: str):
        self.parent = parent
        self.cap_name = cap_name
        self._data: dict[str, Any] = {}

    def with_property(self, name: str, value: Any) -> "CapabilityBuilder":
        """Adds a property to the capability"""
        if "properties" not in self._data:
            self._data["properties"] = {}
        self._data["properties"][name] = value
        return self

    def with_properties(self, properties: dict[str, Any]) -> "CapabilityBuilder":
        """Adds multiple properties to the capability"""
        if "properties" not in self._data:
            self._data["properties"] = {}
        self._data["properties"].update(properties)
        return self

    def with_directives(self, *directives: str) -> "CapabilityBuilder":
        """Adds directives (internal, external)"""
        self._data["directives"] = list(directives)
        return self

    def and_node(self) -> NodeTemplateBuilder:
        """Finalizes the capability and returns to the node builder"""
        if "capabilities" not in self.parent._data:
            self.parent._data["capabilities"] = {}

        cap_assignment = CapabilityAssignment(**self._data)
        self.parent._data["capabilities"][self.cap_name] = cap_assignment
        return self.parent


class InterfaceBuilder:
    """Builder for interface assignment"""

    def __init__(self, parent: NodeTemplateBuilder, interface_name: str):
        self.parent = parent
        self.interface_name = interface_name
        self._data: dict[str, Any] = {}

    def with_input(self, name: str, value: Any) -> "InterfaceBuilder":
        """Adds an input parameter"""
        if "inputs" not in self._data:
            self._data["inputs"] = {}
        # Semplificato - in realtà dovrebbe essere ParameterDefinition
        self._data["inputs"][name] = {"value": value}
        return self

    def and_node(self) -> NodeTemplateBuilder:
        """Finalizes the interface and returns to the node builder"""
        if "interfaces" not in self.parent._data:
            self.parent._data["interfaces"] = {}

        interface_assignment = InterfaceAssignment(**self._data)
        self.parent._data["interfaces"][self.interface_name] = interface_assignment
        return self.parent


class ArtifactBuilder:
    """Builder for artifact definition"""

    def __init__(
        self,
        parent: NodeTemplateBuilder,
        artifact_name: str,
        artifact_type: str,
        file_path: str,
    ):
        self.parent = parent
        self.artifact_name = artifact_name
        self._data = {"type": artifact_type, "file": file_path}

    def with_repository(self, repository: str) -> "ArtifactBuilder":
        """Specifies the repository"""
        self._data["repository"] = repository
        return self

    def with_version(self, version: str) -> "ArtifactBuilder":
        """Specifies the version"""
        self._data["artifact_version"] = version
        return self

    def with_checksum(
        self, checksum: str, algorithm: str = "SHA-256"
    ) -> "ArtifactBuilder":
        """Adds checksum and algorithm"""
        self._data["checksum"] = checksum
        self._data["checksum_algorithm"] = algorithm
        return self

    def and_node(self) -> NodeTemplateBuilder:
        """Finalizes the artifact and returns to the node builder"""
        if "artifacts" not in self.parent._data:
            self.parent._data["artifacts"] = {}

        artifact_def = ArtifactDefinition(**self._data)
        self.parent._data["artifacts"][self.artifact_name] = artifact_def
        return self.parent


class ServiceTemplateBuilder:
    """Fluent builder for creating ServiceTemplate objects"""

    def __init__(self):
        self._data = {"node_templates": {}}
        self._node_builders = {}

    def with_description(self, description: str) -> "ServiceTemplateBuilder":
        """Adds a description to the service template"""
        self._data["description"] = description
        return self

    def with_metadata(self, metadata: dict[str, Any]) -> "ServiceTemplateBuilder":
        """Adds metadata to the service template"""
        self._data["metadata"] = metadata
        return self

    def with_input(
        self, name: str, param_type: str, **kwargs
    ) -> "ServiceTemplateBuilder":
        """Adds an input parameter"""
        if "inputs" not in self._data:
            self._data["inputs"] = {}

        # Debug: Check for overwrites
        if name in self._data["inputs"]:
            existing_type = self._data["inputs"][name].get("type", "unknown")
            if existing_type != param_type:
                print(
                    "BUILDER WARNING: Overwriting input "
                    f"'{name}' type '{existing_type}' -> '{param_type}'"
                )

        param_def = {"type": param_type}
        param_def.update(kwargs)
        self._data["inputs"][name] = param_def
        return self

    def with_output(self, name: str, **kwargs) -> "ServiceTemplateBuilder":
        """Adds an output parameter"""
        if "outputs" not in self._data:
            self._data["outputs"] = {}
        self._data["outputs"][name] = kwargs
        return self

    def add_node(self, name: str, node_type: str) -> NodeTemplateBuilder:
        """Adds a node and returns a builder to configure it"""
        node_builder = NodeTemplateBuilder(name, node_type)
        self._node_builders[name] = node_builder
        return node_builder

    def add_group(self, name: str, group_type: str) -> "GroupBuilder":
        """Adds a group and returns a builder to configure it"""
        return GroupBuilder(self, name, group_type)

    def add_policy(self, name: str, policy_type: str) -> "PolicyBuilder":
        """Adds a policy and returns a builder to configure it"""
        return PolicyBuilder(self, name, policy_type)

    def add_workflow(self, name: str) -> "WorkflowBuilder":
        """Adds a workflow and returns a builder to configure it"""
        return WorkflowBuilder(self, name)

    def build(self) -> ServiceTemplate:
        """Builds the final ServiceTemplate object"""
        # Finalizza tutti i node template
        for name, builder in self._node_builders.items():
            self._data["node_templates"][name] = builder.build()

        return ServiceTemplate(**self._data)


class GroupBuilder:
    """Builder for group definition"""

    def __init__(self, parent: ServiceTemplateBuilder, name: str, group_type: str):
        self.parent = parent
        self.name = name
        self._data: dict[str, Any] = {"type": group_type}

    def with_members(self, *members: str) -> "GroupBuilder":
        """Adds members to the group"""
        self._data["members"] = list(members)
        return self

    def with_property(self, name: str, value: Any) -> "GroupBuilder":
        """Adds a property to the group"""
        if "properties" not in self._data:
            self._data["properties"] = {}
        self._data["properties"][name] = value
        return self

    def and_service(self) -> ServiceTemplateBuilder:
        """Finalizes the group and returns to the service template builder"""
        if "groups" not in self.parent._data:
            self.parent._data["groups"] = {}

        group_def = GroupDefinition(**self._data)
        self.parent._data["groups"][self.name] = group_def
        return self.parent


class PolicyBuilder:
    """Builder for policy definition"""

    def __init__(self, parent: ServiceTemplateBuilder, name: str, policy_type: str):
        self.parent = parent
        self.name = name
        self._data: dict[str, Any] = {"type": policy_type}

    def with_targets(self, *targets: str) -> "PolicyBuilder":
        """Specifies the targets of the policy"""
        self._data["targets"] = list(targets)
        return self

    def with_property(self, name: str, value: Any) -> "PolicyBuilder":
        """Adds a property to the policy"""
        if "properties" not in self._data:
            self._data["properties"] = {}
        self._data["properties"][name] = value
        return self

    def and_service(self) -> ServiceTemplateBuilder:
        """Finalizes the policy and returns to the service template builder"""
        if "policies" not in self.parent._data:
            self.parent._data["policies"] = []

        # Create a dictionary with the policy name as key
        policy_def = PolicyDefinition(**self._data)
        policy_dict = {self.name: policy_def}
        self.parent._data["policies"].append(policy_dict)
        return self.parent


class WorkflowBuilder:
    """Builder for workflow definition"""

    def __init__(self, parent: ServiceTemplateBuilder, name: str):
        self.parent = parent
        self.name = name
        self._data: dict[str, Any] = {}

    def with_input(self, name: str, param_type: str, **kwargs) -> "WorkflowBuilder":
        """Adds an input parameter"""
        if "inputs" not in self._data:
            self._data["inputs"] = {}

        param_def = {"type": param_type}
        param_def.update(kwargs)
        self._data["inputs"][name] = param_def
        return self

    def with_step(self, name: str, step_def: dict[str, Any]) -> "WorkflowBuilder":
        """Adds a step to the workflow"""
        if "steps" not in self._data:
            self._data["steps"] = {}
        self._data["steps"][name] = step_def
        return self

    def and_service(self) -> ServiceTemplateBuilder:
        """Finalizes the workflow and returns to the service template builder"""
        if "workflows" not in self.parent._data:
            self.parent._data["workflows"] = {}

        workflow_def = WorkflowDefinition(**self._data)
        self.parent._data["workflows"][self.name] = workflow_def
        return self.parent


class ToscaFileBuilder:
    """Main builder for creating a complete TOSCA file with YAML export capabilities"""

    def __init__(self, tosca_version: str = "tosca_2_0"):
        self._data: dict[str, Any] = {"tosca_definitions_version": tosca_version}
        self._service_template_builder: ServiceTemplateBuilder | None = None

        # Initialize YAML serializer
        self._yaml = YAML()
        self._configure_yaml()

    def _configure_yaml(self):
        """Configura il serializzatore YAML per TOSCA"""
        self._yaml.indent(mapping=2, sequence=4, offset=2)
        self._yaml.default_flow_style = False
        self._yaml.allow_unicode = True
        self._yaml.width = 4096
        self._yaml.map_indent = 2
        self._yaml.sequence_indent = 4
        self._yaml.preserve_quotes = True

        # Custom representer per mantenere l'ordine delle chiavi TOSCA
        def represent_ordered_dict(dumper, data):
            tosca_key_order = [
                "tosca_definitions_version",
                "description",
                "metadata",
                "profile",
                "imports",
                "repositories",
                "dsl_definitions",
                "service_template",
            ]

            service_template_order = [
                "description",
                "metadata",
                "inputs",
                "outputs",
                "node_templates",
                "relationship_templates",
                "groups",
                "policies",
                "workflows",
            ]

            if isinstance(data, dict):
                ordered_items = []
                key_order = (
                    tosca_key_order
                    if "tosca_definitions_version" in data
                    else service_template_order
                )

                # Prima le chiavi nell'ordine preferito
                for key in key_order:
                    if key in data:
                        ordered_items.append((key, data[key]))

                # Poi le altre chiavi
                for key, value in data.items():
                    if key not in key_order:
                        ordered_items.append((key, value))

                # Convert to dictionary format that ruamel.yaml expects
                ordered_dict = dict(ordered_items)
                return dumper.represent_mapping("tag:yaml.org,2002:map", ordered_dict)

            return dumper.represent_dict(data)

        self._yaml.representer.add_representer(dict, represent_ordered_dict)

    def with_description(self, description: str) -> "ToscaFileBuilder":
        """Adds a description to the TOSCA file"""
        self._data["description"] = description
        return self

    def with_metadata(self, metadata: dict[str, Any]) -> "ToscaFileBuilder":
        """Adds metadata to the TOSCA file"""
        self._data["metadata"] = metadata
        return self

    def with_profile(self, profile: str) -> "ToscaFileBuilder":
        """Specifies the TOSCA profile"""
        self._data["profile"] = profile
        return self

    def with_import(self, import_def: str | dict[str, Any]) -> "ToscaFileBuilder":
        """Adds an import"""
        if "imports" not in self._data:
            self._data["imports"] = []
        self._data["imports"].append(import_def)
        return self

    def with_repository(
        self, name: str, repo_def: dict[str, Any]
    ) -> "ToscaFileBuilder":
        """Adds a repository"""
        if "repositories" not in self._data:
            self._data["repositories"] = {}
        self._data["repositories"][name] = repo_def
        return self

    def with_dsl_definition(self, name: str, definition: Any) -> "ToscaFileBuilder":
        """Adds a DSL definition (YAML alias)"""
        if "dsl_definitions" not in self._data:
            self._data["dsl_definitions"] = {}
        self._data["dsl_definitions"][name] = definition
        return self

    def add_service_template(self) -> "ServiceTemplateBuilder":
        """Adds a service template and returns a builder to configure it"""
        self._service_template_builder = ServiceTemplateBuilder()
        return self._service_template_builder

    def build(self) -> ToscaFile:
        """Builds the final ToscaFile object"""
        if self._service_template_builder:
            self._data["service_template"] = self._service_template_builder.build()

        return ToscaFile(**self._data)

    # ===== YAML SERIALIZATION METHODS =====

    def to_dict(self) -> dict[str, Any]:
        """Converts the builder data to a dictionary for YAML serialization"""
        result = self._data.copy()

        # Convert service template builder to dict if present
        if self._service_template_builder:
            result["service_template"] = self._service_template_to_dict(
                self._service_template_builder
            )

        # Add generation metadata
        if "metadata" not in result:
            result["metadata"] = {}

        result["metadata"].update(
            {
                "generated_by": "TOSCA Infrastructure Intent Discovery",
                "generation_timestamp": datetime.datetime.now().isoformat(),
                "generator_version": "1.0.0",
            }
        )

        return result

    def _service_template_to_dict(
        self, st_builder: "ServiceTemplateBuilder"
    ) -> dict[str, Any]:
        """Converts ServiceTemplateBuilder to dictionary"""
        result = st_builder._data.copy()

        # Convert node templates
        if st_builder._node_builders:
            result["node_templates"] = {}
            for name, node_builder in st_builder._node_builders.items():
                result["node_templates"][name] = self._node_template_to_dict(
                    node_builder
                )

        # Convert policies if present
        if "policies" in result and result["policies"]:
            converted_policies = []
            for policy_dict in result["policies"]:
                # Each policy_dict is {policy_name: PolicyDefinition}
                converted_policy_dict = {}
                for policy_name, policy_obj in policy_dict.items():
                    converted_policy = self._object_to_dict(policy_obj)
                    if converted_policy is not None:
                        converted_policy_dict[policy_name] = converted_policy
                if converted_policy_dict:
                    converted_policies.append(converted_policy_dict)
            if converted_policies:
                result["policies"] = converted_policies
            else:
                del result["policies"]

        return result

    def _node_template_to_dict(self, node_builder) -> dict[str, Any]:
        """Converts NodeTemplateBuilder to dictionary, excluding None values"""
        result = {}

        # Convert complex objects to dictionaries, excluding None values
        for key, value in node_builder._data.items():
            if isinstance(value, BaseModel):
                converted_value = self._object_to_dict(value)
                if converted_value is not None:
                    result[key] = converted_value
            elif isinstance(value, list):
                converted_list = []
                for item in value:
                    if item is not None:
                        if isinstance(item, BaseModel):
                            converted_item = self._object_to_dict(item)
                            if converted_item is not None:
                                converted_list.append(converted_item)
                        elif isinstance(item, dict):
                            # Handle dictionaries within lists (like requirements)
                            converted_dict = {}
                            for k, v in item.items():
                                if isinstance(v, BaseModel):
                                    converted_value = self._object_to_dict(v)
                                    if converted_value is not None:
                                        converted_dict[k] = converted_value
                                elif v is not None:
                                    converted_dict[k] = (
                                        self._object_to_dict(v)
                                        if hasattr(v, "__dict__")
                                        else v
                                    )
                            if converted_dict:
                                converted_list.append(converted_dict)
                        elif hasattr(item, "__dict__"):
                            converted_item = self._object_to_dict(item)
                            if converted_item is not None:
                                converted_list.append(converted_item)
                        else:
                            converted_list.append(item)
                if converted_list:
                    result[key] = converted_list
            elif isinstance(value, dict):
                converted_dict = {}
                for k, v in value.items():
                    if isinstance(v, BaseModel):
                        converted_value = self._object_to_dict(v)
                        if converted_value is not None:
                            converted_dict[k] = converted_value
                    elif v is not None:
                        converted_value = (
                            self._object_to_dict(v) if hasattr(v, "__dict__") else v
                        )
                        if converted_value is not None:
                            converted_dict[k] = converted_value
                if converted_dict:
                    result[key] = converted_dict
            elif hasattr(value, "__dict__") and not isinstance(
                value, str | int | float | bool
            ):
                converted_value = self._object_to_dict(value)
                if converted_value is not None:
                    result[key] = converted_value
            elif value is not None:
                result[key] = value

        return result

    def _object_to_dict(self, obj) -> Any:
        """
        Converts any object to dictionary recursively,
        excluding None values and empty collections.
        """

        if obj is None:
            return None
        elif isinstance(obj, str | int | float | bool):
            return obj
        elif isinstance(obj, list):
            result_list = [
                self._object_to_dict(item) for item in obj if item is not None
            ]
            return result_list if result_list else None
        elif isinstance(obj, dict):
            result_dict = {}
            for k, v in obj.items():
                converted_value = self._object_to_dict(v)
                if converted_value is not None:
                    result_dict[k] = converted_value
            return result_dict if result_dict else None
        elif isinstance(obj, BaseModel):
            # Handle Pydantic models using model_dump()
            model_dict = obj.model_dump(exclude_none=True)
            result = {}
            for k, v in model_dict.items():
                converted_value = self._object_to_dict(v)
                if converted_value is not None:
                    result[k] = converted_value
            return result if result else None
        elif hasattr(obj, "__dict__"):
            result = {}
            for attr_name, attr_value in obj.__dict__.items():
                if not attr_name.startswith("_"):
                    converted_value = self._object_to_dict(attr_value)
                    if converted_value is not None:
                        result[attr_name] = converted_value
            return result if result else None
        else:
            return str(obj)

    def to_yaml(self, output_path: str | None = None) -> str:
        """
        Converts the TOSCA file to YAML format

        Args:
            output_path: Optional file path to save the YAML

        Returns:
            YAML string representation
        """
        tosca_dict = self.to_dict()

        # Serialize to YAML
        stream = StringIO()
        self._yaml.dump(tosca_dict, stream)
        yaml_content = stream.getvalue()

        # Save to file if path provided
        if output_path:
            self.save_yaml_to_file(yaml_content, output_path)

        return yaml_content

    def save_yaml(self, file_path: str) -> str:
        """
        Saves the TOSCA file as YAML to the specified path

        Args:
            file_path: Path where to save the YAML file

        Returns:
            YAML string that was saved
        """
        return self.to_yaml(file_path)

    def save_yaml_to_file(self, yaml_content: str, file_path: str):
        """Saves YAML content to file"""
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(yaml_content)

        print(f"✅ TOSCA YAML saved to: {file_path}")


# Factory methods for easier usage
def create_tosca_file(tosca_version: str = "tosca_2_0") -> ToscaFileBuilder:
    """Factory method to create a new TOSCA file"""
    return ToscaFileBuilder(tosca_version)


def create_service_template() -> ServiceTemplateBuilder:
    """Factory method to create a standalone service template"""
    return ServiceTemplateBuilder()


def create_node_template(name: str, node_type: str) -> NodeTemplateBuilder:
    """Factory method to create a standalone node template"""
    return NodeTemplateBuilder(name, node_type)
