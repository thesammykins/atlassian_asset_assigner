"""
Jira User API Client

This module provides functionality for interacting with Jira's User API,
including user search by email address and account management.
"""

import logging
import time
from typing import Dict, List, Optional, Any
import requests
from urllib.parse import quote

from config import config
from oauth_client import OAuthClient, TokenError


class JiraUserAPIError(Exception):
    """Base exception for Jira User API errors."""
    pass


class UserNotFoundError(JiraUserAPIError):
    """Raised when a user is not found."""
    pass


class MultipleUsersFoundError(JiraUserAPIError):
    """Raised when multiple users are found for a single email."""
    pass


class RateLimitError(JiraUserAPIError):
    """Raised when rate limit is exceeded."""
    pass


class JiraUserClient:
    """Client for interacting with Jira User API."""
    
    def __init__(self):
        """Initialize the Jira User API client."""
        self.base_url = config.jira_base_url
        self.session = requests.Session()
        
        # For OAuth, we'll use site-specific API routing
        self.site_id = None
        self.api_base_url = None
        
        # Initialize authentication based on configuration
        if config.auth_method == 'oauth':
            self.oauth_client = OAuthClient()
            self.logger = logging.getLogger('jira_assets_manager.user_client')
            self._setup_oauth_auth()
        else:
            self.oauth_client = None
            self.session.auth = config.get_basic_auth()
            self.logger = logging.getLogger('jira_assets_manager.user_client')
            # For basic auth, use the direct domain URL
            self.api_base_url = self.base_url
        
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 60.0 / config.max_requests_per_minute  # seconds between requests
        
        # Caching to avoid duplicate requests
        self.user_cache: Dict[str, Dict[str, Any]] = {}
        
        self.logger = logging.getLogger('jira_assets_manager.user_client')
        
        self.logger.info(f"Initialized Jira User Client for {config.jira_domain}")
    
    def _setup_oauth_auth(self):
        """Setup OAuth authentication headers."""
        try:
            headers = self.oauth_client.get_auth_headers()
            self.session.headers.update(headers)
            self._discover_site_id()
            self.logger.info("OAuth authentication configured")
        except TokenError as e:
            self.logger.warning(f"OAuth token not available: {e}")
            # Don't raise here - let requests fail and handle later
    
    def _discover_site_id(self):
        """Discover the site ID for the Atlassian instance."""
        try:
            # Get accessible resources to find the site ID
            response = requests.get(
                'https://api.atlassian.com/oauth/token/accessible-resources',
                headers=self.session.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                resources = response.json()
                for resource in resources:
                    if resource.get('url') == self.base_url:
                        self.site_id = resource['id']
                        # Set the correct Jira API base URL using site-specific routing
                        self.api_base_url = f"https://api.atlassian.com/ex/jira/{self.site_id}"
                        self.logger.info(f"Discovered site ID: {self.site_id}")
                        return
                
                self.logger.error(f"Site not found in accessible resources for {self.base_url}")
            else:
                self.logger.error(f"Failed to get accessible resources: {response.status_code}")
        
        except Exception as e:
            self.logger.error(f"Failed to discover site ID: {e}")
            # Fallback to the old endpoint structure (will likely fail with OAuth)
            self.api_base_url = self.base_url
    
    def _refresh_oauth_headers(self):
        """Refresh OAuth headers with current valid token."""
        if self.oauth_client:
            try:
                headers = self.oauth_client.get_auth_headers()
                # Remove old auth headers and set new ones
                self.session.headers.pop('Authorization', None)
                self.session.headers.update({'Authorization': headers['Authorization']})
                self.logger.debug("OAuth headers refreshed")
            except TokenError as e:
                self.logger.error(f"Failed to refresh OAuth headers: {e}")
                raise JiraUserAPIError(f"OAuth authentication failed: {e}")
    
    def _rate_limit(self):
        """Implement rate limiting between requests."""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last_request
            self.logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _handle_response(self, response: requests.Response, context: str = "") -> Any:
        """
        Handle API response and raise appropriate exceptions.
        
        Args:
            response: The HTTP response object
            context: Additional context for error messages
            
        Returns:
            Parsed JSON response
            
        Raises:
            RateLimitError: If rate limit is exceeded
            JiraUserAPIError: For other API errors
        """
        # Check for rate limiting
        if response.status_code == 429:
            retry_after = response.headers.get('Retry-After', '60')
            self.logger.warning(f"Rate limit exceeded. Retry after {retry_after} seconds")
            raise RateLimitError(f"Rate limit exceeded. Retry after {retry_after} seconds")
        
        # Log response for debugging
        self.logger.debug(f"API Response [{context}]: {response.status_code} - {response.text[:500]}")
        
        if not response.ok:
            error_msg = f"API request failed [{context}]: {response.status_code} - {response.text}"
            self.logger.error(error_msg)
            raise JiraUserAPIError(error_msg)
        
        try:
            return response.json()
        except ValueError as e:
            error_msg = f"Failed to parse JSON response [{context}]: {e}"
            self.logger.error(error_msg)
            raise JiraUserAPIError(error_msg)
    
    def search_user_by_email(self, email: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Search for a user by email address.
        
        Args:
            email: The email address to search for
            use_cache: Whether to use cached results
            
        Returns:
            User account information including accountId
            
        Raises:
            UserNotFoundError: If no user is found
            MultipleUsersFoundError: If multiple users are found
            JiraUserAPIError: For other API errors
        """
        # Normalize email for consistent caching
        normalized_email = email.lower().strip()
        
        # Check cache first
        if use_cache and normalized_email in self.user_cache:
            self.logger.debug(f"Using cached result for {email}")
            return self.user_cache[normalized_email]
        
        self.logger.info(f"Searching for user with email: {email}")
        
        # Refresh OAuth headers before making the request
        if self.oauth_client:
            self._refresh_oauth_headers()
        
        # Apply rate limiting
        self._rate_limit()
        
        # Prepare API request
        url = f"{self.api_base_url}/rest/api/3/user/search"
        params = {
            'query': email
        }
        
        try:
            self.logger.debug(f"Making request to: {url} with params: {params}")
            response = self.session.get(url, params=params)
            users = self._handle_response(response, f"search user by email: {email}")
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error while searching for user {email}: {e}"
            self.logger.error(error_msg)
            raise JiraUserAPIError(error_msg)
        
        # Process results
        if not users:
            error_msg = f"No user found with email: {email}"
            self.logger.warning(error_msg)
            raise UserNotFoundError(error_msg)
        
        # Filter for exact email match (Jira search can return partial matches)
        exact_matches = [
            user for user in users 
            if user.get('emailAddress', '').lower() == normalized_email
        ]
        
        if not exact_matches:
            error_msg = f"No user found with exact email match: {email}"
            self.logger.warning(error_msg)
            raise UserNotFoundError(error_msg)
        
        if len(exact_matches) > 1:
            # Log details about multiple matches
            account_types = [user.get('accountType', 'unknown') for user in exact_matches]
            self.logger.warning(f"Multiple users found for {email}: {account_types}")
            
            # Prefer 'atlassian' account type over 'customer'
            atlassian_users = [user for user in exact_matches if user.get('accountType') == 'atlassian']
            if len(atlassian_users) == 1:
                self.logger.info(f"Selected atlassian account type for {email}")
                user_info = atlassian_users[0]
            else:
                error_msg = f"Multiple users found for email {email}, cannot determine which to use"
                self.logger.error(error_msg)
                raise MultipleUsersFoundError(error_msg)
        else:
            user_info = exact_matches[0]
        
        # Cache the result
        self.user_cache[normalized_email] = user_info
        
        self.logger.info(f"Found user: {user_info.get('displayName')} (accountId: {user_info.get('accountId')})")
        return user_info
    
    def get_account_id_by_email(self, email: str, use_cache: bool = True) -> str:
        """
        Get accountId for a user by their email address.
        
        Args:
            email: The email address to search for
            use_cache: Whether to use cached results
            
        Returns:
            The user's accountId
            
        Raises:
            UserNotFoundError: If no user is found
            MultipleUsersFoundError: If multiple users are found
            JiraUserAPIError: For other API errors
        """
        user_info = self.search_user_by_email(email, use_cache)
        account_id = user_info.get('accountId')
        
        if not account_id:
            error_msg = f"User found but no accountId available for {email}"
            self.logger.error(error_msg)
            raise JiraUserAPIError(error_msg)
        
        return account_id
    
    def validate_account_id(self, account_id: str) -> bool:
        """
        Validate that an account ID exists and is active.
        
        Args:
            account_id: The account ID to validate
            
        Returns:
            True if account is valid and active, False otherwise
        """
        try:
            self._rate_limit()
            
            url = f"{self.api_base_url}/rest/api/3/user"
            params = {'accountId': account_id}
            
            response = self.session.get(url, params=params)
            
            if response.status_code == 404:
                self.logger.warning(f"Account ID not found: {account_id}")
                return False
            
            user_info = self._handle_response(response, f"validate account {account_id}")
            is_active = user_info.get('active', False)
            
            self.logger.debug(f"Account {account_id} validation: active={is_active}")
            return is_active
            
        except JiraUserAPIError:
            self.logger.warning(f"Could not validate account ID: {account_id}")
            return False
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Network error validating account {account_id}: {e}")
            return False
    
    def clear_cache(self):
        """Clear the user cache."""
        self.logger.info("Clearing user cache")
        self.user_cache.clear()
    
    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get statistics about the user cache.
        
        Returns:
            Dictionary with cache statistics
        """
        return {
            'cached_users': len(self.user_cache),
            'emails_cached': list(self.user_cache.keys())
        }
