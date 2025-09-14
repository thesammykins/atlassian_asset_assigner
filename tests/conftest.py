import os
import sys


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

