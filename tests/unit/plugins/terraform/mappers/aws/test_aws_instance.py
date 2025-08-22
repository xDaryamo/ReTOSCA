from __future__ import annotations

import logging
from typing import Any

import pytest

from src.plugins.terraform.mappers.aws.aws_instance import AWSInstanceMapper


class FakeCap:
    def __init__(self, node: FakeNode) -> None:
        self.node = node
        self.name: str | None = None
        self.props: dict[str, Any] = {}

    def with_property(self, k: str, v: Any) -> FakeCap:
        self.props[k] = v
        return self

    def and_node(self) -> FakeNode:
        return self.node


class FakeNode:
    def __init__(self) -> None:
        self.node_type: str | None = None
        self.props: dict[str, Any] = {}
        self.meta: dict[str, Any] = {}
        self.caps: dict[str, FakeCap] = {}

    def with_property(self, k: str, v: Any) -> FakeNode:
        self.props[k] = v
        return self

    def with_metadata(self, m: dict[str, Any]) -> FakeNode:
        self.meta.update(m)
        return self

    def add_capability(self, name: str) -> FakeCap:
        cap = FakeCap(self)
        self.caps[name] = cap
        return cap


class FakeBuilder:
    def __init__(self) -> None:
        self.created: list[tuple[str, str]] = []
        self.nodes: list[FakeNode] = []

    def add_node(self, name: str, node_type: str) -> FakeNode:
        self.created.append((name, node_type))
        n = FakeNode()
        n.node_type = node_type
        self.nodes.append(n)
        return n


def _mk_parsed(**vals: Any) -> dict[str, Any]:
    return {
        "values": vals,
        "provider_name": "registry.terraform.io/hashicorp/aws",
    }


class TestCanMap:
    def test_true_for_aws_instance(self) -> None:
        m = AWSInstanceMapper()
        assert m.can_map("aws_instance", {}) is True

    def test_false_for_other(self) -> None:
        m = AWSInstanceMapper()
        assert m.can_map("aws_vpc", {}) is False


