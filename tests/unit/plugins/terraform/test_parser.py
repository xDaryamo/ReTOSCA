from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from src.plugins.terraform.parser import TerraformParser


@pytest.fixture
def parser() -> TerraformParser:
    return TerraformParser()


@pytest.fixture
def tf_dir(tmp_path: Path) -> Path:
    # Create a fake terraform project dir with a .tf file
    (tmp_path / "main.tf").write_text('resource "aws_s3_bucket" "b" {}')
    return tmp_path


def test_supported_extensions(parser: TerraformParser) -> None:
    assert set(parser.get_supported_extensions()) == {".tf", ".tf.json"}


def test_can_parse_directory_with_tf_files(
    parser: TerraformParser, tf_dir: Path
) -> None:
    assert parser.can_parse(tf_dir) is True


def test_can_parse_directory_without_tf_files(
    parser: TerraformParser, tmp_path: Path
) -> None:
    assert parser.can_parse(tmp_path) is False


def test_can_parse_single_file_tf(parser: TerraformParser, tmp_path: Path) -> None:
    f = tmp_path / "vars.tf"
    f.write_text("# tf")
    assert parser.can_parse(f) is True


def test_can_parse_single_file_invalid_ext(
    parser: TerraformParser, tmp_path: Path
) -> None:
    f = tmp_path / "notes.txt"
    f.write_text("noop")
    assert parser.can_parse(f) is False


def test_validate_file_directory_ok(parser: TerraformParser, tf_dir: Path) -> None:
    # should not raise
    parser.validate_file(tf_dir)


def test_validate_file_directory_without_tf_raises(
    parser: TerraformParser, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="No Terraform files found"):
        parser.validate_file(tmp_path)


def test_validate_file_missing_path_raises(
    parser: TerraformParser, tmp_path: Path
) -> None:
    missing = tmp_path / "nope"
    with pytest.raises(FileNotFoundError):
        parser.validate_file(missing)


def test_validate_file_single_tf_ok(parser: TerraformParser, tmp_path: Path) -> None:
    f = tmp_path / "stack.tf.json"
    f.write_text("{}")
    # base class validation for files checks extension
    parser.validate_file(f)  # no exception


def test_run_command_success_with_output(parser: TerraformParser, tf_dir: Path) -> None:
    # mock subprocess.run to return a CompletedProcess with stdout
    fake_cp = subprocess.CompletedProcess(
        args=["tflocal", "show", "-json"], returncode=0, stdout='{"ok": true}'
    )
    with patch("subprocess.run", return_value=fake_cp) as run:
        cp = parser._run_command(
            ["tflocal", "show", "-json"], tf_dir, capture_output=True
        )
        run.assert_called_once()
        assert isinstance(cp, subprocess.CompletedProcess)
        assert json.loads(cp.stdout)["ok"] is True


def test_run_command_timeout_raises_valueerror(
    parser: TerraformParser, tf_dir: Path
) -> None:
    with patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="tflocal plan", timeout=1),
    ):
        with pytest.raises(
            ValueError,
            match="command timed out|Command timed out|Terraform command timed out",
        ):
            parser._run_command(["tflocal", "plan"], tf_dir, capture_output=False)


def test_run_command_calledprocesserror_is_reraised(
    parser: TerraformParser, tf_dir: Path
) -> None:
    err = subprocess.CalledProcessError(
        returncode=1, cmd="tflocal apply", stderr="boom"
    )
    with patch("subprocess.run", side_effect=err):
        with pytest.raises(subprocess.CalledProcessError):
            parser._run_command(["tflocal", "apply", "-auto-approve"], tf_dir)


def test_extract_complete_state_success(parser: TerraformParser, tf_dir: Path) -> None:
    payload = {
        "values": {
            "root_module": {"resources": [{"type": "aws_s3_bucket", "name": "b"}]}
        }
    }
    fake_cp = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(payload)
    )
    with patch.object(parser, "_run_command", return_value=fake_cp) as rc:
        state = parser._extract_complete_state(tf_dir)
        rc.assert_called_once()
        assert state["values"]["root_module"]["resources"][0]["type"] == "aws_s3_bucket"


def test_extract_complete_state_bad_json_raises(
    parser: TerraformParser, tf_dir: Path
) -> None:
    fake_cp = subprocess.CompletedProcess(args=[], returncode=0, stdout="{not json")
    with patch.object(parser, "_run_command", return_value=fake_cp):
        with pytest.raises(ValueError, match="Invalid JSON"):
            parser._extract_complete_state(tf_dir)


def test_deploy_and_extract_state_calls_sequence_and_returns(
    parser: TerraformParser, tf_dir: Path
) -> None:
    # spy calls on the internal steps
    plan_data = {"planned_values": {"root_module": {}}}
    state_data = {"values": {"root_module": {}}}

    with (
        patch.object(parser, "_run_terraform_init") as p_init,
        patch.object(parser, "_run_terraform_plan") as p_plan,
        patch.object(
            parser, "_extract_plan_json", return_value=plan_data
        ) as p_plan_json,
        patch.object(parser, "_run_terraform_apply") as p_apply,
        patch.object(
            parser, "_extract_complete_state", return_value=state_data
        ) as p_state,
    ):
        result = parser._deploy_and_extract_state(tf_dir)
        p_init.assert_called_once_with(tf_dir)
        p_plan.assert_called_once_with(tf_dir)
        p_plan_json.assert_called_once_with(tf_dir)
        p_apply.assert_called_once_with(tf_dir)
        p_state.assert_called_once_with(tf_dir)

        expected = {"plan": plan_data, "state": state_data}
        assert result == expected


