from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from src.plugins.terraform.orchestrator import TerraformOrchestrator


class FakeParser:
    """Minimal parser: accepts a directory with at least one .tf file."""

    def __init__(self) -> None:
        self.parsed: list[Path] = []

    def get_supported_extensions(self) -> list[str]:
        return [".tf"]

    def can_parse(self, p: Path) -> bool:
        return p.is_dir() and any(p.glob("*.tf"))

    def parse(self, p: Path) -> dict[str, Any]:
        self.parsed.append(p)
        return {
            "resources": [{"name": "web", "type": "aws_instance", "data": {"cpu": 2}}]
        }


class FakeMapper:
    """Minimal mapper: transfers resources into the builder."""

    def __init__(self) -> None:
        self.mapped: list[dict[str, Any]] = []

    def map(self, parsed: dict[str, Any], builder: FakeBuilder) -> None:
        self.mapped.append(parsed)
        for r in parsed.get("resources", []):
            builder.nodes[r["name"]] = {"type": r["type"], "data": r["data"]}


class FakeBuilder:
    """Minimal builder used in tests."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}


class TestFindSourceFiles:
    def test_valid_dir_returns_directory_only(self, tmp_path: Path) -> None:
        src = tmp_path / "proj"
        src.mkdir()
        (src / "main.tf").write_text("# tf")

        orch = TerraformOrchestrator()
        # use the orchestrator's real parser
        files = orch.find_source_files(src)

        assert files == [src]

    def test_invalid_dir_returns_empty_and_logs(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.WARNING)
        src = tmp_path / "proj"
        src.mkdir()
        (src / "readme.md").write_text("x")  # no .tf files

        orch = TerraformOrchestrator()
        files = orch.find_source_files(src)

        assert files == []
        assert any("not a valid Terraform project" in r.message for r in caplog.records)


class TestTranslateFlowWithFakes:
    def test_translate_happy_path(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        src = tmp_path / "proj"
        out = tmp_path / "out" / "tosca.yaml"
        src.mkdir()
        (src / "main.tf").write_text("# tf")

        orch = TerraformOrchestrator()

        # inject fake parser/mapper to avoid external integrations
        fp = FakeParser()
        fm = FakeMapper()
        orch._parser = fp
        orch._mapper = fm

        # avoid dependency on ToscaFileBuilder
        def fake_create_builder(self) -> FakeBuilder:  # noqa: D401
            return FakeBuilder()

        def fake_save_output(self, builder: FakeBuilder, path: Path) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("# generated\n")

        monkeypatch.setattr(
            TerraformOrchestrator,
            "create_builder",
            fake_create_builder,
            raising=True,
        )
        monkeypatch.setattr(
            TerraformOrchestrator,
            "save_output",
            fake_save_output,
            raising=True,
        )

        builder = orch.translate(src, out)

        # output produced and builder populated
        assert out.exists() and out.read_text().startswith("# generated")
        assert "web" in builder.nodes
        assert builder.nodes["web"]["type"] == "aws_instance"
        # parser was invoked on the directory
        assert fp.parsed and fp.parsed[0] == src

    def test_translate_no_supported_files_raises(self, tmp_path: Path) -> None:
        src = tmp_path / "proj"
        src.mkdir()
        (src / "note.txt").write_text("x")

        orch = TerraformOrchestrator()
        with pytest.raises(ValueError, match="No supported source files"):
            orch.translate(src, tmp_path / "out.yaml")


class TestRegistrationAndInfo:
    def test_mappers_are_registered_in_init(self) -> None:
        orch = TerraformOrchestrator()
        # TerraformMapper should derive from BaseResourceMapper
        # and provide get_registered_mappers()
        regs = orch._mapper.get_registered_mappers()
        # check presence of some main resource types
        assert "aws_instance" in regs
        assert "aws_vpc" in regs
        assert "aws_subnet" in regs
        assert "aws_security_group" in regs
        assert "aws_s3_bucket" in regs
        assert "aws_ebs_volume" in regs
        assert "aws_db_instance" in regs

    def test_get_orchestrator_info_uses_current_components(self) -> None:
        orch = TerraformOrchestrator()
        # replace with fakes to make output predictable
        orch._parser = FakeParser()
        orch._mapper = FakeMapper()

        info = orch.get_orchestrator_info()
        assert info["class_name"] == "TerraformOrchestrator"
        assert info["parser"]["class_name"] == "FakeParser"
        assert ".tf" in info["parser"]["supported_extensions"]
        assert info["mapper"]["class_name"] == "FakeMapper"
