import pytest

from src.plugins.provisioning.terraform.mappers.aws.aws_lb_target_group import (
    AWSLBTargetGroupMapper,
)


class _ReqBuilder:
    def __init__(self, node, name):
        self._node = node
        self._req = {"name": name, "target": None, "relationship": None}

    def to_node(self, target):
        self._req["target"] = target
        return self

    def with_relationship(self, rel):
        self._req["relationship"] = rel
        return self

    def and_node(self):
        self._node.requirements.append(self._req)
        return self._node


class _CapBuilder:
    def __init__(self, node, name):
        self._node = node
        self.name = name
        self.properties = {}

    def with_property(self, k, v):
        self.properties[k] = v
        return self

    # compat API
    def to_capability(self, *_a, **_k):  # not used here, kept for parity
        return self

    def and_node(self):
        self._node.capabilities[self.name] = self
        return self._node


class _Node:
    def __init__(self, builder, name, node_type):
        self._builder = builder
        self.name = name
        self.node_type = node_type
        self.properties = {}
        self.metadata = {}
        self.capabilities = {}
        self.requirements = []

    def with_property(self, k, v):
        self.properties[k] = v
        return self

    def with_metadata(self, md):
        self.metadata.update(md or {})
        return self

    def add_capability(self, name):
        cap = _CapBuilder(self, name)
        # we don't register until and_node() is called
        return cap

    def add_requirement(self, name):
        return _ReqBuilder(self, name)


class FakeBuilder:
    def __init__(self):
        self.nodes = {}

    def add_node(self, name: str, node_type: str):
        n = _Node(self, name, node_type)
        self.nodes[name] = n
        return n

    def get_node(self, name: str):
        return self.nodes.get(name)


class FakeContext:
    """Minimal context for methods that require it."""

    def __init__(self, parsed_data=None, refs=None, prop_values=None, meta_values=None):
        self.parsed_data = parsed_data or {}
        self._refs = refs or []
        self._prop_values = prop_values or {}
        self._meta_values = meta_values or {}

    def get_resolved_values(self, _resource_data: dict, which: str = "property"):
        return self._prop_values if which == "property" else self._meta_values

    def extract_terraform_references(self, _resource_data: dict):
        # Returns list of tuples (prop_name, target_ref, relationship_type)
        return list(self._refs)

    def generate_tosca_node_name_from_address(
        self, address: str, _rtype: str | None = None
    ):
        return "TOSCA_" + address.replace(".", "_")


@pytest.fixture
def mapper():
    return AWSLBTargetGroupMapper()


def test_can_map_true(mapper):
    assert mapper.can_map("aws_lb_target_group", {}) is True


def test_can_map_false(mapper):
    assert mapper.can_map("aws_lb_listener", {}) is False