class TestMap:
    def test_maps_meta_and_caps(self) -> None:
        m = AWSInstanceMapper()
        b = FakeBuilder()
        data = _mk_parsed(
            ami="ubuntu-22",
            instance_type="t3.micro",
            region="us-east-1",
        )
        m.map_resource("aws_instance.web", "aws_instance", data, b)
        assert b.created and b.created[0][1] == "Compute"
        node = b.nodes[0]
        md = node.meta
        assert md["original_resource_type"] == "aws_instance"
        assert md["original_resource_name"] == "web"
        assert md["aws_provider"]
        assert md["aws_region"] == "us-east-1"
        assert md["aws_instance_type"] == "t3.micro"
        assert md["aws_ami"] == "ubuntu-22"
        host = node.caps.get("host")
        assert host is not None
        assert host.props["num_cpus"] >= 1
        assert host.props["mem_size"] in {"1 GB", "512 MB", "2 GB", "4 GB"}
        oscap = node.caps.get("os")
        assert oscap is not None

    def test_skips_when_no_values(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING)
        m = AWSInstanceMapper()
        b = FakeBuilder()
        data = {"values": {}}
        m.map_resource("aws_instance.x", "aws_instance", data, b)
        assert b.created == []
        assert any("no 'values'" in r.getMessage() for r in caplog.records)

    def test_sets_tags_all_when_diff(self) -> None:
        m = AWSInstanceMapper()
        b = FakeBuilder()
        data = _mk_parsed(
            ami="al2023",
            instance_type="t3.micro",
            region="us-east-1",
            tags={"a": "1"},
            tags_all={"a": "1", "b": "2"},
        )
        m.map_resource("aws_instance.s", "aws_instance", data, b)
        node = b.nodes[0]
        assert node.meta.get("terraform_tags_all") == {"a": "1", "b": "2"}

    def test_os_inferred_from_ami(self) -> None:
        m = AWSInstanceMapper()
        b = FakeBuilder()
        data = _mk_parsed(
            ami="ubuntu-x",
            instance_type="t3.small",
            region="eu-west-1",
        )
        m.map_resource("aws_instance.vm", "aws_instance", data, b)
        oscap = b.nodes[0].caps.get("os")
        assert oscap is not None
        # distro set
        assert "distribution" in oscap.props or "type" in oscap.props

    def test_cpu_options_override_vcpu_count(self) -> None:
        """Test that cpu_options override the default vCPU count."""
        m = AWSInstanceMapper()
        b = FakeBuilder()
        data = _mk_parsed(
            ami="ami-12345",
            instance_type="c6a.2xlarge",  # Default: 8 vCPU
            region="us-east-2",
            cpu_options=[{"core_count": 2, "threads_per_core": 2}],
        )
        m.map_resource("aws_instance.test", "aws_instance", data, b)
        node = b.nodes[0]
        host = node.caps.get("host")
        assert host is not None
        # Should be 2 cores × 2 threads = 4 vCPU, not the default 8
        assert host.props["num_cpus"] == 4

    def test_cpu_options_disabled_hyperthreading(self) -> None:
        """Test cpu_options with hyperthreading disabled."""
        m = AWSInstanceMapper()
        b = FakeBuilder()
        data = _mk_parsed(
            ami="ami-12345",
            instance_type="c6a.4xlarge",  # Default: 16 vCPU
            region="us-east-2",
            cpu_options=[
                {"core_count": 8, "threads_per_core": 1}  # Hyperthreading disabled
            ],
        )
        m.map_resource("aws_instance.test", "aws_instance", data, b)
        node = b.nodes[0]
        host = node.caps.get("host")
        assert host is not None
        # Should be 8 cores × 1 thread = 8 vCPU, not the default 16
        assert host.props["num_cpus"] == 8

    def test_no_cpu_options_uses_default(self) -> None:
        """Test that without cpu_options, default vCPU count is used."""
        m = AWSInstanceMapper()
        b = FakeBuilder()
        data = _mk_parsed(
            ami="ami-12345",
            instance_type="t3.micro",  # Default: 2 vCPU
            region="us-east-1",
        )
        m.map_resource("aws_instance.test", "aws_instance", data, b)
        node = b.nodes[0]
        host = node.caps.get("host")
        assert host is not None
        # Should use default 2 vCPU
        assert host.props["num_cpus"] == 2

    def test_empty_cpu_options_uses_default(self) -> None:
        """Test that empty cpu_options list uses default vCPU count."""
        m = AWSInstanceMapper()
        b = FakeBuilder()
        data = _mk_parsed(
            ami="ami-12345",
            instance_type="t3.small",  # Default: 2 vCPU
            region="us-east-1",
            cpu_options=[],  # Empty list
        )
        m.map_resource("aws_instance.test", "aws_instance", data, b)
        node = b.nodes[0]
        host = node.caps.get("host")
        assert host is not None
        # Should use default 2 vCPU
        assert host.props["num_cpus"] == 2


class TestCalculateActualVcpu:
    """Test the _calculate_actual_vcpu method directly."""

    def test_no_cpu_options_returns_default(self) -> None:
        m = AWSInstanceMapper()
        result = m._calculate_actual_vcpu(8, None)
        assert result == 8

    def test_empty_cpu_options_returns_default(self) -> None:
        m = AWSInstanceMapper()
        result = m._calculate_actual_vcpu(8, [])
        assert result == 8

    def test_valid_cpu_options_calculates_correctly(self) -> None:
        m = AWSInstanceMapper()
        cpu_options = [{"core_count": 4, "threads_per_core": 2}]
        result = m._calculate_actual_vcpu(16, cpu_options)
        assert result == 8  # 4 cores × 2 threads

    def test_cpu_options_dict_instead_of_list(self) -> None:
        """Test handling cpu_options as dict instead of list."""
        m = AWSInstanceMapper()
        cpu_options = {"core_count": 2, "threads_per_core": 1}
        result = m._calculate_actual_vcpu(4, cpu_options)
        assert result == 2  # 2 cores × 1 thread

    def test_missing_core_count_returns_default(self) -> None:
        m = AWSInstanceMapper()
        cpu_options = [{"threads_per_core": 2}]  # Missing core_count
        result = m._calculate_actual_vcpu(8, cpu_options)
        assert result == 8  # Should return default

    def test_missing_threads_per_core_returns_default(self) -> None:
        m = AWSInstanceMapper()
        cpu_options = [{"core_count": 4}]  # Missing threads_per_core
        result = m._calculate_actual_vcpu(8, cpu_options)
        assert result == 8  # Should return default
