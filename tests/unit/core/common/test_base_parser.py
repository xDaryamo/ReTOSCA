"""Unit tests for BaseSourceFileParser abstract class."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from src.core.common.base_parser import BaseSourceFileParser

# -------- Concrete fakes for testing --------


class ConcreteTestParser(BaseSourceFileParser):
    """Concrete implementation for testing BaseSourceFileParser."""

    def get_supported_extensions(self) -> list[str]:
        return [".test", ".tf.json"]

    def _parse_content(self, content: str, file_path: Path) -> dict[str, Any]:
        if content.strip() == "invalid":
            raise ValueError("Test parsing error")
        return {"content": content, "file": str(file_path)}


class EmptyExtensionsParser(BaseSourceFileParser):
    """Parser with no supported extensions (accept all files)."""

    def get_supported_extensions(self) -> list[str]:
        return []

    def _parse_content(self, content: str, file_path: Path) -> dict[str, Any]:
        return {"content": content}


# ------------------------- Tests -------------------------


class TestBaseSourceFileParser:
    @pytest.fixture
    def parser(self) -> ConcreteTestParser:
        return ConcreteTestParser()

    @pytest.fixture
    def temp_file(self, tmp_path: Path) -> Path:
        f = tmp_path / "sample.test"
        f.write_text("test content")
        return f

    # --- capabilities & can_parse ---

    def test_supported_extensions(self, parser: ConcreteTestParser) -> None:
        assert parser.get_supported_extensions() == [".test", ".tf.json"]

    def test_can_parse_valid_extension(
        self, parser: ConcreteTestParser, temp_file: Path
    ) -> None:
        assert parser.can_parse(temp_file) is True

    def test_can_parse_invalid_extension(
        self, parser: ConcreteTestParser, tmp_path: Path
    ) -> None:
        f = tmp_path / "x.invalid"
        f.write_text("content")
        assert parser.can_parse(f) is False

    def test_can_parse_multi_part_extension(
        self, parser: ConcreteTestParser, tmp_path: Path
    ) -> None:
        f = tmp_path / "main.tf.json"
        f.write_text("content")
        assert parser.can_parse(f) is True

    def test_can_parse_nonexistent_file(
        self, parser: ConcreteTestParser, tmp_path: Path
    ) -> None:
        assert parser.can_parse(tmp_path / "missing.test") is False

    def test_can_parse_returns_false_on_exception(
        self,
        parser: ConcreteTestParser,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        # Force an internal exception: can_parse must return False
        monkeypatch.setattr(
            parser,
            "get_supported_extensions",
            lambda: 1 / 0,  # type: ignore
        )
        f = tmp_path / "a.test"
        f.write_text("x")
        assert parser.can_parse(f) is False

    # --- validate_file ---

    def test_validate_file_success(
        self, parser: ConcreteTestParser, temp_file: Path
    ) -> None:
        parser.validate_file(temp_file)  # should not raise

    def test_validate_file_multi_part_extension_ok(
        self, parser: ConcreteTestParser, tmp_path: Path
    ) -> None:
        f = tmp_path / "main.tf.json"
        f.write_text("x")
        parser.validate_file(f)  # should not raise after patch

    def test_validate_file_not_found(
        self, parser: ConcreteTestParser, tmp_path: Path
    ) -> None:
        with pytest.raises(FileNotFoundError):
            parser.validate_file(tmp_path / "missing.test")

    def test_validate_file_directory(
        self, parser: ConcreteTestParser, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError, match="Path is not a file"):
            parser.validate_file(tmp_path)

    def test_validate_file_unsupported_extension(
        self, parser: ConcreteTestParser, tmp_path: Path
    ) -> None:
        f = tmp_path / "x.invalid"
        f.write_text("x")
        with pytest.raises(ValueError, match="Unsupported file extension"):
            parser.validate_file(f)

    # --- I/O & parse workflow ---

    def test_read_file_success(
        self, parser: ConcreteTestParser, temp_file: Path
    ) -> None:
        assert parser._read_file(temp_file) == "test content"

    def test_read_file_encoding_error(
        self, parser: ConcreteTestParser, tmp_path: Path
    ) -> None:
        f = tmp_path / "bad.test"
        f.write_bytes(b"\x80\x81\x82")
        with pytest.raises(UnicodeDecodeError):
            parser._read_file(f)

    def test_parse_success(
        self,
        parser: ConcreteTestParser,
        temp_file: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level(logging.INFO)
        result = parser.parse(temp_file)
        assert result == {"content": "test content", "file": str(temp_file)}
        assert any("Parsing file:" in r.message for r in caplog.records)

    def test_parse_with_parsing_error(
        self,
        parser: ConcreteTestParser,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.set_level(logging.ERROR)
        f = tmp_path / "error.test"
        f.write_text("invalid")
        with pytest.raises(ValueError, match="Test parsing error"):
            parser.parse(f)
        assert any("Failed to parse" in r.message for r in caplog.records)

    # --- error handling & info ---

    def test_handle_parse_error_default_behavior(
        self, parser: ConcreteTestParser, tmp_path: Path
    ) -> None:
        f = tmp_path / "x.test"
        f.write_text("x")
        with pytest.raises(ValueError, match="boom"):
            parser._handle_parse_error(ValueError("boom"), f)

    def test_get_parser_info(self, parser: ConcreteTestParser) -> None:
        info = parser.get_parser_info()
        assert info["class_name"] == "ConcreteTestParser"
        # module ending is robust to project structure
        assert info["module"].endswith("base_parser")
        assert info["supported_extensions"] == [".test", ".tf.json"]
        assert info["encoding"] == "utf-8"

    def test_custom_encoding(self, tmp_path: Path) -> None:
        p = ConcreteTestParser(encoding="latin-1")
        assert p.encoding == "latin-1"
        assert p.get_parser_info()["encoding"] == "latin-1"


class TestEmptyExtensionsParser:
    def test_can_parse_any_file_when_no_extensions(self, tmp_path: Path) -> None:
        p = EmptyExtensionsParser()
        f = tmp_path / "any.xyz"
        f.write_text("x")
        assert p.can_parse(f) is True

    def test_validate_file_with_no_extensions(self, tmp_path: Path) -> None:
        p = EmptyExtensionsParser()
        f = tmp_path / "any.xyz"
        f.write_text("x")
        p.validate_file(f)  # should not raise
