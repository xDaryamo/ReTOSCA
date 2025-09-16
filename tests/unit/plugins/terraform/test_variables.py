from __future__ import annotations

import pytest

from src.plugins.provisioning.terraform.variables import (
    OutputDefinition,
    OutputExtractor,
    OutputMapper,
    PropertyResolver,
    ToscaInputDefinition,
    VariableContext,
    VariableExtractor,
    VariableReferenceTracker,
)


@pytest.fixture()
def parsed_data() -> dict:
    return {
        "plan": {
            "configuration": {
                "root_module": {
                    "variables": {
                        "env": {
                            "type": "string",
                            "default": "dev",
                            "description": "environment",
                        },
                        "instance_type": {
                            "type": "string",
                            "default": "t3.micro",
                        },
                        "cidr_map": {
                            "type": "map(string)",
                            "default": {
                                "public": "10.0.1.0/24",
                                "private": "10.0.2.0/24",
                            },
                        },
                        "subnets": {
                            "type": "list(string)",
                            "default": ["sub1", "sub2"],
                        },
                        "count": {
                            "type": "number",
                            "default": 3,
                        },
                        "secret": {
                            "type": "string",
                            "sensitive": True,
                        },
                    },
                    "resources": [
                        {
                            "address": "aws_instance.web",
                            "expressions": {
                                # explicit reference to a variable
                                "instance_type": {"references": ["var.instance_type"]},
                            },
                        },
                        {
                            "address": "aws_subnet.example[0]",
                            "expressions": {
                                # reference to map-type variable
                                "cidr_block": {"references": ["var.cidr_map"]},
                            },
                        },
                        {
                            # no reference; will be detected as list-pattern
                            "address": "aws_subnet.example[1]",
                            "expressions": {"name": {}},
                        },
                    ],
                    "outputs": {
                        "web_public_ip": {
                            "description": "Public IP of web",
                            "expression": {
                                "references": ["aws_instance.web.public_ip"]
                            },
                            "sensitive": False,
                        },
                        "just_region": {
                            "description": "Hardcoded region",
                            "expression": {},
                            "sensitive": False,
                        },
                        "sensitive_secret_out": {
                            "description": "Top secret",
                            "expression": {},
                            "sensitive": True,
                        },
                    },
                }
            },
            "planned_values": {
                "root_module": {
                    "resources": [
                        {
                            "address": "aws_instance.web",
                            "values": {
                                "instance_type": "t3.micro",
                                "private_ip": "10.0.0.10",
                                "public_ip": "1.2.3.4",
                                "public_dns": "ec2.amazonaws.com",
                                "id": "i-abc",
                            },
                        },
                        {
                            "address": "aws_subnet.example[0]",
                            "values": {
                                "cidr_block": "10.0.1.0/24",
                                "tags": {"Name": "public"},
                            },
                        },
                        {
                            "address": "aws_subnet.example[1]",
                            "values": {
                                "name": "sub2",
                                "cidr_block": "10.0.2.0/24",
                            },
                        },
                    ],
                    "outputs": {
                        "web_public_ip": {"value": "1.2.3.4"},
                        "just_region": {"value": "eu-west-1"},
                        "sensitive_secret_out": {"value": "dontshow"},
                    },
                }
            },
        },
        "state": {
            # not necessary for these tests, but present for completeness
        },
    }


# ---------------------------------------------------------------------------
# VariableExtractor & conversion to TOSCA inputs
# ---------------------------------------------------------------------------


def test_extract_variables_and_convert_to_tosca_inputs(parsed_data):
    ve = VariableExtractor()
    vars_map = ve.extract_variables(parsed_data)

    assert set(vars_map.keys()) >= {
        "env",
        "instance_type",
        "cidr_map",
        "subnets",
        "count",
        "secret",
    }

    # Types and required mapping
    inputs = ve.convert_to_tosca_inputs(vars_map)

    def _inp(name):
        assert name in inputs, f"Missing input {name}"
        return inputs[name]

    env = _inp("env")
    assert env.param_type == "string"
    assert env.default == "dev"
    assert env.required is False

    instance_type = _inp("instance_type")
    assert instance_type.param_type == "string"
    assert instance_type.default == "t3.micro"
    assert instance_type.required is False

    cidr_map = _inp("cidr_map")
    assert cidr_map.param_type == "map"
    assert cidr_map.entry_schema == "string"
    assert cidr_map.required is False

    subnets = _inp("subnets")
    assert subnets.param_type == "list"
    assert subnets.entry_schema == "string"

    count = _inp("count")
    assert count.param_type == "float"  # number -> float
    assert count.default == 3

    secret = _inp("secret")
    assert secret.param_type == "string"
    assert secret.default is None
    assert secret.required is True  # no default


# ---------------------------------------------------------------------------
# OutputExtractor & conversion to TOSCA outputs
# ---------------------------------------------------------------------------


def test_extract_outputs_and_convert_to_tosca_outputs(parsed_data):
    ox = OutputExtractor()
    outs = ox.extract_outputs(parsed_data)

    assert set(outs.keys()) == {"web_public_ip", "just_region", "sensitive_secret_out"}

    # Resolved values read from planned_values
    assert outs["web_public_ip"].value == "1.2.3.4"
    assert outs["just_region"].value == "eu-west-1"
    assert outs["sensitive_secret_out"].value == "dontshow"
    assert outs["sensitive_secret_out"].sensitive is True

    tosca_outs = ox.convert_to_tosca_outputs(outs)
    # The sensitive one should be excluded
    assert set(tosca_outs.keys()) == {"web_public_ip", "just_region"}


