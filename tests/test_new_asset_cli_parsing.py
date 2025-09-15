"""Tests for the new asset CLI argument parsing and command structure."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.main import setup_argument_parser


def test_parser_includes_new_option():
    """Parser should recognize the `--new` flag."""
    parser = setup_argument_parser()
    args = parser.parse_args(["--new"])
    assert getattr(args, "new", False) is True


def test_parser_new_option_mutually_exclusive():
    """The --new option should be mutually exclusive with other operation modes."""
    parser = setup_argument_parser()
    
    # Should not be able to combine --new with --bulk
    with pytest.raises(SystemExit):
        parser.parse_args(["--new", "--bulk"])
    
    # Should not be able to combine --new with --test-asset
    with pytest.raises(SystemExit):
        parser.parse_args(["--new", "--test-asset", "HW-123"])
    
    # Should not be able to combine --new with --retire-assets
    with pytest.raises(SystemExit):
        parser.parse_args(["--new", "--retire-assets"])


def test_parser_new_option_with_valid_flags():
    """The --new option should work with compatible flags."""
    parser = setup_argument_parser()
    
    # Should work with --verbose
    args = parser.parse_args(["--new", "--verbose"])
    assert getattr(args, "new", False) is True
    assert getattr(args, "verbose", False) is True
    
    # Should work with --quiet
    args = parser.parse_args(["--new", "--quiet"])
    assert getattr(args, "new", False) is True
    assert getattr(args, "quiet", False) is True
    
    # Should work with --clear-cache
    args = parser.parse_args(["--new", "--clear-cache"])
    assert getattr(args, "new", False) is True
    assert getattr(args, "clear_cache", False) is True


@pytest.mark.parametrize("invalid_combo", [
    ["--new", "--bulk"],
    ["--new", "--test-asset", "HW-123"], 
    ["--new", "--retire-assets"],
    ["--new", "--oauth-setup"],
    ["--new", "--csv-migrate"],
])
def test_parser_new_option_exclusive_combinations(invalid_combo):
    """Test that --new is mutually exclusive with other main operations."""
    parser = setup_argument_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(invalid_combo)


def test_help_text_includes_new_option():
    """Help text should mention the --new option."""
    parser = setup_argument_parser()
    help_text = parser.format_help()
    assert "--new" in help_text
    assert "interactive" in help_text.lower() or "new asset" in help_text.lower()