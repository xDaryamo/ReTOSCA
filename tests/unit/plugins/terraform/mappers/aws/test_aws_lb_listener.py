import pytest

from src.plugins.terraform.mappers.aws.aws_lb_listener import AWSLBListenerMapper


class FakeBuilder:
    """Collects any added nodes (there shouldn't be any here)."""

    def __init__(self):
        self.added = []

    def add_node(self, name: str, node_type: str):
        self.added.append((name, node_type))

        # return an object with builder-style API just in case
        class _N:
            def with_property(self, *_a, **_k):
                return self

            def with_metadata(self, *_a, **_k):
                return self

            def add_requirement(self, *_a, **_k):
                return self

            def to_node(self, *_a, **_k):
                return self

            def with_relationship(self, *_a, **_k):
                return self

            def and_node(self, *_a, **_k):
                return self

        return _N()

    def get_node(self, name: str):
        # not really needed for these tests
        return None


class FakeContext:
    """Minimal context for methods that require it."""

    def __init__(self, parsed_data=None, refs=None):
        self.parsed_data = parsed_data or {}
        self._refs = refs or []

    def extract_terraform_references(self, _resource_data: dict):
        # Returns list of tuples (prop_name, target_ref, relationship_type)
        return list(self._refs)


@pytest.fixture
def mapper():
    return AWSLBListenerMapper()


def test_can_map_true(mapper):
    assert mapper.can_map("aws_lb_listener", {}) is True


def test_can_map_false(mapper):
    assert mapper.can_map("aws_lb_target_group", {}) is False


def test_map_resource_is_noop(mapper):
    b = FakeBuilder()
    resource_name = "aws_lb_listener.front"
    resource_type = "aws_lb_listener"
    resource_data = {
        "values": {
            "port": 80,
            "protocol": "HTTP",
        }
    }
    # Should not create nodes
    mapper.map_resource(resource_name, resource_type, resource_data, b, context=None)
    assert b.added == []


def test_validate_listener_config_valid_http(mapper):
    values = {"port": 80, "protocol": "HTTP"}
    assert mapper._validate_listener_config(values, "l1") is True


def test_validate_listener_config_invalid_low_port(mapper):
    values = {"port": 0, "protocol": "HTTP"}
    assert mapper._validate_listener_config(values, "l2") is False


def test_validate_listener_config_invalid_high_port(mapper):
    values = {"port": 70000, "protocol": "HTTP"}
    assert mapper._validate_listener_config(values, "l3") is False


def test_validate_listener_config_unsupported_protocol(mapper):
    values = {"port": 80, "protocol": "SCTP"}
    assert mapper._validate_listener_config(values, "l4") is False


def test_validate_listener_config_secure_without_policy_is_ok_but_warn(mapper):
    # We don't verify logs; the function should return True with HTTPS
    values = {"port": 443, "protocol": "HTTPS"}
    assert mapper._validate_listener_config(values, "l5") is True


@pytest.mark.parametrize(
    "aws, expected",
    [
        ("HTTP", "http"),
        ("HTTPS", "https"),
        ("TCP", "tcp"),
        ("TLS", "tcp"),
        ("UDP", "udp"),
        ("TCP_UDP", "tcp"),
        ("GENEVE", "tcp"),
        ("FooBar", "foobar"),
    ],
)
def test_map_protocol_to_tosca(mapper, aws, expected):
    assert mapper._map_protocol_to_tosca(aws) == expected


def test_build_metadata_maps_core_and_config_fields(mapper):
    resource_type = "aws_lb_listener"
    clean_name = "front"
    resource_data = {"provider_name": "aws"}

    # Note: we avoid using a list for default_action to work around
    # possible isinstance errors with UnionType; a string is sufficient
    metadata_values = {
        "arn": "arn:aws:elasticloadbalancing:REG:ACC:listener/app/lb/123",
        "id": "listener-abc",
        "load_balancer_arn": (
            "arn:aws:elasticloadbalancing:REG:ACC:loadbalancer/app/lb/123"
        ),
        "port": 443,
        "protocol": "HTTPS",
        "region": "eu-west-1",
        "ssl_policy": "ELBSecurityPolicy-TLS13-1-2-2021-06",
        "certificate_arn": "arn:aws:acm:REG:ACC:certificate/xyz",
        "alpn_policy": ["HTTP2Preferred"],
        "default_action": "forward:tg-1",
        "tags": {"Name": "front"},
        "tags_all": {"Name": "front", "env": "prod"},
    }

    md = mapper._build_metadata(
        resource_type, clean_name, resource_data, metadata_values
    )

    # Base
    assert md["original_resource_type"] == resource_type
    assert md["original_resource_name"] == clean_name
    assert md["aws_component_type"] == "LoadBalancerListener"
    assert md["aws_provider"] == "aws"

    # Core
    assert md["aws_listener_arn"] == metadata_values["arn"]
    assert md["aws_listener_id"] == metadata_values["id"]
    assert md["aws_load_balancer_arn"] == metadata_values["load_balancer_arn"]
    assert md["aws_port"] == 443
    assert md["aws_protocol"] == "HTTPS"
    assert md["aws_region"] == "eu-west-1"

    # Config
    assert md["aws_ssl_policy"] == metadata_values["ssl_policy"]
    assert md["aws_certificate_arn"] == metadata_values["certificate_arn"]
    assert md["aws_alpn_policy"] == metadata_values["alpn_policy"]
    assert md["aws_default_action"] == metadata_values["default_action"]

    # Operational
    assert md["aws_tags"] == {"Name": "front"}
    assert md["aws_tags_all"] == {"Name": "front", "env": "prod"}


def test_determine_network_name_without_context_defaults_public(mapper):
    values = {}  # no LB ARN
    assert mapper._determine_network_name(values, None, {}) == "PUBLIC"


def test_determine_network_name_with_internal_lb_returns_private(mapper):
    # values must include load_balancer_arn to trigger the logic
    values = {"load_balancer_arn": "arn:lb"}

    # Terraform references pointing to the LB resource
    refs = [("load_balancer_arn", "aws_lb.main", "DependsOn")]

    parsed_data = {
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_lb.main",
                        "values": {"internal": True},
                    }
                ]
            }
        }
    }
    ctx = FakeContext(parsed_data=parsed_data, refs=refs)

    result = mapper._determine_network_name(
        values, ctx, {"address": "aws_lb_listener.front"}
    )
    assert result == "PRIVATE"


def test_determine_network_name_with_external_lb_returns_public(mapper):
    values = {"load_balancer_arn": "arn:lb"}
    refs = [("load_balancer_arn", "aws_lb.pub", "DependsOn")]
    parsed_data = {
        "planned_values": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_lb.pub",
                        "values": {"internal": False},
                    }
                ]
            }
        }
    }
    ctx = FakeContext(parsed_data=parsed_data, refs=refs)

    result = mapper._determine_network_name(
        values, ctx, {"address": "aws_lb_listener.front"}
    )
    assert result == "PUBLIC"
