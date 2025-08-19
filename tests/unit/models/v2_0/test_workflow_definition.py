"""Unit tests for WorkflowDefinition class."""

import pytest
from pydantic import ValidationError

from src.models.v2_0.parameter_definition import ParameterDefinition
from src.models.v2_0.workflow_definition import WorkflowDefinition


class TestWorkflowDefinitionBasics:
    """Basic behavior and defaults."""

    def test_defaults(self):
        wf = WorkflowDefinition()
        assert wf.inputs is None
        assert wf.precondition is None
        assert wf.steps is None
        assert wf.implementation is None
        assert wf.outputs is None

    def test_with_inputs_and_outputs(self):
        ins = {
            "retries": ParameterDefinition(type="integer", default=3),
            "timeout": ParameterDefinition(type="integer", default=60),
        }
        outs = {
            "service_url": ParameterDefinition(
                type="string", mapping={"get_attribute": ["web", "url"]}
            )
        }
        wf = WorkflowDefinition(inputs=ins, outputs=outs)
        assert wf.inputs["retries"].default == 3
        assert "get_attribute" in wf.outputs["service_url"].mapping

    def test_with_precondition(self):
        cond = {"and": [{"greater_than": 0}, {"less_than": 100}]}
        wf = WorkflowDefinition(precondition=cond)
        assert wf.precondition == cond


class TestWorkflowDefinitionStepsVsImplementation:
    """Mutual exclusivity between steps and implementation."""

    def test_steps_only(self):
        steps = {
            "s1": {"target": "web", "activities": [{"call_operation": "x"}]},
            "s2": {"target": "db", "on_success": ["s1"]},
        }
        wf = WorkflowDefinition(steps=steps)
        assert wf.steps is not None
        assert wf.implementation is None

    def test_implementation_only(self):
        impl = {"engine": "argo", "entrypoint": "deploy"}
        wf = WorkflowDefinition(implementation=impl)
        assert wf.implementation == impl
        assert wf.steps is None

    def test_both_set_raises(self):
        steps = {"s1": {"target": "web"}}
        impl = {"engine": "argo"}
        with pytest.raises(ValidationError) as exc:
            WorkflowDefinition(steps=steps, implementation=impl)
        assert "mutually exclusive" in str(exc.value)


class TestWorkflowDefinitionSerialization:
    """model_dump behavior."""

    def test_model_dump_exclude_none(self):
        wf = WorkflowDefinition(
            inputs={"k": ParameterDefinition(type="string", default="v")},
            steps={"s": {"target": "web"}},
        )
        dumped = wf.model_dump(exclude_none=True)
        assert "inputs" in dumped
        assert "steps" in dumped
        assert "implementation" not in dumped
        assert dumped["inputs"]["k"]["type"] == "string"

    def test_model_dump_include_none(self):
        wf = WorkflowDefinition()
        dumped = wf.model_dump(exclude_none=False)
        for k in ("inputs", "precondition", "steps", "implementation", "outputs"):
            assert k in dumped


class TestWorkflowDefinitionInheritanceAndEdgeCases:
    """ToscaBase fields, unicode, and empties."""

    def test_toscabase_fields(self):
        wf = WorkflowDefinition(
            description="A test workflow",
            metadata={"owner": "unit-test"},
        )
        assert wf.description == "A test workflow"
        assert wf.metadata == {"owner": "unit-test"}

    def test_unicode_values(self):
        wf = WorkflowDefinition(
            precondition={"msg": "ok ✅"},
            steps={"deploy_✨": {"target": "web🚀"}},
            description="Workflow 🌟",
        )
        assert "✅" in wf.precondition["msg"]
        assert "✨" in list(wf.steps.keys())[0]
        assert "🚀" in wf.steps["deploy_✨"]["target"]
        assert "🌟" in wf.description

    def test_empty_dicts_allowed(self):
        wf = WorkflowDefinition(inputs={}, steps={}, outputs={})
        assert wf.inputs == {}
        assert wf.steps == {}
        assert wf.outputs == {}
