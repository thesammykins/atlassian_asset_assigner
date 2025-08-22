"""
Configuration module for Jira Assets Manager

This module handles loading and validation of environment variables
and provides secure access to application configuration.
"""

import os
import logging
from typing import Optional
from dotenv import load_dotenv


class ConfigurationError(Exception):
    """Raised when there's an issue with the configuration."""
    pass


class Config:
    """Configuration management class."""
    
    def __init__(self, env_file: Optional[str] = None):
        """
        Initialize configuration by loading environment variables.
        
        Args:
            env_file: Optional path to .env file. If None, searches in current directory.
        """
        # Load environment variables
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()
        
        self._validate_required_variables()
    
    def _validate_required_variables(self) -> None:
        """Validate that all required environment variables are set."""
        # Always required
        required_vars = [
            'JIRA_DOMAIN',
            'ASSETS_WORKSPACE_ID'
        ]
        
        # Authentication method specific requirements
        auth_method = os.getenv('AUTH_METHOD', 'basic').lower()
        
        if auth_method == 'oauth':
            # OAuth requires client credentials
            required_vars.extend([
                'OAUTH_CLIENT_ID',
                'OAUTH_CLIENT_SECRET'
            ])
        else:
            # Basic auth requires user credentials
            required_vars.extend([
                'JIRA_USER_EMAIL',
                'JIRA_API_TOKEN'
            ])
        
        missing_vars = []
        placeholder_vars = []
        
        for var in required_vars:
            value = os.getenv(var)
            if not value:
                missing_vars.append(var)
            elif value in ['YOUR_ATLASSIAN_API_TOKEN_HERE', 'your.email@company.com', 'your-client-id-here', 'your-client-secret-here']:
                placeholder_vars.append(var)
        
        if missing_vars:
            if auth_method == 'oauth':
                error_msg = (
                    f"Missing required OAuth environment variables: {', '.join(missing_vars)}\n"
                    "Please configure OAuth settings in your .env file. See README.md for OAuth setup instructions."
                )
            else:
                error_msg = (
                    f"Missing required environment variables: {', '.join(missing_vars)}\n"
                    "Please copy .env.example to .env and fill in the values."
                )
            raise ConfigurationError(error_msg)
        
        if placeholder_vars:
            raise ConfigurationError(
                f"Please update placeholder values in .env for: {', '.join(placeholder_vars)}\n"
                "These still contain example values and need to be replaced with actual credentials."
            )
    
    @property
    def jira_domain(self) -> str:
        """Get the Jira domain."""
        return os.getenv('JIRA_DOMAIN', 'your-domain.atlassian.net')
    
    @property
    def jira_base_url(self) -> str:
        """Get the full Jira base URL."""
        return f"https://{self.jira_domain}"
    
    @property
    def jira_user_email(self) -> str:
        """Get the Jira user email."""
        return os.getenv('JIRA_USER_EMAIL', '')
    
    @property
    def jira_api_token(self) -> str:
        """Get the Jira API token."""
        return os.getenv('JIRA_API_TOKEN', '')
    
    @property
    def assets_workspace_id(self) -> str:
        """Get the Assets workspace ID."""
        return os.getenv('ASSETS_WORKSPACE_ID', '')
    
    @property
    def hardware_schema_name(self) -> str:
        """Get the Hardware schema name."""
        return os.getenv('HARDWARE_SCHEMA_NAME', 'Hardware')
    
    @property
    def laptops_object_schema_name(self) -> str:
        """Get the Laptops object schema name."""
        return os.getenv('LAPTOPS_OBJECT_SCHEMA_NAME', 'Laptops')
    
    @property
    def user_email_attribute(self) -> str:
        """Get the user email attribute name."""
        return os.getenv('USER_EMAIL_ATTRIBUTE', 'User Email')
    
    @property
    def assignee_attribute(self) -> str:
        """Get the assignee attribute name."""
        return os.getenv('ASSIGNEE_ATTRIBUTE', 'Assignee')
    
    @property
    def retirement_date_attribute(self) -> str:
        """Get the retirement date attribute name."""
        return os.getenv('RETIREMENT_DATE_ATTRIBUTE', 'Retirement Date')
    
    @property
    def asset_status_attribute(self) -> str:
        """Get the asset status attribute name."""
        return os.getenv('ASSET_STATUS_ATTRIBUTE', 'Asset Status')
    
    @property
    def max_requests_per_minute(self) -> int:
        """Get the maximum requests per minute for rate limiting."""
        return int(os.getenv('MAX_REQUESTS_PER_MINUTE', '300'))
    
    @property
    def batch_size(self) -> int:
        """Get the batch size for bulk operations."""
        return int(os.getenv('BATCH_SIZE', '10'))
    
    @property
    def log_level(self) -> str:
        """Get the logging level."""
        return os.getenv('LOG_LEVEL', 'INFO').upper()
    
    @property
    def log_to_file(self) -> bool:
        """Check if logging to file is enabled."""
        return os.getenv('LOG_TO_FILE', 'true').lower() in ('true', '1', 'yes', 'on')
    
    @property
    def auth_method(self) -> str:
        """Get the authentication method (basic or oauth)."""
        return os.getenv('AUTH_METHOD', 'basic').lower()
    
    @property
    def oauth_client_id(self) -> str:
        """Get the OAuth client ID."""
        return os.getenv('OAUTH_CLIENT_ID', '')
    
    @property
    def oauth_client_secret(self) -> str:
        """Get the OAuth client secret."""
        return os.getenv('OAUTH_CLIENT_SECRET', '')
    
    @property
    def oauth_redirect_uri(self) -> str:
        """Get the OAuth redirect URI."""
        return os.getenv('OAUTH_REDIRECT_URI', 'http://localhost:8080/callback')
    
    @property
    def oauth_scopes(self) -> str:
        """Get the OAuth scopes."""
        return os.getenv('OAUTH_SCOPES', 'read:jira-user read:cmdb-object:jira read:cmdb-schema:jira write:cmdb-object:jira')
    
    def get_basic_auth(self) -> tuple[str, str]:
        """
        Get basic authentication credentials for Jira API.
        
        Returns:
            Tuple of (email, api_token)
        """
        return (self.jira_user_email, self.jira_api_token)
    
    def is_oauth_configured(self) -> bool:
        """
        Check if OAuth 2.0 is properly configured.
        
        Returns:
            True if OAuth credentials are available
        """
        return bool(self.oauth_client_id and self.oauth_client_secret)


# Global config instance
config = Config()


def setup_logging() -> logging.Logger:
    """
    Set up logging configuration based on config settings.
    
    Returns:
        Configured logger instance
    """
    # Create logs directory if it doesn't exist
    logs_dir = 'logs'
    os.makedirs(logs_dir, exist_ok=True)
    
    # Configure logging
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'
    
    # Set up formatters
    formatter = logging.Formatter(log_format, date_format)
    
    # Create logger
    logger = logging.getLogger('jira_assets_manager')
    logger.setLevel(getattr(logging, config.log_level))
    
    # Clear any existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, config.log_level))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (if enabled)
    if config.log_to_file:
        file_handler = logging.FileHandler(
            os.path.join(logs_dir, 'jira_assets_manager.log'),
            encoding='utf-8'
        )
        file_handler.setLevel(getattr(logging, config.log_level))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger
