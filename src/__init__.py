"""
Jira Assets Manager

A comprehensive tool for managing Jira Assets by automating the process
of extracting user email attributes and updating assignee fields.
"""

__version__ = "1.0.0"
__author__ = "Assistant"
__email__ = "assistant@example.com"

from .asset_manager import AssetManager, AssetUpdateError, ValidationError
from .config import ConfigurationError, config, setup_logging
from .jira_assets_client import AssetNotFoundError, JiraAssetsAPIError, JiraAssetsClient
from .jira_user_client import JiraUserAPIError, JiraUserClient, UserNotFoundError

__all__ = [
    'AssetManager',
    'AssetUpdateError', 
    'ValidationError',
    'JiraAssetsClient',
    'JiraAssetsAPIError',
    'AssetNotFoundError', 
    'JiraUserClient',
    'JiraUserAPIError',
    'UserNotFoundError',
    'config',
    'setup_logging',
    'ConfigurationError'
]
