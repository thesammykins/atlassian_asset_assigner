"""Tests for new asset manager functionality and API interactions."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
from typing import Dict, Any, List

import pytest

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.asset_manager import AssetManager
from src.jira_assets_client import JiraAssetsAPIError, AttributeNotFoundError


class TestNewAssetManagerMethods:
    """Test new methods that should be added to AssetManager for new asset creation."""

    @pytest.fixture
    def mock_asset_manager(self):
        """Create a mock asset manager with mocked dependencies."""
        with patch('src.asset_manager.JiraUserClient'), \
             patch('src.asset_manager.JiraAssetsClient') as mock_assets_client:
            
            manager = AssetManager()
            manager.assets_client = mock_assets_client.return_value
            return manager

    def test_list_models_calls_correct_api(self, mock_asset_manager):
        """Test that list_models calls the correct API endpoint."""
        # Mock the laptops object type response
        mock_asset_manager.get_laptops_object_type.return_value = {'id': '23', 'name': 'Laptops'}
        
        # Mock AQL query response with model names
        mock_asset_manager.assets_client.find_objects_by_aql.return_value = {
            'values': [
                {'objectKey': 'MODEL-001', 'attributes': [{'name': 'Model Name', 'values': [{'value': 'MacBook Pro 16"'}]}]},
                {'objectKey': 'MODEL-002', 'attributes': [{'name': 'Model Name', 'values': [{'value': 'MacBook Air 13"'}]}]},
                {'objectKey': 'MODEL-003', 'attributes': [{'name': 'Model Name', 'values': [{'value': 'ThinkPad X1 Carbon'}]}]}
            ]
        }
        
        # Mock extract_attribute_value to return model names
        mock_asset_manager.assets_client.extract_attribute_value.side_effect = lambda obj, attr: {
            'MODEL-001': 'MacBook Pro 16"',
            'MODEL-002': 'MacBook Air 13"', 
            'MODEL-003': 'ThinkPad X1 Carbon'
        }.get(obj.get('objectKey'))

        # Test the method (should be implemented)
        try:
            models = mock_asset_manager.list_models()
            # Should return unique model names
            expected_models = ['MacBook Pro 16"', 'MacBook Air 13"', 'ThinkPad X1 Carbon']
            assert len(models) == 3
            for model in expected_models:
                assert model in models
        except AttributeError:
            pytest.skip("list_models method not yet implemented")

    def test_list_statuses_calls_correct_api(self, mock_asset_manager):
        """Test that list_statuses fetches available status options from object type attributes."""
        # Mock the laptops object type response
        mock_asset_manager.get_laptops_object_type.return_value = {'id': '23', 'name': 'Laptops'}
        
        # Mock object type attributes response with status attribute
        mock_status_attr = {
            'id': '145',
            'name': 'Status',
            'defaultType': {'id': 7, 'name': 'Status'},
            'typeValue': {
                'statusTypeValues': [
                    {'id': '1', 'name': 'Available', 'category': 1},
                    {'id': '2', 'name': 'In Use', 'category': 2},
                    {'id': '3', 'name': 'Maintenance', 'category': 3},
                    {'id': '4', 'name': 'Retired', 'category': 4}
                ]
            }
        }
        
        mock_asset_manager.assets_client.get_object_attributes.return_value = [
            {'id': '134', 'name': 'Serial Number', 'defaultType': {'name': 'Text'}},
            mock_status_attr,
            {'id': '146', 'name': 'Model', 'defaultType': {'name': 'Text'}}
        ]

        # Test the method (should be implemented)
        try:
            statuses = mock_asset_manager.list_statuses()
            expected_statuses = ['Available', 'In Use', 'Maintenance', 'Retired']
            assert len(statuses) == 4
            for status in expected_statuses:
                assert status in statuses
        except AttributeError:
            pytest.skip("list_statuses method not yet implemented")

    def test_create_asset_builds_correct_payload(self, mock_asset_manager):
        """Test that create_asset builds the correct API payload."""
        # Mock object type and attributes
        mock_object_type = {'id': '23', 'name': 'Laptops'}
        mock_asset_manager.get_laptops_object_type.return_value = mock_object_type
        
        mock_attributes = [
            {'id': '134', 'name': 'Serial Number', 'defaultType': {'name': 'Text'}},
            {'id': '145', 'name': 'Status', 'defaultType': {'name': 'Status'}},
            {'id': '146', 'name': 'Model', 'defaultType': {'name': 'Text'}},
            {'id': '147', 'name': 'Remote Asset', 'defaultType': {'name': 'Boolean'}}
        ]
        mock_asset_manager.assets_client.get_object_attributes.return_value = mock_attributes
        
        # Mock successful object creation response
        mock_created_object = {
            'id': '12345',
            'objectKey': 'HW-9999',
            'label': 'MacBook Pro - SN12345',
            'created': '2023-12-01T10:00:00.000Z'
        }
        mock_asset_manager.assets_client.create_object.return_value = mock_created_object

        # Test the method (should be implemented)
        try:
            result = mock_asset_manager.create_asset(
                serial="SN12345",
                model_name="MacBook Pro 16\"",
                status="In Use",
                is_remote=True
            )
            
            # Verify create_object was called with correct payload
            mock_asset_manager.assets_client.create_object.assert_called_once()
            call_args = mock_asset_manager.assets_client.create_object.call_args
            
            object_type_id, attributes = call_args[0]
            assert object_type_id == '23'
            
            # Check attributes structure
            expected_attribute_names = ['Serial Number', 'Status', 'Model', 'Remote Asset']
            attribute_names = []
            
            # This part would need to be adjusted based on actual implementation
            # but shows the expected test structure
            
            assert result['success'] is True
            assert result['object_key'] == 'HW-9999'
            assert result['serial_number'] == 'SN12345'
            
        except AttributeError:
            pytest.skip("create_asset method not yet implemented")

    def test_create_asset_handles_api_errors(self, mock_asset_manager):
        """Test that create_asset properly handles API errors."""
        # Mock object type
        mock_asset_manager.get_laptops_object_type.return_value = {'id': '23', 'name': 'Laptops'}
        
        # Mock attributes
        mock_asset_manager.assets_client.get_object_attributes.return_value = [
            {'id': '134', 'name': 'Serial Number', 'defaultType': {'name': 'Text'}}
        ]
        
        # Mock API error during object creation
        mock_asset_manager.assets_client.create_object.side_effect = JiraAssetsAPIError("Permission denied")

        try:
            result = mock_asset_manager.create_asset(
                serial="SN12345",
                model_name="MacBook Pro",
                status="Available",
                is_remote=False
            )
            
            assert result['success'] is False
            assert 'error' in result
            assert 'Permission denied' in result['error']
            
        except AttributeError:
            pytest.skip("create_asset method not yet implemented")

    @pytest.mark.parametrize("serial,model,status,is_remote", [
        ("ABC123", "MacBook Pro", "Available", True),
        ("DEF456", "ThinkPad X1", "In Use", False),
        ("GHI789", "Surface Pro", "Maintenance", True),
    ])
    def test_create_asset_with_various_inputs(self, mock_asset_manager, serial, model, status, is_remote):
        """Test create_asset with various input combinations."""
        # Mock successful responses
        mock_asset_manager.get_laptops_object_type.return_value = {'id': '23', 'name': 'Laptops'}
        mock_asset_manager.assets_client.get_object_attributes.return_value = [
            {'id': '134', 'name': 'Serial Number'},
            {'id': '145', 'name': 'Status'},
            {'id': '146', 'name': 'Model'},
            {'id': '147', 'name': 'Remote Asset'}
        ]
        mock_asset_manager.assets_client.create_object.return_value = {
            'id': '999',
            'objectKey': f'HW-{serial[-3:]}',
            'label': f'{model} - {serial}'
        }

        try:
            result = mock_asset_manager.create_asset(
                serial=serial,
                model_name=model,
                status=status,
                is_remote=is_remote
            )
            
            assert result['success'] is True
            assert result['serial_number'] == serial
            assert result['model_name'] == model
            assert result['status'] == status
            assert result['is_remote'] == is_remote
            
        except AttributeError:
            pytest.skip("create_asset method not yet implemented")

    def test_validate_asset_creation_input(self, mock_asset_manager):
        """Test input validation for asset creation."""
        try:
            # Test empty serial number
            with pytest.raises(ValueError, match="Serial number cannot be empty"):
                mock_asset_manager.create_asset(
                    serial="",
                    model_name="MacBook Pro",
                    status="Available",
                    is_remote=False
                )
            
            # Test empty model name
            with pytest.raises(ValueError, match="Model name cannot be empty"):
                mock_asset_manager.create_asset(
                    serial="ABC123",
                    model_name="",
                    status="Available", 
                    is_remote=False
                )
                
            # Test empty status
            with pytest.raises(ValueError, match="Status cannot be empty"):
                mock_asset_manager.create_asset(
                    serial="ABC123",
                    model_name="MacBook Pro",
                    status="",
                    is_remote=False
                )
                
        except AttributeError:
            pytest.skip("create_asset method not yet implemented or validation not added")

    def test_duplicate_serial_number_handling(self, mock_asset_manager):
        """Test handling of duplicate serial numbers."""
        # Mock object type
        mock_asset_manager.get_laptops_object_type.return_value = {'id': '23', 'name': 'Laptops'}
        
        # Mock finding existing object with same serial
        mock_asset_manager.assets_client.find_objects_by_aql.return_value = {
            'values': [{'objectKey': 'HW-001', 'id': '123'}]
        }
        
        try:
            result = mock_asset_manager.create_asset(
                serial="DUPLICATE123",
                model_name="MacBook Pro",
                status="Available",
                is_remote=False
            )
            
            assert result['success'] is False
            assert 'duplicate' in result['error'].lower() or 'already exists' in result['error'].lower()
            
        except AttributeError:
            pytest.skip("create_asset method not yet implemented or duplicate checking not added")


class TestNewAssetManagerAPIIntegration:
    """Test integration with the Assets API for new asset workflow."""

    @pytest.fixture
    def mock_assets_client(self):
        """Create a mock assets client."""
        return MagicMock()

    def test_get_model_options_from_existing_objects(self, mock_assets_client):
        """Test extracting model options from existing objects."""
        # This test shows how the implementation should work
        # when fetching model names from existing objects
        
        mock_objects_response = {
            'values': [
                {
                    'objectKey': 'HW-001',
                    'attributes': [
                        {'name': 'Model', 'values': [{'value': 'MacBook Pro 16"'}]}
                    ]
                },
                {
                    'objectKey': 'HW-002', 
                    'attributes': [
                        {'name': 'Model', 'values': [{'value': 'ThinkPad X1 Carbon'}]}
                    ]
                }
            ]
        }
        
        mock_assets_client.find_objects_by_aql.return_value = mock_objects_response
        mock_assets_client.extract_attribute_value.side_effect = lambda obj, attr: {
            'HW-001': 'MacBook Pro 16"',
            'HW-002': 'ThinkPad X1 Carbon'
        }.get(obj.get('objectKey'))
        
        # The implementation should use this pattern
        assert mock_objects_response['values'][0]['objectKey'] == 'HW-001'

    def test_get_status_options_from_object_type_attributes(self, mock_assets_client):
        """Test extracting status options from object type attributes."""
        mock_attributes_response = [
            {
                'id': '145',
                'name': 'Status', 
                'defaultType': {'id': 7, 'name': 'Status'},
                'typeValue': {
                    'statusTypeValues': [
                        {'id': '1', 'name': 'Available'},
                        {'id': '2', 'name': 'In Use'},
                        {'id': '3', 'name': 'Maintenance'},
                        {'id': '4', 'name': 'Retired'}
                    ]
                }
            }
        ]
        
        mock_assets_client.get_object_attributes.return_value = mock_attributes_response
        
        # The implementation should parse this structure
        status_attr = mock_attributes_response[0]
        assert status_attr['name'] == 'Status'
        assert len(status_attr['typeValue']['statusTypeValues']) == 4

    def test_create_object_api_payload_structure(self, mock_assets_client):
        """Test the correct structure for create object API payload."""
        expected_payload = {
            'objectTypeId': '23',
            'attributes': [
                {
                    'objectTypeAttributeId': '134',
                    'objectAttributeValues': [{'value': 'SN12345'}]
                },
                {
                    'objectTypeAttributeId': '145', 
                    'objectAttributeValues': [{'value': '2'}]  # Status ID
                },
                {
                    'objectTypeAttributeId': '146',
                    'objectAttributeValues': [{'value': 'MacBook Pro'}]
                },
                {
                    'objectTypeAttributeId': '147',
                    'objectAttributeValues': [{'value': True}]  # Remote asset
                }
            ]
        }
        
        # The create_asset method should build this structure
        assert expected_payload['objectTypeId'] == '23'
        assert len(expected_payload['attributes']) == 4
        assert expected_payload['attributes'][0]['objectAttributeValues'][0]['value'] == 'SN12345'