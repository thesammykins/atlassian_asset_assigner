import os
import sys
from pathlib import Path

import pytest


def pytest_sessionstart(session):
    # Ensure src is importable for tests
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    src_path = os.path.join(repo_root, "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    # Minimal, safe environment so config loads without secrets
    os.environ.setdefault("JIRA_DOMAIN", "example.atlassian.net")
    os.environ.setdefault("ASSETS_WORKSPACE_ID", "1")
    os.environ.setdefault("AUTH_METHOD", "basic")
    os.environ.setdefault("JIRA_USER_EMAIL", "ci@example.com")
    os.environ.setdefault("JIRA_API_TOKEN", "token_ci_123")
    os.environ.setdefault("LOG_LEVEL", "INFO")
    # Keep default LOG_TO_FILE (true); tests avoid writing sensitive data


@pytest.fixture(autouse=True)
def clear_cache_before_each_test():
    """Clear cache files before each test to ensure clean state."""
    # Clear any existing cache files with test workspace ID
    cache_dir = Path("cache")
    if cache_dir.exists():
        # Remove cache files for test workspace ID "1"
        for cache_file in cache_dir.glob("*_1.json"):
            try:
                cache_file.unlink()
            except OSError:
                pass  # Ignore errors if file doesn't exist
    
    yield
    
    # Clean up after test as well
    if cache_dir.exists():
        for cache_file in cache_dir.glob("*_1.json"):
            try:
                cache_file.unlink()
            except OSError:
                pass