def test_deploy_and_extract_state_wraps_calledprocesserror(
    parser: TerraformParser, tf_dir: Path
) -> None:
    # make one of the steps raise CalledProcessError
    with patch.object(
        parser,
        "_run_terraform_init",
        side_effect=subprocess.CalledProcessError(1, "tflocal init"),
    ):
        with pytest.raises(ValueError, match="Terraform deployment failed"):
            parser._deploy_and_extract_state(tf_dir)


def test_parse_success(parser: TerraformParser, tf_dir: Path) -> None:
    expected_data = {"plan": {}, "state": {"values": {}}}
    with patch.object(
        parser, "_deploy_and_extract_state", return_value=expected_data
    ) as dep:
        out = parser.parse(tf_dir)
        dep.assert_called_once_with(tf_dir)
        assert out == expected_data


def test_parse_failure_triggers_cleanup_and_reraises(
    parser: TerraformParser, tf_dir: Path
) -> None:
    with (
        patch.object(
            parser, "_deploy_and_extract_state", side_effect=RuntimeError("boom")
        ),
        patch.object(
            parser, "_handle_parse_error", side_effect=RuntimeError("boom")
        ) as handle_error,
    ):
        with pytest.raises(RuntimeError, match="boom"):
            parser.parse(tf_dir)
        handle_error.assert_called_once()


def test_cleanup_on_error_calls_destroy(parser: TerraformParser, tf_dir: Path) -> None:
    with patch.object(parser, "_run_command") as rc:
        parser._cleanup_on_error(tf_dir)
        rc.assert_called_once()
        args, kwargs = rc.call_args
        assert args[0] == ["tflocal", "destroy", "-auto-approve"]
        assert args[1] == tf_dir


def test_extract_plan_json_success(parser: TerraformParser, tf_dir: Path) -> None:
    plan_data = {
        "configuration": {
            "root_module": {"variables": {"bucket_name": {"default": "test-bucket"}}}
        },
        "planned_values": {"root_module": {"resources": []}},
    }
    fake_cp = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(plan_data)
    )
    with (
        patch.object(parser, "_run_command", return_value=fake_cp) as rc,
        patch("pathlib.Path.exists", return_value=True),
        patch("pathlib.Path.unlink") as unlink_mock,
    ):
        result = parser._extract_plan_json(tf_dir)
        # Should call destroy, plan with -out, and show -json
        assert rc.call_count == 3
        assert result == plan_data
        unlink_mock.assert_called_once()


def test_extract_plan_json_bad_json_raises(
    parser: TerraformParser, tf_dir: Path
) -> None:
    fake_cp = subprocess.CompletedProcess(args=[], returncode=0, stdout="{not json")
    with patch.object(parser, "_run_command", return_value=fake_cp):
        with pytest.raises(ValueError, match="Invalid JSON"):
            parser._extract_plan_json(tf_dir)


def test_create_plan_only_data_success(parser: TerraformParser) -> None:
    plan_data = {
        "planned_values": {
            "root_module": {"resources": [{"type": "aws_s3_bucket", "name": "test"}]}
        }
    }
    result = parser._create_plan_only_data(plan_data)

    expected = {
        "plan": plan_data,
        "state": {"format_version": "1.0", "values": plan_data["planned_values"]},
    }
    assert result == expected


def test_is_localstack_service_error_detects_license_error(
    parser: TerraformParser,
) -> None:
    error = subprocess.CalledProcessError(
        returncode=1,
        cmd="tflocal apply",
        stderr="Error: not included in your current license plan",
    )
    assert parser._is_localstack_service_error(error) is True


def test_is_localstack_service_error_detects_emulation_error(
    parser: TerraformParser,
) -> None:
    error = subprocess.CalledProcessError(returncode=1, cmd="tflocal apply")
    error.stdout = "has not yet been emulated by LocalStack"
    assert parser._is_localstack_service_error(error) is True


def test_is_localstack_service_error_detects_internal_failure(
    parser: TerraformParser,
) -> None:
    error = subprocess.CalledProcessError(
        returncode=1, cmd="tflocal apply", stderr="api error InternalFailure"
    )
    assert parser._is_localstack_service_error(error) is True


def test_is_localstack_service_error_returns_false_for_other_errors(
    parser: TerraformParser,
) -> None:
    error = subprocess.CalledProcessError(
        returncode=1, cmd="tflocal apply", stderr="Some other terraform error"
    )
    assert parser._is_localstack_service_error(error) is False


def test_deploy_and_extract_state_falls_back_to_plan_only_on_localstack_error(
    parser: TerraformParser, tf_dir: Path
) -> None:
    plan_data = {"planned_values": {"root_module": {}}}
    apply_error = subprocess.CalledProcessError(
        returncode=1,
        cmd="tflocal apply",
        stderr="not included in your current license plan",
    )

    with (
        patch.object(parser, "_run_terraform_init"),
        patch.object(parser, "_run_terraform_plan"),
        patch.object(parser, "_extract_plan_json", return_value=plan_data),
        patch.object(parser, "_run_terraform_apply", side_effect=apply_error),
        patch.object(
            parser, "_create_plan_only_data", return_value={"plan": plan_data}
        ) as plan_only,
    ):
        result = parser._deploy_and_extract_state(tf_dir)
        plan_only.assert_called_once_with(plan_data)
        assert result == {"plan": plan_data}


def test_handle_parse_error_calls_cleanup_and_reraises(
    parser: TerraformParser, tf_dir: Path
) -> None:
    original_error = RuntimeError("boom")
    with patch.object(parser, "_cleanup_on_error") as cleanup:
        with pytest.raises(RuntimeError, match="boom"):
            parser._handle_parse_error(original_error, tf_dir)
        cleanup.assert_called_once_with(tf_dir)
