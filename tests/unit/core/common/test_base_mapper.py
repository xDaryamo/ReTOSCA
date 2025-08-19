"""Unit tests for BaseResourceMapper abstract class."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from src.core.common.base_mapper import BaseResourceMapper

# -------------------- Fakes / helpers --------------------


class FakeBuilder:
    """Minimal builder that collects mapped nodes."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}


class FakeSingleResourceMapper:
    """Configurable SingleResourceMapper fake."""

    def __init__(self, can_map_result: bool = True, raise_on_map: bool = False):
        self.can_map_result = can_map_result
        self.raise_on_map = raise_on_map
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def can_map(self, resource_type: str, resource_data: dict[str, Any]) -> bool:
        return self.can_map_result

    def map_resource(
        self,
        resource_name: str,
        resource_type: str,
        resource_data: dict[str, Any],
        builder: FakeBuilder,
    ) -> None:
        if self.raise_on_map:
            raise ValueError("mapper boom")
        self.calls.append((resource_name, resource_type, resource_data))
        builder.nodes[resource_name] = {
            "type": resource_type,
            "data": resource_data,
        }


class ConcreteResourceMapper(BaseResourceMapper):
    """Concrete mapper that reads resources from parsed_data['resources']."""

    def _extract_resources(self, parsed_data: dict[str, Any]):
        # expected shape:
        # {"resources": [{"name":..., "type":..., "data": {...}}, ...]}
        for item in parsed_data.get("resources", []):
            yield (item["name"], item["type"], item.get("data", {}))


class RaisingExtractResourceMapper(BaseResourceMapper):
    """Mapper whose extractor raises for error-path tests."""

    def _extract_resources(self, parsed_data: dict[str, Any]):
        raise RuntimeError("extract boom")


# --------------------------- Tests ---------------------------


class TestRegistry:
    def test_register_and_get_registered_mappers(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)
        rm = ConcreteResourceMapper()
        m1 = FakeSingleResourceMapper()
        rm.register_mapper("aws_instance", m1)
        regs = rm.get_registered_mappers()
        assert regs["aws_instance"] is m1
        # log info about registration
        assert any("Registering mapper" in r.message for r in caplog.records)

    def test_register_overwrite_logs_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING)
        rm = ConcreteResourceMapper()
        rm.register_mapper("aws_instance", FakeSingleResourceMapper())
        rm.register_mapper("aws_instance", FakeSingleResourceMapper())
        assert any("Overwriting mapper" in r.message for r in caplog.records)


class TestGenerateToscaNodeName:
    def test_name_transformation_variants(self) -> None:
        f = BaseResourceMapper.generate_tosca_node_name
        assert f("aws_instance.web", "aws_instance") == "aws_instance_web"
        assert f("name-with-dash[0]", "kind") == "kind_name_with_dash_0"
        assert f("plainname", "k") == "k_plainname"


class TestMappingFlow:
    def test_map_delegates_to_registered_mapper(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)
        rm = ConcreteResourceMapper()
        m_inst = FakeSingleResourceMapper()
        m_s3 = FakeSingleResourceMapper()
        rm.register_mapper("aws_instance", m_inst)
        rm.register_mapper("aws_s3_bucket", m_s3)

        parsed = {
            "resources": [
                {"name": "web", "type": "aws_instance", "data": {"cpu": 2}},
                {"name": "assets", "type": "aws_s3_bucket", "data": {}},
            ]
        }
        b = FakeBuilder()
        rm.map(parsed, b)

        assert "web" in b.nodes and "assets" in b.nodes
        assert b.nodes["web"]["data"]["cpu"] == 2
        # start/completed logs present
        assert any(
            "Starting the resource mapping process" in r.message for r in caplog.records
        )
        assert any("completed" in r.message for r in caplog.records)

    def test_map_skips_when_no_mapper(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.WARNING)
        rm = ConcreteResourceMapper()
        # register only for instances, not for s3
        rm.register_mapper("aws_instance", FakeSingleResourceMapper())
        parsed = {
            "resources": [
                {"name": "web", "type": "aws_instance", "data": {}},
                {"name": "assets", "type": "aws_s3_bucket", "data": {}},
            ]
        }
        b = FakeBuilder()
        rm.map(parsed, b)
        assert "web" in b.nodes and "assets" not in b.nodes
        assert any("No mapper registered" in r.message for r in caplog.records)

    def test_map_skips_when_can_map_false(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING)
        rm = ConcreteResourceMapper()
        # mapper refuses this config
        rm.register_mapper(
            "aws_instance", FakeSingleResourceMapper(can_map_result=False)
        )
        parsed = {
            "resources": [{"name": "web", "type": "aws_instance", "data": {"cpu": -1}}]
        }
        b = FakeBuilder()
        rm.map(parsed, b)
        assert b.nodes == {}
        assert any(
            "cannot handle the specific configuration" in r.message
            for r in caplog.records
        )

    def test_exception_bubbles_when_extract_raises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.ERROR)
        rm = RaisingExtractResourceMapper()
        b = FakeBuilder()
        with pytest.raises(RuntimeError, match="extract boom"):
            rm.map({"resources": []}, b)
        assert any(
            "Critical failure during mapping" in r.message for r in caplog.records
        )

    def test_exception_bubbles_when_strategy_raises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.ERROR)
        rm = ConcreteResourceMapper()
        # mapper raises during map_resource
        rm.register_mapper("aws_instance", FakeSingleResourceMapper(raise_on_map=True))
        parsed = {
            "resources": [{"name": "web", "type": "aws_instance", "data": {"cpu": 2}}]
        }
        b = FakeBuilder()
        with pytest.raises(ValueError, match="mapper boom"):
            rm.map(parsed, b)
        assert any(
            "Critical failure during mapping" in r.message for r in caplog.records
        )