def test_map_resource_creates_lb_with_client_capability_https(mapper):
    resource_name = "aws_lb_target_group.app"
    resource_type = "aws_lb_target_group"

    # Values for property and metadata (resolved via context)
    prop_values = {
        "port": 443,
        "protocol": "HTTPS",
        "load_balancing_algorithm_type": "least_outstanding_requests",
    }
    meta_values = {
        "name": "tg-app",
        "port": 443,
        "protocol": "HTTPS",
        "vpc_id": "vpc-123",
        "target_type": "ip",
        "region": "eu-west-1",
        "arn": "arn:aws:elasticloadbalancing:eu-west-1:123:targetgroup/tg/abc",
        "id": "tg-abc",
        "protocol_version": "HTTP2",
        "load_balancing_algorithm_type": "least_outstanding_requests",
        "ip_address_type": "ipv4",
        # operational (only scalars to avoid isinstance(list|dict) at runtime)
        "connection_termination": True,
        "deregistration_delay": 60,
        "lambda_multi_value_headers_enabled": False,
        "preserve_client_ip": True,
        "proxy_protocol_v2": False,
        "slow_start": 30,
        "tags": {"Name": "tg-app"},
        "tags_all": {"Name": "tg-app", "env": "prod"},
    }

    # refs: one to an application target (application/RoutesTo),
    # one generic (dependency)
    refs = [
        ("target_id", "AppServerNode", "DependsOn"),
        ("vpc_id", "VpcNode", "DependsOn"),
    ]

    ctx = FakeContext(
        parsed_data={}, refs=refs, prop_values=prop_values, meta_values=meta_values
    )
    b = FakeBuilder()

    mapper.map_resource(resource_name, resource_type, {"values": {}}, b, context=ctx)

    node_name = ctx.generate_tosca_node_name_from_address(resource_name, resource_type)
    n = b.get_node(node_name)
    assert n is not None
    assert n.node_type == "LoadBalancer"

    # LB properties
    assert n.properties["algorithm"] == "least_outstanding_requests"

    # client capability
    client = n.capabilities.get("client")
    assert client is not None
    assert client.properties["port"] == 443
    assert client.properties["protocol"] == "https"  # lower-case
    assert client.properties["secure"] is True

    # main metadata
    md = n.metadata
    assert md["original_resource_type"] == resource_type
    assert md["original_resource_name"] == "app"
    assert md["aws_component_type"] == "TargetGroup"
    assert md["aws_target_group_name"] == "tg-app"
    assert md["aws_port"] == 443
    assert md["aws_protocol"] == "HTTPS"
    assert md["aws_vpc_id"] == "vpc-123"
    assert md["aws_target_type"] == "ip"
    assert md["aws_region"] == "eu-west-1"
    assert md["aws_target_group_arn"].startswith("arn:")
    assert md["aws_target_group_id"] == "tg-abc"
    assert md["aws_protocol_version"] == "HTTP2"
    assert md["aws_load_balancing_algorithm_type"] == "least_outstanding_requests"
    assert md["aws_ip_address_type"] == "ipv4"
    # operational + tags
    assert md["aws_connection_termination"] is True
    assert md["aws_deregistration_delay"] == 60
    assert md["aws_preserve_client_ip"] is True
    assert md["aws_proxy_protocol_v2"] is False
    assert md["aws_slow_start"] == 30
    assert md["aws_tags"] == {"Name": "tg-app"}
    assert md["aws_tags_all"] == {"Name": "tg-app", "env": "prod"}

    # requirements: one application/RoutesTo for target_id,
    # one dependency/DependsOn for vpc_id
    expected_app_req = {
        "name": "application",
        "target": "AppServerNode",
        "relationship": "RoutesTo",
    }
    expected_dep_req = {
        "name": "dependency",
        "target": "VpcNode",
        "relationship": "DependsOn",
    }
    assert expected_app_req in n.requirements
    assert expected_dep_req in n.requirements


def test_map_resource_defaults_and_tcp_not_secure(mapper):
    resource_name = "aws_lb_target_group.tcp"
    resource_type = "aws_lb_target_group"

    prop_values = {
        # no port => should not set the 'port' property in the capability
        "protocol": "TCP",
        # no algorithm => uses default round_robin
    }
    ctx = FakeContext(prop_values=prop_values, meta_values={})
    b = FakeBuilder()

    mapper.map_resource(resource_name, resource_type, {"values": {}}, b, context=ctx)

    node_name = ctx.generate_tosca_node_name_from_address(resource_name, resource_type)
    n = b.get_node(node_name)
    assert n is not None
    assert n.properties["algorithm"] == "round_robin"

    client = n.capabilities.get("client")
    assert client is not None
    assert client.properties["protocol"] == "tcp"
    assert client.properties["secure"] is False
    assert "port" not in client.properties  # not set


def test_map_resource_invalid_port_skips_node(mapper):
    resource_name = "aws_lb_target_group.badport"
    resource_type = "aws_lb_target_group"

    prop_values = {"port": 70000, "protocol": "HTTP"}  # invalid port
    ctx = FakeContext(prop_values=prop_values, meta_values={})
    b = FakeBuilder()

    mapper.map_resource(resource_name, resource_type, {"values": {}}, b, context=ctx)

    # No node created
    assert b.nodes == {}


def test_map_resource_unsupported_protocol_skips_node(mapper):
    resource_name = "aws_lb_target_group.badproto"
    resource_type = "aws_lb_target_group"

    prop_values = {"port": 80, "protocol": "SCTP"}  # unsupported protocol
    ctx = FakeContext(prop_values=prop_values, meta_values={})
    b = FakeBuilder()

    mapper.map_resource(resource_name, resource_type, {"values": {}}, b, context=ctx)

    # No node created
    assert b.nodes == {}
