"""Tests for the forthcoming `--new` interactive asset workflow."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.main import main as cli_main
from src.main import setup_argument_parser


def test_parser_includes_new_option() -> None:
    """Parser should recognize the `--new` flag."""

    parser = setup_argument_parser()
    args = parser.parse_args(["--new"])
    assert getattr(args, "new", False) is True


@pytest.mark.parametrize(
    "serial,model,status,remote_input,expected_remote",
    [
        ("SN123", "Laptop Model A", "In Use", "y", True),
        ("SN124", "Laptop Model B", "Storage", "n", False),
    ],
)
def test_cli_new_adds_single_asset(monkeypatch, serial, model, status, remote_input, expected_remote) -> None:
    """Interactive flow should create a single asset from user input."""

    mock_manager = MagicMock()
    mock_manager.list_models.return_value = ["Laptop Model A", "Laptop Model B"]
    mock_manager.list_statuses.return_value = ["In Use", "Storage"]

    monkeypatch.setattr("src.main.AssetManager", lambda: mock_manager)

    user_inputs = iter([serial, model, status, remote_input, "n"])
    monkeypatch.setattr("builtins.input", lambda *args: next(user_inputs))

    monkeypatch.setattr(sys, "argv", ["main.py", "--new"])
    exit_code = cli_main()

    mock_manager.list_models.assert_called_once()
    mock_manager.list_statuses.assert_called_once()
    mock_manager.create_asset.assert_called_once_with(
        serial=serial,
        model_name=model,
        status=status,
        is_remote=expected_remote,
    )
    assert exit_code == 0
