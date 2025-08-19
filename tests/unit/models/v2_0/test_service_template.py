# tests/test_service_template.py
import pytest
from pydantic import ValidationError

from src.models.v2_0.group_definition import GroupDefinition
from src.models.v2_0.node_template import NodeTemplate
from src.models.v2_0.policy_definition import PolicyDefinition
from src.models.v2_0.service_template import ServiceTemplate
from src.models.v2_0.workflow_definition import WorkflowDefinition


class TestServiceTemplate:
    def test_minimal_valid_service_template(self):
        """Creates the smallest valid ServiceTemplate: just one NodeTemplate."""
        st = ServiceTemplate(
            node_templates={"web": NodeTemplate(type="WebApplication")}
        )
        assert "web" in st.node_templates
        assert st.node_templates["web"].type == "WebApplication"

    def test_accepts_plain_dict_for_nested_node_template(self):
        """
        Pydantic should coerce dicts into NodeTemplate instances when nested.
        """
        st = ServiceTemplate(node_templates={"db": {"type": "Database"}})
        assert st.node_templates["db"].type == "Database"
        assert isinstance(st.node_templates["db"], NodeTemplate)

    def test_missing_required_node_templates_raises(self):
        """node_templates is mandatory."""
        with pytest.raises(ValidationError):
            ServiceTemplate()  # type: ignore[call-arg]

    def test_invalid_node_template_directive_propagates_validation_error(self):
        """
        NodeTemplate validates directives; an invalid directive should surface
        as a ValidationError during ServiceTemplate construction.
        """
        with pytest.raises(ValidationError):
            ServiceTemplate(
                node_templates={
                    "bad": NodeTemplate(type="Anything", directives=["bogus"])
                }
            )

    def test_groups_policies_workflows_ok(self):
        """
        Populates optional groups, policies, and workflows with minimal valid content.
        """
        st = ServiceTemplate(
            node_templates={"web": {"type": "WebApp"}},
            groups={"frontend": GroupDefinition(type="MyGroupType")},
            policies=[
                PolicyDefinition(
                    type="ScalingPolicy",
                    properties={"min_instances": 1},
                    targets=["web"],
                )
            ],
            workflows={
                # Minimal imperative workflow: only steps OR implementation, not both
                "deploy": WorkflowDefinition(steps={"start": {"run": "noop"}})
            },
            # inputs/outputs are Any by design for this model
            inputs={"env": "prod"},
            outputs={"endpoint": "$get_attribute: ..."},
        )
        assert "frontend" in st.groups
        assert st.policies and st.policies[0].type == "ScalingPolicy"
        assert "deploy" in st.workflows

    def test_workflow_steps_vs_implementation_conflict_raises(self):
        """
        WorkflowDefinition enforces mutual exclusivity between 'steps' and
        'implementation'; violation should raise during ServiceTemplate creation.
        """
        with pytest.raises(ValidationError):
            ServiceTemplate(
                node_templates={"web": {"type": "Web"}},
                workflows={
                    "bad": {
                        "steps": {"a": {"run": "noop"}},
                        "implementation": {"ref": "external-impl"},
                    }
                },
            )

    def test_inputs_and_outputs_allow_any_mapping(self):
        """
        The ServiceTemplate model types inputs/outputs as dict[str, Any];
        accept arbitrary structures.
        """
        st = ServiceTemplate(
            node_templates={"n1": {"type": "X"}},
            inputs={"raw": {"nested": [1, 2, 3]}},
            outputs={"result": {"expression": {"$concat": ["a", "b"]}}},
        )
        assert isinstance(st.inputs["raw"]["nested"], list)
        assert "result" in st.outputs
