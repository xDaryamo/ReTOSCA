import pytest

from src.plugins.provisioning.terraform.exceptions import ValidationError
from src.plugins.provisioning.terraform.mappers.aws.aws_lb_target_group_attachment import (  # noqa: E501
    AWSLBTargetGroupAttachmentMapper,
    TargetGroupAttachmentError,
)


class _ReqBuilder:
    def __init__(self, node, name):
        self._node = node
        self._req = {
            "name": name,
            "target": None,
            "capability": None,
            "relationship": None,
            "rel_properties": {},
        }

    def to_node(self, target):
        self._req["target"] = target
        return self

    def to_capability(self, capability):
        self._req["capability"] = capability
        return self

    def with_relationship(self, rel):
        # can be string ("RoutesTo") or dict({"type": "...", "properties": {...}})
        self._req["relationship"] = rel
        # If dict, we also extract properties for simpler verification
        if (
            isinstance(rel, dict)
            and "properties" in rel
            and isinstance(rel["properties"], dict)
        ):
            self._req["rel_properties"].update(rel["properties"])
        return self

    def with_properties(self, **props):
        # used in the mapper's fallback branch
        self._req["rel_properties"].update(props)
        return self

    def and_node(self):
        self._node.requirements.append(self._req)
        return self._node


class _Node:
    def __init__(self, name, node_type):
        self.name = name
        self.node_type = node_type
        self.properties = {}
        self.metadata = {}
        self.capabilities = {}
        self.requirements = []

    def add_requirement(self, name):
        return _ReqBuilder(self, name)

    def add_capability(self, name):
        self.capabilities.setdefault(name, {})

        class _CapProxy:
            def __init__(self, node, capname):
                self._node = node
                self._capname = capname

            def and_node(self):
                return self._node

        return _CapProxy(self, name)

    def with_property(self, k, v):
        self.properties[k] = v
        return self

    def with_metadata(self, md):
        self.metadata.update(md or {})
        return self


class FakeBuilder:
    def __init__(self):
        self.nodes = {}

    def add_node(self, name: str, node_type: str):
        n = _Node(name, node_type)
        self.nodes[name] = n
        return n

    def get_node(self, name: str):
        return self.nodes.get(name)


class FakeContext:
    """Minimal context for methods used by the mapper."""

    def __init__(
        self,
        parsed_data=None,
        refs=None,
        prop_values=None,
        meta_values=None,
    ):
        self.parsed_data = parsed_data or {}
        self._refs = refs or []
        self._prop_values = prop_values or {}
        self._meta_values = meta_values or {}

    def get_resolved_values(self, _resource_data: dict, which: str = "property"):
        return self._prop_values if which == "property" else self._meta_values

    def extract_terraform_references(self, _resource_data: dict):
        # Returns list of tuples (prop_name, target_ref, relationship_type)
        return list(self._refs)


def make_resource(
    address="aws_lb_target_group_attachment.example",
    values=None,
    mode=None,
    change_actions=None,
):
    data = {
        "address": address,
        "values": values or {},
    }
    if mode is not None:
        data["mode"] = mode
    if change_actions is not None:
        data["change"] = {"actions": list(change_actions)}
    return data


@pytest.fixture
def mapper():
    return AWSLBTargetGroupAttachmentMapper()


def test_can_map_true(mapper):
    assert mapper.can_map("aws_lb_target_group_attachment", {}) is True


def test_can_map_false(mapper):
    assert mapper.can_map("aws_lb_target_group", {}) is False


def test_map_attachment_with_port_22_uses_admin_endpoint(mapper):
    # We use references already in "TOSCA format" (no dots) so we avoid
    # dependencies on the BaseResourceMapper
    tg_node_name = "aws_lb_target_group_tg"
    target_node_name = "aws_instance_web"

    b = FakeBuilder()
    b.add_node(tg_node_name, "LoadBalancer")
    b.add_node(target_node_name, "Compute")

    ctx = FakeContext(
        refs=[
            ("target_group_arn", tg_node_name, "DependsOn"),
            ("target_id", target_node_name, "DependsOn"),
        ],
        prop_values={"port": 22, "availability_zone": "eu-west-1a"},
        meta_values={"port": 22},
    )

    resource = make_resource(values={"port": 22, "availability_zone": "eu-west-1a"})

    mapper.map_resource(
        resource_name="aws_lb_target_group_attachment.attach",
        resource_type="aws_lb_target_group_attachment",
        resource_data=resource,
        builder=b,
        context=ctx,
    )

    reqs = b.get_node(tg_node_name).requirements
    assert len(reqs) == 1
    req = reqs[0]
    assert req["name"] == "application"
    assert req["target"] == target_node_name
    assert req["capability"] == "admin_endpoint"  # port 22 => admin_endpoint
    assert isinstance(req["relationship"], dict)
    assert req["relationship"]["type"] == "RoutesTo"
    assert req["rel_properties"].get("availability_zone") == "eu-west-1a"


