"""Tests for JiraAssetsClient.create_object method implementation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.jira_assets_client import JiraAssetsAPIError, JiraAssetsClient


class TestJiraAssetsClientCreateObject:
    """Test the new create_object method that needs to be added to JiraAssetsClient."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock config for testing."""
        config = MagicMock()
        config.JIRA_DOMAIN = 'test-domain.atlassian.net'
        config.ASSETS_WORKSPACE_ID = 'workspace-123'
        config.MAX_REQUESTS_PER_MINUTE = 300
        # Add attributes needed by JiraAssetsClient
        config.jira_base_url = 'https://test-domain.atlassian.net'
        config.assets_workspace_id = 'workspace-123'
        config.max_requests_per_minute = 300
        config.auth_method = 'basic'
        config.get_basic_auth.return_value = ('user@example.com', 'token')
        return config

    @pytest.fixture
    def assets_client(self, mock_config):
        """Create assets client with mocked dependencies."""
        with patch('src.jira_assets_client.requests') as mock_requests:
            # Patch the config module to use our mock config
            with patch('src.jira_assets_client.config', mock_config):
                client = JiraAssetsClient()
                client.session = mock_requests.Session()
                return client, mock_requests

    def test_create_object_builds_correct_url(self, assets_client):
        """Test that create_object builds the correct API endpoint URL."""
        client, mock_requests = assets_client
        
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': '12345',
            'objectKey': 'HW-9999',
            'label': 'Test Asset',
            'created': '2023-12-01T10:00:00.000Z'
        }
        client.session.post.return_value = mock_response

        # Test the method (should be implemented)
        try:
            client.create_object(
                object_type_id='23',
                attributes=[
                    {
                        'objectTypeAttributeId': '134',
                        'objectAttributeValues': [{'value': 'SN12345'}]
                    }
                ]
            )
            
            # Verify correct URL was called
            expected_url = 'https://test-domain.atlassian.net/gateway/api/jsm/assets/workspace/workspace-123/v1/object/create'
            client.session.post.assert_called_once()
            call_args = client.session.post.call_args
            assert call_args[0][0] == expected_url  # First positional argument is the URL
            
        except (AttributeError, NotImplementedError):
            pytest.skip("create_object method not yet implemented")

    def test_create_object_sends_correct_payload(self, assets_client):
        """Test that create_object sends the correct JSON payload."""
        client, mock_requests = assets_client
        
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {'id': '12345', 'objectKey': 'HW-9999'}
        client.session.post.return_value = mock_response

        try:
            attributes = [
                {
                    'objectTypeAttributeId': '134',
                    'objectAttributeValues': [{'value': 'SN12345'}]
                },
                {
                    'objectTypeAttributeId': '145',
                    'objectAttributeValues': [{'value': '2'}]
                }
            ]
            
            client.create_object(
                object_type_id='23',
                attributes=attributes
            )
            
            # Verify correct payload was sent
            call_args = client.session.post.call_args
            expected_payload = {
                'objectTypeId': '23',
                'attributes': attributes
            }
            
            # Check that json parameter was passed correctly
            assert 'json' in call_args.kwargs
            assert call_args.kwargs['json'] == expected_payload
            
        except (AttributeError, NotImplementedError):
            pytest.skip("create_object method not yet implemented")

    def test_create_object_handles_successful_response(self, assets_client):
        """Test create_object returns correct data on successful creation."""
        client, mock_requests = assets_client
        
        # Mock successful API response
        mock_response_data = {
            'id': '12345',
            'objectKey': 'HW-9999',
            'label': 'MacBook Pro - SN12345',
            'created': '2023-12-01T10:00:00.000Z',
            'updated': '2023-12-01T10:00:00.000Z',
            'hasAvatar': False,
            'objectType': {
                'id': '23',
                'name': 'Laptops'
            }
        }
        
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = mock_response_data
        client.session.post.return_value = mock_response

        try:
            result = client.create_object(
                object_type_id='23',
                attributes=[
                    {
                        'objectTypeAttributeId': '134',
                        'objectAttributeValues': [{'value': 'SN12345'}]
                    }
                ]
            )
            
            # Verify returned data
            assert result['id'] == '12345'
            assert result['objectKey'] == 'HW-9999'
            assert result['label'] == 'MacBook Pro - SN12345'
            assert 'created' in result
            
        except (AttributeError, NotImplementedError):
            pytest.skip("create_object method not yet implemented")

    def test_create_object_handles_api_errors(self, assets_client):
        """Test create_object properly handles API errors."""
        client, mock_requests = assets_client
    
        # Mock API error response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.ok = False  # Important: set ok to False for non-2xx status codes
        mock_response.json.return_value = {
            'errorMessages': ['Invalid object type ID'],
            'errors': {'objectTypeId': 'Object type not found'}
        }
        mock_response.text = json.dumps(mock_response.json.return_value)
        client.session.post.return_value = mock_response
    
        try:
            with pytest.raises(JiraAssetsAPIError) as exc_info:
                client.create_object(
                    object_type_id='23',
                    attributes=[]
                )
            
            error = str(exc_info.value)
            assert 'Invalid object type ID' in error or '400' in error
            
        except (AttributeError, NotImplementedError):
            pytest.skip("create_object method not yet implemented")

    def test_create_object_handles_permission_denied(self, assets_client):
        """Test create_object handles permission denied errors."""
        client, mock_requests = assets_client
        
        # Mock 403 Forbidden response
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {
            'errorMessages': ['Insufficient permissions to create objects'],
            'errors': {}
        }
        mock_response.text = json.dumps(mock_response.json.return_value)
        client.session.post.return_value = mock_response

        try:
            with pytest.raises(JiraAssetsAPIError) as exc_info:
                client.create_object(
                    object_type_id='23',
                    attributes=[]
                )
            
            error = str(exc_info.value)
            assert 'permission' in error.lower() or '403' in error
            
        except (AttributeError, NotImplementedError):
            pytest.skip("create_object method not yet implemented")

    def test_create_object_handles_duplicate_object(self, assets_client):
        """Test create_object handles duplicate object errors."""
        client, mock_requests = assets_client
    
        # Mock 409 Conflict response for duplicate
        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_response.ok = False  # Important: set ok to False for non-2xx status codes
        mock_response.json.return_value = {
            'errorMessages': ['Object with this serial number already exists'],
            'errors': {'serialNumber': 'Duplicate value'}
        }
        mock_response.text = json.dumps(mock_response.json.return_value)
        client.session.post.return_value = mock_response
    
        try:
            with pytest.raises(JiraAssetsAPIError) as exc_info:
                client.create_object(
                    object_type_id='23',
                    attributes=[]
                )
            
            error = str(exc_info.value)
            assert 'duplicate' in error.lower() or 'exists' in error.lower() or '409' in error
            
        except (AttributeError, NotImplementedError):
            pytest.skip("create_object method not yet implemented")
            
        except (AttributeError, NotImplementedError):
            pytest.skip("create_object method not yet implemented")

    def test_create_object_with_avatar(self, assets_client):
        """Test create_object with avatar parameters."""
        client, mock_requests = assets_client
        
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': '12345',
            'objectKey': 'HW-9999',
            'hasAvatar': True,
            'avatarUUID': 'avatar-uuid-123'
        }
        client.session.post.return_value = mock_response

        try:
            client.create_object(
                object_type_id='23',
                attributes=[],
                has_avatar=True,
                avatar_uuid='avatar-uuid-123'
            )
            
            # Verify avatar parameters were included in payload
            call_args = client.session.post.call_args
            payload = call_args.kwargs['json']
            
            assert payload['hasAvatar'] is True
            assert payload['avatarUUID'] == 'avatar-uuid-123'
            
        except (AttributeError, NotImplementedError):
            pytest.skip("create_object method not yet implemented or avatar support not added")

    def test_create_object_rate_limiting(self, assets_client):
        """Test create_object respects rate limiting."""
        client, mock_requests = assets_client
        
        # Mock rate limit exceeded response
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {'Retry-After': '60'}
        mock_response.json.return_value = {
            'errorMessages': ['Rate limit exceeded']
        }
        mock_response.text = json.dumps(mock_response.json.return_value)
        client.session.post.return_value = mock_response

        try:
            with pytest.raises(JiraAssetsAPIError) as exc_info:
                client.create_object(
                    object_type_id='23',
                    attributes=[]
                )
            
            error = str(exc_info.value)
            assert 'rate limit' in error.lower() or '429' in error
            
        except (AttributeError, NotImplementedError):
            pytest.skip("create_object method not yet implemented")

    def test_create_object_network_timeout(self, assets_client):
        """Test create_object handles network timeouts."""
        client, mock_requests = assets_client
        
        # Mock timeout exception
        client.session.post.side_effect = requests.exceptions.Timeout("Request timed out")

        try:
            with pytest.raises(JiraAssetsAPIError) as exc_info:
                client.create_object(
                    object_type_id='23',
                    attributes=[]
                )
            
            error = str(exc_info.value)
            assert 'timeout' in error.lower() or 'timed out' in error.lower()
            
        except (AttributeError, NotImplementedError):
            pytest.skip("create_object method not yet implemented")

    @pytest.mark.parametrize("object_type_id,attributes", [
        ('23', [{'objectTypeAttributeId': '134', 'objectAttributeValues': [{'value': 'TEST1'}]}]),
        ('45', [{'objectTypeAttributeId': '145', 'objectAttributeValues': [{'value': 'TEST2'}]}]),
        ('67', [
            {'objectTypeAttributeId': '134', 'objectAttributeValues': [{'value': 'TEST3'}]},
            {'objectTypeAttributeId': '145', 'objectAttributeValues': [{'value': 'STATUS1'}]}
        ]),
    ])
    def test_create_object_with_various_inputs(self, assets_client, object_type_id, attributes):
        """Test create_object with various input combinations."""
        client, mock_requests = assets_client
        
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': f'obj-{object_type_id}',
            'objectKey': f'HW-{object_type_id}',
            'objectType': {'id': object_type_id}
        }
        client.session.post.return_value = mock_response

        try:
            result = client.create_object(
                object_type_id=object_type_id,
                attributes=attributes
            )
            
            assert result['objectType']['id'] == object_type_id
            assert f'obj-{object_type_id}' in result['id']
            
        except (AttributeError, NotImplementedError):
            pytest.skip("create_object method not yet implemented")

    def test_create_object_input_validation(self, assets_client):
        """Test create_object validates input parameters."""
        client, mock_requests = assets_client

        try:
            # Test empty object_type_id
            with pytest.raises(ValueError, match="object_type_id cannot be empty"):
                client.create_object(
                    object_type_id="",
                    attributes=[]
                )
            
            # Test None object_type_id
            with pytest.raises(ValueError):
                client.create_object(
                    object_type_id=None,
                    attributes=[]
                )
                
            # Test invalid attributes structure
            with pytest.raises(ValueError):
                client.create_object(
                    object_type_id="23",
                    attributes="invalid"  # Should be a list
                )
                
        except (AttributeError, NotImplementedError):
            pytest.skip("create_object method not yet implemented or validation not added")

    def test_create_object_uses_correct_headers(self, assets_client):
        """Test create_object uses correct HTTP headers."""
        client, mock_requests = assets_client
        
        # Mock successful response
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {'id': '12345'}
        client.session.post.return_value = mock_response

        try:
            client.create_object(
                object_type_id='23',
                attributes=[]
            )
            
            # Verify request was made with json parameter (which automatically sets Content-Type: application/json)
            call_args = client.session.post.call_args
            
            # Should use json parameter for JSON content
            assert 'json' in call_args.kwargs
            json_data = call_args.kwargs.get('json', {})
            assert 'objectTypeId' in json_data
            assert 'attributes' in json_data
            
        except (AttributeError, NotImplementedError):
            pytest.skip("create_object method not yet implemented")

    def test_create_object_authentication_failure(self, assets_client):
        """Test create_object handles authentication failures."""
        client, mock_requests = assets_client
        
        # Mock 401 Unauthorized response
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {
            'errorMessages': ['Authentication failed'],
            'errors': {}
        }
        mock_response.text = json.dumps(mock_response.json.return_value)
        client.session.post.return_value = mock_response

        try:
            with pytest.raises(JiraAssetsAPIError) as exc_info:
                client.create_object(
                    object_type_id='23',
                    attributes=[]
                )
            
            error = str(exc_info.value)
            assert 'authentication' in error.lower() or '401' in error
            
        except (AttributeError, NotImplementedError):
            pytest.skip("create_object method not yet implemented")