# ---------------------------------------------------------------------------
# OutputMapper: mapping to get_attribute when possible
# ---------------------------------------------------------------------------


def test_output_mapper_maps_get_attribute_when_reference_and_mapping(parsed_data):
    mapper = OutputMapper(parsed_data)

    # Build OutputDefinition consistent with parsed_data
    od = OutputDefinition(
        name="web_public_ip",
        description="Public IP of web",
        sensitive=False,
        value="1.2.3.4",
    )

    # Map of Terraform resources -> TOSCA names
    tosca_nodes = {
        "aws_instance.web": "compute_web",
    }

    val = mapper.map_output_value(od, tosca_nodes)
    # Should be $get_attribute with mapped attribute
    # aws_instance.public_ip -> public_address
    assert isinstance(val, dict) and "$get_attribute" in val
    assert val["$get_attribute"] == ["compute_web", "public_address"]


def test_output_mapper_falls_back_to_literal_when_no_reference(parsed_data):
    mapper = OutputMapper(parsed_data)
    od = OutputDefinition(
        name="just_region",
        description="region",
        sensitive=False,
        value="eu-west-1",
    )
    out = mapper.map_output_value(od, {})
    assert out == "eu-west-1"


# ---------------------------------------------------------------------------
# VariableReferenceTracker & PropertyResolver
# ---------------------------------------------------------------------------


def test_reference_tracker_builds_maps_and_patterns(parsed_data):
    tr = VariableReferenceTracker(parsed_data)

    # Direct reference to variable
    assert tr.is_variable_reference("aws_instance.web", "instance_type")
    assert tr.get_variable_name("aws_instance.web", "instance_type") == "instance_type"
    assert tr.get_resolved_value("aws_instance.web", "instance_type") == "t3.micro"

    # Map-variable pattern on cidr_map
    mv = tr.get_map_variable_reference("aws_subnet.example[0]", "cidr_block")
    assert mv == ("cidr_map", "public")

    # List-variable pattern on 'name' in example[1] -> "sub2" matches subnets[1]
    lv = tr.get_list_variable_reference("aws_subnet.example[1]", "name")
    assert lv == ("subnets", 1)

    # In metadata should not use get_input
    assert (
        tr.should_use_get_input(
            "aws_subnet.example[0]", "cidr_block", context="metadata"
        )
        is False
    )
    # In property yes
    assert (
        tr.should_use_get_input(
            "aws_subnet.example[0]", "cidr_block", context="property"
        )
        is True
    )


def test_property_resolver_returns_get_input_or_concrete(parsed_data):
    tr = VariableReferenceTracker(parsed_data)
    pr = PropertyResolver(tr)

    # Regular var
    v = pr.resolve_property_value(
        "aws_instance.web", "instance_type", context="property"
    )
    assert v == {"$get_input": "instance_type"}

    # Map var -> key 'public'
    v2 = pr.resolve_property_value(
        "aws_subnet.example[0]", "cidr_block", context="property"
    )
    assert v2 == {"$get_input": ["cidr_map", "public"]}

    # List var -> index 1
    v3 = pr.resolve_property_value("aws_subnet.example[1]", "name", context="property")
    assert v3 == {"$get_input": ["subnets", 1]}

    # In metadata returns concrete value
    v4 = pr.resolve_property_value(
        "aws_subnet.example[0]", "cidr_block", context="metadata"
    )
    assert v4 == "10.0.1.0/24"


# ---------------------------------------------------------------------------
# VariableContext end-to-end integration
# ---------------------------------------------------------------------------


def test_variable_context_end_to_end(parsed_data):
    ctx = VariableContext(parsed_data)

    assert ctx.has_variables() is True
    assert ctx.has_outputs() is True

    # Extracted and mapped inputs
    inputs = ctx.get_tosca_inputs()
    assert "instance_type" in inputs and isinstance(
        inputs["instance_type"], ToscaInputDefinition
    )

    # Property resolution
    resolved = ctx.resolve_property(
        "aws_instance.web", "instance_type", context="property"
    )
    assert resolved == {"$get_input": "instance_type"}

    # Concrete value (ignores get_input)
    concrete = ctx.get_concrete_value("aws_instance.web", "instance_type")
    assert concrete == "t3.micro"

    # TOSCA outputs with get_attribute mapping for web_public_ip
    tosca_nodes = {"aws_instance.web": "compute_web"}
    mapped_outs = ctx.get_tosca_outputs(tosca_nodes)
    assert "web_public_ip" in mapped_outs
    val = mapped_outs["web_public_ip"].value
    assert isinstance(val, dict) and val["$get_attribute"] == [
        "compute_web",
        "public_address",
    ]

    # Sensitive output should have been discarded in convert_to_tosca_outputs
    assert "sensitive_secret_out" not in mapped_outs

    # L’output costante rimane letterale
    assert mapped_outs["just_region"].value == "eu-west-1"