def test_map_attachment_without_port_fallback_relationship(mapper):
    tg_node_name = "aws_lb_target_group_tg"
    target_node_name = "aws_instance_web"

    b = FakeBuilder()
    b.add_node(tg_node_name, "LoadBalancer")
    b.add_node(target_node_name, "Compute")

    ctx = FakeContext(
        refs=[
            ("target_group_arn", tg_node_name, "DependsOn"),
            ("target_id", target_node_name, "DependsOn"),
        ],
        prop_values={"availability_zone": "us-east-1a"},
        meta_values={},
    )

    resource = make_resource(values={"availability_zone": "us-east-1a"})

    mapper.map_resource(
        resource_name="aws_lb_target_group_attachment.attach2",
        resource_type="aws_lb_target_group_attachment",
        resource_data=resource,
        builder=b,
        context=ctx,
    )

    reqs = b.get_node(tg_node_name).requirements
    assert len(reqs) == 1
    req = reqs[0]
    assert req["name"] == "application"
    assert req["target"] == target_node_name
    assert req["capability"] is None  # fallback path
    assert req["relationship"] == "RoutesTo"
    assert req["rel_properties"].get("availability_zone") == "us-east-1a"


def test_map_attachment_raises_without_context(mapper):
    b = FakeBuilder()
    resource = make_resource(values={"port": 80})
    with pytest.raises(TargetGroupAttachmentError):
        mapper.map_resource(
            "aws_lb_target_group_attachment.noctx",
            "aws_lb_target_group_attachment",
            resource,
            b,
            context=None,
        )


def test_map_attachment_empty_resource_raises_validation(mapper):
    b = FakeBuilder()
    with pytest.raises(ValidationError):
        mapper.map_resource(
            "aws_lb_target_group_attachment.empty",
            "aws_lb_target_group_attachment",
            {},
            b,
            context=FakeContext(),
        )


def test_map_attachment_destroy_mode_raises(mapper):
    b = FakeBuilder()
    resource = make_resource(mode="destroy")
    with pytest.raises(ValidationError):
        mapper.map_resource(
            "aws_lb_target_group_attachment.destroy",
            "aws_lb_target_group_attachment",
            resource,
            b,
            context=FakeContext(),
        )


def test_map_attachment_delete_action_raises(mapper):
    b = FakeBuilder()
    resource = make_resource(change_actions=["delete"])
    with pytest.raises(ValidationError):
        mapper.map_resource(
            "aws_lb_target_group_attachment.delete",
            "aws_lb_target_group_attachment",
            resource,
            b,
            context=FakeContext(),
        )


def test_map_attachment_invalid_port_raises(mapper):
    b = FakeBuilder()
    resource = make_resource(values={"port": 70000})  # port out of range
    with pytest.raises(ValidationError):
        mapper.map_resource(
            "aws_lb_target_group_attachment.badport",
            "aws_lb_target_group_attachment",
            resource,
            b,
            context=FakeContext(),
        )


def test_map_attachment_missing_refs_raises(mapper):
    b = FakeBuilder()
    # No nodes created and no references available
    ctx = FakeContext(refs=[], prop_values={}, meta_values={})
    resource = make_resource(values={})

    with pytest.raises(ValidationError):
        mapper.map_resource(
            "aws_lb_target_group_attachment.norefs",
            "aws_lb_target_group_attachment",
            resource,
            b,
            context=ctx,
        )


