"""
OAuth 2.0 Client for Jira Assets Manager

This module handles OAuth 2.0 authentication flow for accessing Jira APIs
with advanced permissions like read:cmdb-schema:jira.

Based on Atlassian's OAuth 2.0 (3LO) implementation:
https://developer.atlassian.com/cloud/jira/platform/oauth-2-3lo-apps/
"""

import json
import logging
import os
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional
from urllib.parse import parse_qs

import requests
from requests_oauthlib import OAuth2Session

from config import config


class OAuthError(Exception):
    """Base exception for OAuth errors."""
    pass


class OAuthFlowError(OAuthError):
    """Raised when OAuth flow fails."""
    pass


class TokenError(OAuthError):
    """Raised when token operations fail."""
    pass


class CallbackHandler(BaseHTTPRequestHandler):
    """HTTP request handler for OAuth callback."""
    
    def do_GET(self):
        """Handle GET request for OAuth callback."""
        # Parse query parameters
        parsed_url = urllib.parse.urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        
        # Validate state parameter for security (CSRF protection)
        if 'state' in query_params:
            received_state = query_params['state'][0]
            expected_state = getattr(self.server, 'expected_state', None)
            if expected_state and received_state != expected_state:
                self.server.authorization_error = "Invalid state parameter - possible CSRF attack"
                self._send_error_response("Security Error: Invalid state parameter")
                return
        
        # Handle successful authorization
        if 'code' in query_params:
            self.server.authorization_code = query_params['code'][0]
            self.server.authorization_state = query_params.get('state', [None])[0]
            self._send_success_response("Authorization successful! You can close this window.")
            return
        
        # Handle OAuth errors
        if 'error' in query_params:
            error_code = query_params['error'][0]
            error_description = query_params.get('error_description', [''])[0]
            error_uri = query_params.get('error_uri', [''])[0]
            
            # Store detailed error information
            self.server.authorization_error = error_code
            self.server.error_description = error_description
            self.server.error_uri = error_uri
            
            # Map common OAuth errors to user-friendly messages
            error_messages = {
                'access_denied': "Access denied - user declined authorization",
                'invalid_request': "Invalid authorization request",
                'unauthorized_client': "Client is not authorized",
                'unsupported_response_type': "Response type not supported",
                'invalid_scope': "Invalid scope requested",
                'server_error': "Authorization server error",
                'temporarily_unavailable': "Authorization server temporarily unavailable"
            }
            
            user_message = error_messages.get(error_code, f"Authorization failed: {error_code}")
            if error_description:
                user_message += f" - {error_description}"
            
            self._send_error_response(user_message)
            return
        
        # No valid parameters found
        self.server.authorization_error = "Invalid callback request - missing required parameters"
        self._send_error_response("Invalid callback request")
    
    def _send_success_response(self, message: str):
        """Send success response to browser."""
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Jira Assets Manager OAuth - Success</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 50px; text-align: center; }}
                .success {{ color: #28a745; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1 class="success">✓ Authorization Successful</h1>
                <p>{message}</p>
                <p><small>You can safely close this tab and return to the terminal.</small></p>
            </div>
        </body>
        </html>
        """.encode())
    
    def _send_error_response(self, message: str):
        """Send error response to browser."""
        self.send_response(400)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Jira Assets Manager OAuth - Error</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 50px; text-align: center; }}
                .error {{ color: #dc3545; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1 class="error">✗ Authorization Failed</h1>
                <p>{message}</p>
                <p><small>Please close this tab and try again from the terminal.</small></p>
            </div>
        </body>
        </html>
        """.encode())
    
    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


class OAuthClient:
    """OAuth 2.0 client for Jira API authentication."""
    
    def __init__(self):
        """Initialize the OAuth client."""
        self.logger = logging.getLogger('jira_assets_manager.oauth_client')
        
        # OAuth configuration
        self.client_id = config.oauth_client_id
        self.client_secret = config.oauth_client_secret
        self.redirect_uri = config.oauth_redirect_uri
        self.scopes = config.oauth_scopes.split()
        
        # Atlassian OAuth URLs
        self.base_url = config.jira_base_url
        self.authorization_base_url = 'https://auth.atlassian.com/authorize'
        self.token_url = 'https://auth.atlassian.com/oauth/token'
        
        # Token storage
        self.token_file = os.path.expanduser('~/.jira_assets_oauth_token.json')
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        
        self.logger.info("Initialized OAuth client")
    
    def get_authorization_url(self) -> str:
        """
        Generate authorization URL for OAuth flow.
        
        Returns:
            Authorization URL string
        """
        # Add offline_access to scopes to get refresh token
        scopes_with_offline = self.scopes.copy()
        if 'offline_access' not in scopes_with_offline:
            scopes_with_offline.append('offline_access')
        
        oauth = OAuth2Session(
            self.client_id,
            redirect_uri=self.redirect_uri,
            scope=scopes_with_offline
        )
        
        authorization_url, state = oauth.authorization_url(
            self.authorization_base_url,
            audience='api.atlassian.com',
            prompt='consent'
        )
        
        # Store state for verification
        self._state = state
        
        return authorization_url
    
    def start_callback_server(self, port: int = 8080) -> str:
        """
        Start local HTTP server to receive OAuth callback.
        
        Args:
            port: Port to listen on
            
        Returns:
            Authorization code from callback
            
        Raises:
            OAuthFlowError: If callback fails
        """
        server = HTTPServer(('localhost', port), CallbackHandler)
        server.authorization_code = None
        server.authorization_error = None
        server.expected_state = getattr(self, '_state', None)  # Pass expected state for validation
        
        self.logger.info(f"Starting callback server on port {port}")
        
        try:
            # Handle single request
            server.handle_request()
            
            if server.authorization_error:
                raise OAuthFlowError(f"Authorization failed: {server.authorization_error}")
            
            if not server.authorization_code:
                raise OAuthFlowError("No authorization code received")
            
            return server.authorization_code
            
        except Exception as e:
            self.logger.error(f"Callback server error: {e}")
            raise OAuthFlowError(f"Callback server failed: {e}")
        finally:
            server.server_close()
    
    def exchange_code_for_token(self, authorization_code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.
        
        Args:
            authorization_code: Authorization code from OAuth callback
            
        Returns:
            Token response dictionary
            
        Raises:
            TokenError: If token exchange fails
        """
        oauth = OAuth2Session(
            self.client_id,
            redirect_uri=self.redirect_uri
        )
        
        try:
            token = oauth.fetch_token(
                self.token_url,
                authorization_response=None,
                code=authorization_code,
                client_secret=self.client_secret,
                audience='api.atlassian.com'
            )
            
            self.logger.info("Successfully exchanged authorization code for tokens")
            return token
            
        except Exception as e:
            self.logger.error(f"Token exchange failed: {e}")
            raise TokenError(f"Failed to exchange authorization code: {e}")
    
    def save_token(self, token: Dict[str, Any]) -> None:
        """
        Save token to file.
        
        Args:
            token: Token dictionary to save
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
            
            with open(self.token_file, 'w') as f:
                json.dump(token, f, indent=2)
            
            # Set secure permissions
            os.chmod(self.token_file, 0o600)
            
            self.access_token = token.get('access_token')
            self.refresh_token = token.get('refresh_token')
            
            self.logger.info(f"Saved token to {self.token_file}")
            
        except Exception as e:
            self.logger.error(f"Failed to save token: {e}")
            raise TokenError(f"Failed to save token: {e}")
    
    def load_token(self) -> Optional[Dict[str, Any]]:
        """
        Load token from file.
        
        Returns:
            Token dictionary or None if not found
        """
        try:
            if not os.path.exists(self.token_file):
                return None
            
            with open(self.token_file, 'r') as f:
                token = json.load(f)
            
            self.access_token = token.get('access_token')
            self.refresh_token = token.get('refresh_token')
            
            self.logger.info("Loaded saved token")
            return token
            
        except Exception as e:
            self.logger.warning(f"Failed to load token: {e}")
            return None
    
    def refresh_access_token(self) -> Dict[str, Any]:
        """
        Refresh access token using refresh token.
        
        Returns:
            New token dictionary
            
        Raises:
            TokenError: If refresh fails
        """
        if not self.refresh_token:
            raise TokenError("No refresh token available")
        
        oauth = OAuth2Session(self.client_id)
        
        try:
            token = oauth.refresh_token(
                self.token_url,
                refresh_token=self.refresh_token,
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            
            self.logger.info("Successfully refreshed access token")
            self.save_token(token)
            return token
            
        except Exception as e:
            self.logger.error(f"Token refresh failed: {e}")
            raise TokenError(f"Failed to refresh token: {e}")
    
    def is_token_valid(self) -> bool:
        """
        Check if current token is valid by making a test request.
        
        Returns:
            True if token is valid
        """
        if not self.access_token:
            return False
        
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Accept': 'application/json'
            }
            
            # Test with a simple API call
            response = requests.get(
                f"{self.base_url}/rest/api/3/myself",
                headers=headers,
                timeout=10
            )
            
            return response.status_code == 200
            
        except Exception as e:
            self.logger.debug(f"Token validation failed: {e}")
            return False
    
    def get_valid_access_token(self) -> str:
        """
        Get a valid access token, refreshing if necessary.
        
        Returns:
            Valid access token
            
        Raises:
            TokenError: If unable to get valid token
        """
        # Try to load existing token
        if not self.access_token:
            self.load_token()
        
        # Check if current token is valid
        if self.access_token and self.is_token_valid():
            return self.access_token
        
        # Try to refresh token
        if self.refresh_token:
            try:
                self.refresh_access_token()
                return self.access_token
            except TokenError:
                self.logger.warning("Failed to refresh token, need new authorization")
        
        # Need new authorization
        raise TokenError("No valid token available, need to re-authorize")
    
    def authorize(self) -> str:
        """
        Perform complete OAuth authorization flow.
        
        Returns:
            Valid access token
            
        Raises:
            OAuthFlowError: If authorization fails
        """
        self.logger.info("Starting OAuth authorization flow")
        
        # Generate authorization URL
        auth_url = self.get_authorization_url()
        
        # Open browser for user authorization
        print("Opening browser for authorization...")
        print(f"If browser doesn't open automatically, visit: {auth_url}")
        
        webbrowser.open(auth_url)
        
        # Start callback server and wait for response
        try:
            authorization_code = self.start_callback_server()
        except OAuthFlowError:
            raise
        
        # Exchange code for tokens
        token = self.exchange_code_for_token(authorization_code)
        
        # Save tokens
        self.save_token(token)
        
        self.logger.info("OAuth authorization completed successfully")
        return self.access_token
    
    def get_auth_headers(self) -> Dict[str, str]:
        """
        Get authentication headers for API requests.
        
        Returns:
            Dictionary of headers
            
        Raises:
            TokenError: If unable to get valid token
        """
        access_token = self.get_valid_access_token()
        
        return {
            'Authorization': f'Bearer {access_token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
    
    def clear_tokens(self) -> None:
        """Clear stored tokens."""
        if os.path.exists(self.token_file):
            os.remove(self.token_file)
            self.logger.info("Cleared stored tokens")
        
        self.access_token = None
        self.refresh_token = None
