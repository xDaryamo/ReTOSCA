"""Unit tests for BaseOrchestrator abstract class."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from src.core.common.base_orchestrator import BaseOrchestrator

# -------------------- Fakes / helpers --------------------


class FakeParser:
    """Minimal SourceFileParser fake with multi-part ext support."""

    def __init__(self, exts: list[str] | None = None):
        self._exts = exts or [".tf", ".tf.json"]
        self.parsed: list[Path] = []

    def get_supported_extensions(self) -> list[str]:
        return self._exts

    def can_parse(self, file_path: Path) -> bool:
        name = file_path.name
        return any(name.endswith(ext) for ext in self._exts)

    def parse(self, file_path: Path) -> dict[str, Any]:
        self.parsed.append(file_path)
        # return a predictable structure for mapper
        return {
            "resources": [{"name": "web", "type": "aws_instance", "data": {"cpu": 2}}]
        }


class BoomParser(FakeParser):
    def parse(self, file_path: Path) -> dict[str, Any]:
        raise RuntimeError("parse boom")


class FakeMapper:
    """Minimal ResourceMapper fake."""

    def __init__(self):
        self.mapped_payloads: list[dict[str, Any]] = []

    def map(self, parsed_data: dict[str, Any], builder: FakeBuilder) -> None:
        self.mapped_payloads.append(parsed_data)
        # simulate writing into builder
        for r in parsed_data.get("resources", []):
            builder.nodes[r["name"]] = {"type": r["type"], "data": r["data"]}

    # present for Protocol completeness if used elsewhere
    def register_mapper(
        self, resource_type: str, mapper: Any
    ) -> None:  # pragma: no cover
        pass

    def get_registered_mappers(self) -> dict[str, Any]:  # pragma: no cover
        return {}


class FakeBuilder:
    """Very small builder used by the orchestrator in tests."""

    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}


class SimpleOrchestrator(BaseOrchestrator):
    """Concrete orchestrator for tests."""

    def __init__(self, parser: FakeParser, mapper: FakeMapper):
        super().__init__()
        self._parser = parser
        self._mapper = mapper

    def get_parser(self):
        return self._parser

    def get_mapper(self):
        return self._mapper

    def create_builder(self) -> FakeBuilder:
        return FakeBuilder()

    def save_output(self, builder: FakeBuilder, output_file: Path) -> None:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text("# generated\n")


# --------------------------- Tests ---------------------------


class TestFindSourceFiles:
    def test_directory_search_with_multi_part_ext(self, tmp_path: Path) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.tf").write_text("# tf")
        (src / "vars.tf.json").write_text("{}")
        (src / "readme.md").write_text("nope")

        orch = SimpleOrchestrator(FakeParser(), FakeMapper())
        files = orch.find_source_files(src)
        names = sorted(p.name for p in files)
        assert names == ["main.tf", "vars.tf.json"]

    def test_single_file_input(self, tmp_path: Path) -> None:
        f = tmp_path / "one.tf"
        f.write_text("# tf")
        orch = SimpleOrchestrator(FakeParser(), FakeMapper())
        files = orch.find_source_files(f)
        assert files == [f]

    def test_missing_path_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope"
        orch = SimpleOrchestrator(FakeParser(), FakeMapper())
        with pytest.raises(ValueError, match="does not exist"):
            orch.find_source_files(missing)


class TestTranslateFlow:
    def test_translate_happy_path(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO)
        src = tmp_path / "iac"
        out = tmp_path / "out" / "tosca.yaml"
        src.mkdir()
        (src / "main.tf").write_text("# tf")

        parser = FakeParser()
        mapper = FakeMapper()
        orch = SimpleOrchestrator(parser, mapper)

        builder = orch.translate(src, out)

        # output saved
        assert out.exists() and out.read_text().startswith("# generated")
        # parser called on the file and mapper invoked
        assert parser.parsed and parser.parsed[0].name == "main.tf"
        assert "web" in builder.nodes
        assert builder.nodes["web"]["type"] == "aws_instance"
        # logs
        assert any("Starting translation" in r.message for r in caplog.records)
        assert any(
            "Translation completed successfully" in r.message for r in caplog.records
        )

    def test_translate_no_supported_files_raises(self, tmp_path: Path) -> None:
        src = tmp_path / "iac"
        src.mkdir()
        (src / "readme.txt").write_text("x")  # unsupported
        orch = SimpleOrchestrator(FakeParser(), FakeMapper())
        with pytest.raises(ValueError, match="No supported source files"):
            orch.translate(src, tmp_path / "out.yaml")

    def test_translate_bubbles_parser_error(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.ERROR)
        src = tmp_path / "iac"
        src.mkdir()
        (src / "main.tf").write_text("# tf")
        orch = SimpleOrchestrator(BoomParser(), FakeMapper())
        with pytest.raises(RuntimeError, match="parse boom"):
            orch.translate(src, tmp_path / "out.yaml")
        assert any("Translation failed" in r.message for r in caplog.records)


class TestIntrospection:
    def test_get_orchestrator_info(self) -> None:
        parser = FakeParser()
        mapper = FakeMapper()
        orch = SimpleOrchestrator(parser, mapper)
        info = orch.get_orchestrator_info()
        assert info["class_name"] == "SimpleOrchestrator"
        assert info["parser"]["class_name"] == "FakeParser"
        assert ".tf" in info["parser"]["supported_extensions"]
        assert info["mapper"]["class_name"] == "FakeMapper"