def test_map_attachment_dotted_addresses(monkeypatch, mapper):
    """
    Simulates Terraform addresses with dots, monkeypatching the name generator
    to have a deterministic result.
    """
    # monkeypatch the generator to avoid dependencies on real implementation
    from src.core.common import base_mapper as bm

    def _fake_gen(name, rtype=None):
        # simple predictable normalization
        return "TOSCA_" + name.replace(".", "_").replace("[", "_").replace("]", "")

    monkeypatch.setattr(
        bm.BaseResourceMapper, "generate_tosca_node_name", staticmethod(_fake_gen)
    )

    tg_tf_addr = "aws_lb_target_group.tg"
    target_tf_addr = "aws_instance.web"
    tg_node_name = _fake_gen(tg_tf_addr)
    target_node_name = _fake_gen(target_tf_addr)

    b = FakeBuilder()
    b.add_node(tg_node_name, "LoadBalancer")
    b.add_node(target_node_name, "Compute")

    ctx = FakeContext(
        refs=[
            ("target_group_arn", tg_tf_addr, "DependsOn"),
            ("target_id", target_tf_addr, "DependsOn"),
        ],
        prop_values={"port": 8080},
        meta_values={"port": 8080},
    )

    resource = make_resource(values={"port": 8080})

    mapper.map_resource(
        "aws_lb_target_group_attachment.dotrefs",
        "aws_lb_target_group_attachment",
        resource,
        b,
        context=ctx,
    )

    reqs = b.get_node(tg_node_name).requirements
    assert len(reqs) == 1
    req = reqs[0]
    assert req["name"] == "application"
    assert req["target"] == target_node_name
    assert req["capability"] == "endpoint"  # port != 22 => endpoint
    assert req["relationship"]["type"] == "RoutesTo"


def test_map_attachment_plan_mode_extracts_from_configuration(monkeypatch, mapper):
    from src.core.common import base_mapper as bm

    def _fake_gen(name, rtype=None):
        return "TOSCA_" + name.replace(".", "_").replace("[", "_").replace("]", "")

    monkeypatch.setattr(
        bm.BaseResourceMapper, "generate_tosca_node_name", staticmethod(_fake_gen)
    )

    # parsed_data with configuration section containing expressions
    parsed_data = {
        "configuration": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_lb_target_group_attachment.fromplan",
                        "expressions": {
                            "target_group_arn": {
                                "references": ["aws_lb_target_group.app.arn"]
                            },
                            "target_id": {"references": ["aws_instance.web.id"]},
                        },
                    }
                ]
            }
        }
    }

    tg_tf_addr = "aws_lb_target_group.app"
    target_tf_addr = "aws_instance.web"
    tg_node_name = _fake_gen(tg_tf_addr)
    target_node_name = _fake_gen(target_tf_addr)

    b = FakeBuilder()
    b.add_node(tg_node_name, "LoadBalancer")
    b.add_node(target_node_name, "Compute")

    ctx = FakeContext(
        parsed_data=parsed_data,
        refs=[],  # no explicit refs: force extraction from configuration
        prop_values={"port": 80},
        meta_values={"port": 80},
    )

    resource = make_resource(
        address="aws_lb_target_group_attachment.fromplan",
        values={"port": 80},
    )

    mapper.map_resource(
        "aws_lb_target_group_attachment.fromplan",
        "aws_lb_target_group_attachment",
        resource,
        b,
        context=ctx,
    )

    reqs = b.get_node(tg_node_name).requirements
    assert len(reqs) == 1
    req = reqs[0]
    assert req["target"] == target_node_name
    assert req["capability"] == "endpoint"
    assert req["relationship"]["type"] == "RoutesTo"


def test_map_attachment_lambda_target(monkeypatch, mapper):
    from src.core.common import base_mapper as bm

    def _fake_gen(name, rtype=None):
        return "TOSCA_" + name.replace(".", "_")

    monkeypatch.setattr(
        bm.BaseResourceMapper, "generate_tosca_node_name", staticmethod(_fake_gen)
    )

    tg_tf_addr = "aws_lb_target_group.chain"
    lambda_tf_addr = "aws_lambda_function.fn"

    tg_node_name = _fake_gen(tg_tf_addr)
    lambda_node_name = _fake_gen(lambda_tf_addr)

    b = FakeBuilder()
    b.add_node(tg_node_name, "LoadBalancer")
    b.add_node(lambda_node_name, "Function")

    ctx = FakeContext(
        refs=[
            ("target_group_arn", tg_tf_addr, "DependsOn"),
            ("target_id", lambda_tf_addr, "DependsOn"),
        ],
        prop_values={"target_id": "lambda"},  # no port => fallback
        meta_values={},
    )

    resource = make_resource(values={"target_id": "lambda"})

    mapper.map_resource(
        "aws_lb_target_group_attachment.lambda",
        "aws_lb_target_group_attachment",
        resource,
        b,
        context=ctx,
    )

    reqs = b.get_node(tg_node_name).requirements
    assert len(reqs) == 1
    req = reqs[0]
    assert req["target"] == lambda_node_name
    assert req["capability"] is None
    assert req["relationship"] == "RoutesTo"
