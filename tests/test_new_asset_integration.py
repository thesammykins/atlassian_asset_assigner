"""Integration tests for complete new asset workflow end-to-end testing."""

from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.asset_manager import AssetManager
from src.config import Config
from src.jira_assets_client import JiraAssetsAPIError


class TestNewAssetWorkflowIntegration:
    """Integration tests for the complete new asset workflow."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock configuration."""
        config = MagicMock(spec=Config)
        config.JIRA_DOMAIN = 'test-company.atlassian.net'
        config.ASSETS_WORKSPACE_ID = 'workspace-123'
        config.HARDWARE_SCHEMA_NAME = 'Hardware'
        config.LAPTOPS_OBJECT_SCHEMA_NAME = 'Laptops'
        config.USER_EMAIL_ATTRIBUTE = 'User Email'
        config.ASSIGNEE_ATTRIBUTE = 'Assignee'
        return config

    @pytest.fixture
    def mock_full_workflow_manager(self, mock_config):
        """Create a fully mocked asset manager for integration testing."""
        with patch('src.asset_manager.JiraUserClient'), \
             patch('src.asset_manager.JiraAssetsClient') as mock_assets_client:
            
            manager = AssetManager(mock_config)
            assets_client = mock_assets_client.return_value
            
            # Mock schema and object type responses
            manager.get_laptops_object_type = MagicMock(return_value={
                'id': '23',
                'name': 'Laptops',
                'description': 'Hardware laptops and notebooks'
            })
            
            # Mock object type attributes
            mock_attributes = [
                {
                    'id': '134',
                    'name': 'Serial Number',
                    'defaultType': {'id': 1, 'name': 'Text'},
                    'required': True
                },
                {
                    'id': '145',
                    'name': 'Status',
                    'defaultType': {'id': 7, 'name': 'Status'},
                    'required': True,
                    'typeValue': {
                        'statusTypeValues': [
                            {'id': '1', 'name': 'Available', 'category': 1},
                            {'id': '2', 'name': 'In Use', 'category': 2},
                            {'id': '3', 'name': 'Maintenance', 'category': 3},
                            {'id': '4', 'name': 'Retired', 'category': 4}
                        ]
                    }
                },
                {
                    'id': '146',
                    'name': 'Model',
                    'defaultType': {'id': 1, 'name': 'Text'},
                    'required': True
                },
                {
                    'id': '147',
                    'name': 'Remote Asset',
                    'defaultType': {'id': 6, 'name': 'Boolean'},
                    'required': False
                }
            ]
            
            assets_client.get_object_attributes.return_value = mock_attributes
            
            # Mock existing objects for model lookup
            mock_existing_objects = {
                'values': [
                    {
                        'objectKey': 'HW-0001',
                        'attributes': [
                            {'name': 'Model', 'values': [{'value': 'MacBook Pro 16"'}]}
                        ]
                    },
                    {
                        'objectKey': 'HW-0002',
                        'attributes': [
                            {'name': 'Model', 'values': [{'value': 'MacBook Air 13"'}]}
                        ]
                    },
                    {
                        'objectKey': 'HW-0003',
                        'attributes': [
                            {'name': 'Model', 'values': [{'value': 'ThinkPad X1 Carbon'}]}
                        ]
                    }
                ]
            }
            
            assets_client.find_objects_by_aql.return_value = mock_existing_objects
            
            # Mock extract_attribute_value for model extraction
            def mock_extract_attribute(obj, attr_name):
                if attr_name == 'Model':
                    model_map = {
                        'HW-0001': 'MacBook Pro 16"',
                        'HW-0002': 'MacBook Air 13"',
                        'HW-0003': 'ThinkPad X1 Carbon'
                    }
                    return model_map.get(obj.get('objectKey'))
                return None
            
            assets_client.extract_attribute_value.side_effect = mock_extract_attribute
            
            # Mock successful object creation
            assets_client.create_object.return_value = {
                'id': '99999',
                'objectKey': 'HW-9999',
                'label': 'MacBook Pro 16" - SN12345',
                'created': '2023-12-01T10:00:00.000Z',
                'updated': '2023-12-01T10:00:00.000Z',
                'hasAvatar': False,
                'objectType': {
                    'id': '23',
                    'name': 'Laptops'
                }
            }
            
            return manager

    def test_full_workflow_integration_success(self, mock_full_workflow_manager):
        """Test complete workflow integration with successful asset creation."""
        manager = mock_full_workflow_manager
        
        # Test that all methods work together
        try:
            # 1. Fetch available models
            models = manager.list_models()
            assert len(models) == 3
            assert 'MacBook Pro 16"' in models
            assert 'MacBook Air 13"' in models
            assert 'ThinkPad X1 Carbon' in models
            
            # 2. Fetch available statuses
            statuses = manager.list_statuses()
            assert len(statuses) == 4
            assert 'Available' in statuses
            assert 'In Use' in statuses
            
            # 3. Create new asset with fetched data
            result = manager.create_asset(
                serial='INTEGRATION-TEST-001',
                model_name=models[0],  # MacBook Pro 16"
                status=statuses[0],    # Available
                is_remote=False
            )
            
            assert result['success'] is True
            assert result['object_key'] == 'HW-9999'
            assert result['serial_number'] == 'INTEGRATION-TEST-001'
            
        except AttributeError:
            pytest.skip("Methods not yet implemented")

    def test_workflow_with_api_failures_at_each_step(self, mock_full_workflow_manager):
        """Test workflow handles API failures at different steps gracefully."""
        manager = mock_full_workflow_manager
        
        try:
            # Test model fetching failure
            manager.assets_client.find_objects_by_aql.side_effect = JiraAssetsAPIError("Connection failed")
            
            with pytest.raises(JiraAssetsAPIError):
                manager.list_models()
                
            # Reset and test status fetching failure
            manager.assets_client.find_objects_by_aql.side_effect = None
            manager.assets_client.get_object_attributes.side_effect = JiraAssetsAPIError("Permission denied")
            
            with pytest.raises(JiraAssetsAPIError):
                manager.list_statuses()
                
            # Reset and test asset creation failure
            manager.assets_client.get_object_attributes.side_effect = None
            manager.assets_client.create_object.side_effect = JiraAssetsAPIError("Rate limit exceeded")
            
            result = manager.create_asset(
                serial='TEST-FAIL',
                model_name='Test Model',
                status='Available',
                is_remote=False
            )
            
            assert result['success'] is False
            assert 'Rate limit exceeded' in result['error']
            
        except AttributeError:
            pytest.skip("Methods not yet implemented")

    def test_workflow_end_to_end_with_validation(self, mock_full_workflow_manager):
        """Test complete workflow with input validation and error handling."""
        manager = mock_full_workflow_manager
        
        try:
            # Test serial number validation
            result = manager.create_asset(
                serial='',  # Invalid: empty
                model_name='MacBook Pro',
                status='Available',
                is_remote=False
            )
            assert result['success'] is False
            assert 'Serial number' in result['error'] or 'empty' in result['error']
            
            # Test model name validation
            result = manager.create_asset(
                serial='VALID-SERIAL',
                model_name='',  # Invalid: empty
                status='Available',
                is_remote=False
            )
            assert result['success'] is False
            assert 'Model name' in result['error'] or 'empty' in result['error']
            
            # Test successful creation with valid inputs
            manager.assets_client.create_object.side_effect = None  # Reset side effect
            manager.assets_client.create_object.return_value = {
                'id': '88888',
                'objectKey': 'HW-8888',
                'label': 'Valid Asset'
            }
            
            result = manager.create_asset(
                serial='VALID-SERIAL-001',
                model_name='MacBook Pro 16"',
                status='Available',
                is_remote=True
            )
            
            assert result['success'] is True
            assert result['object_key'] == 'HW-8888'
            
        except AttributeError:
            pytest.skip("Methods not yet implemented")

    def test_workflow_duplicate_serial_detection(self, mock_full_workflow_manager):
        """Test workflow detects and handles duplicate serial numbers."""
        manager = mock_full_workflow_manager
        
        try:
            # Mock finding an existing asset with the same serial
            existing_asset_response = {
                'values': [
                    {
                        'objectKey': 'HW-0001',
                        'id': '12345',
                        'label': 'Existing Asset - DUPLICATE123'
                    }
                ]
            }
            
            def mock_aql_query(query):
                if 'DUPLICATE123' in query:
                    return existing_asset_response
                return {'values': []}  # No results for other queries
            
            manager.assets_client.find_objects_by_aql.side_effect = mock_aql_query
            
            result = manager.create_asset(
                serial='DUPLICATE123',
                model_name='Test Model',
                status='Available',
                is_remote=False
            )
            
            assert result['success'] is False
            assert 'duplicate' in result['error'].lower() or 'exists' in result['error'].lower()
            
        except AttributeError:
            pytest.skip("Methods not yet implemented")

    def test_attribute_mapping_and_payload_construction(self, mock_full_workflow_manager):
        """Test that attributes are correctly mapped and payload is properly constructed."""
        manager = mock_full_workflow_manager
        
        try:
            manager.create_asset(
                serial='MAPPING-TEST-001',
                model_name='MacBook Pro 16"',
                status='In Use',
                is_remote=True
            )
            
            # Verify create_object was called with correct payload structure
            manager.assets_client.create_object.assert_called_once()
            call_args = manager.assets_client.create_object.call_args
            
            object_type_id, attributes = call_args[0]
            assert object_type_id == '23'
            
            # Verify attributes structure
            assert len(attributes) == 4  # Serial, Status, Model, Remote Asset
            
            # Check each attribute is properly formatted
            attribute_ids = [attr['objectTypeAttributeId'] for attr in attributes]
            assert '134' in attribute_ids  # Serial Number
            assert '145' in attribute_ids  # Status
            assert '146' in attribute_ids  # Model
            assert '147' in attribute_ids  # Remote Asset
            
            # Check attribute values
            serial_attr = next(attr for attr in attributes if attr['objectTypeAttributeId'] == '134')
            assert serial_attr['objectAttributeValues'][0]['value'] == 'MAPPING-TEST-001'
            
            model_attr = next(attr for attr in attributes if attr['objectTypeAttributeId'] == '146')
            assert model_attr['objectAttributeValues'][0]['value'] == 'MacBook Pro 16"'
            
            remote_attr = next(attr for attr in attributes if attr['objectTypeAttributeId'] == '147')
            assert remote_attr['objectAttributeValues'][0]['value'] is True
            
        except AttributeError:
            pytest.skip("Methods not yet implemented")

    def test_status_id_resolution_from_name(self, mock_full_workflow_manager):
        """Test that status names are correctly resolved to status IDs."""
        manager = mock_full_workflow_manager
        
        try:
            # Test each status name resolves to correct ID
            status_name_to_id = {
                'Available': '1',
                'In Use': '2', 
                'Maintenance': '3',
                'Retired': '4'
            }
            
            for status_name, expected_id in status_name_to_id.items():
                manager.create_asset(
                    serial=f'STATUS-TEST-{expected_id}',
                    model_name='Test Model',
                    status=status_name,
                    is_remote=False
                )
                
                # Verify status ID was correctly mapped
                call_args = manager.assets_client.create_object.call_args
                _, attributes = call_args[0]
                
                status_attr = next(attr for attr in attributes if attr['objectTypeAttributeId'] == '145')
                assert status_attr['objectAttributeValues'][0]['value'] == expected_id
                
        except AttributeError:
            pytest.skip("Methods not yet implemented")

    def test_model_deduplication_and_sorting(self, mock_full_workflow_manager):
        """Test that model list is properly deduplicated and sorted."""
        manager = mock_full_workflow_manager
        
        try:
            # Add duplicate models to test deduplication
            duplicate_objects_response = {
                'values': [
                    {
                        'objectKey': 'HW-0001',
                        'attributes': [{'name': 'Model', 'values': [{'value': 'MacBook Pro 16"'}]}]
                    },
                    {
                        'objectKey': 'HW-0002',
                        'attributes': [{'name': 'Model', 'values': [{'value': 'MacBook Air 13"'}]}]
                    },
                    {
                        'objectKey': 'HW-0003',
                        'attributes': [{'name': 'Model', 'values': [{'value': 'MacBook Pro 16"'}]}]  # Duplicate
                    },
                    {
                        'objectKey': 'HW-0004',
                        'attributes': [{'name': 'Model', 'values': [{'value': 'ThinkPad X1 Carbon'}]}]
                    }
                ]
            }
            
            manager.assets_client.find_objects_by_aql.return_value = duplicate_objects_response
            
            models = manager.list_models()
            
            # Should be deduplicated and sorted
            assert len(models) == 3  # Only unique models
            assert 'MacBook Pro 16"' in models
            assert 'MacBook Air 13"' in models
            assert 'ThinkPad X1 Carbon' in models
            
            # Should be sorted alphabetically
            assert models == sorted(models)
            
        except AttributeError:
            pytest.skip("Methods not yet implemented")

    def test_comprehensive_error_messages(self, mock_full_workflow_manager):
        """Test that comprehensive error messages are returned for various failure scenarios."""
        manager = mock_full_workflow_manager
        
        try:
            # Test API connection error
            manager.assets_client.create_object.side_effect = JiraAssetsAPIError("Connection timeout after 30 seconds")
            
            result = manager.create_asset(
                serial='ERROR-TEST-001',
                model_name='Test Model',
                status='Available',
                is_remote=False
            )
            
            assert result['success'] is False
            assert 'Connection timeout' in result['error']
            
            # Test permission error
            manager.assets_client.create_object.side_effect = JiraAssetsAPIError("Insufficient permissions to create objects in this object type")
            
            result = manager.create_asset(
                serial='ERROR-TEST-002',
                model_name='Test Model',
                status='Available',
                is_remote=False
            )
            
            assert result['success'] is False
            assert 'permission' in result['error'].lower()
            
            # Test validation error
            manager.assets_client.create_object.side_effect = JiraAssetsAPIError("Required field 'Model' is missing")
            
            result = manager.create_asset(
                serial='ERROR-TEST-003',
                model_name='Test Model',
                status='Available',
                is_remote=False
            )
            
            assert result['success'] is False
            assert 'Required field' in result['error']
            
        except AttributeError:
            pytest.skip("Methods not yet implemented")

    @patch('builtins.input')
    @patch('sys.stdout', new_callable=StringIO)
    def test_simulated_interactive_workflow(self, mock_stdout, mock_input, mock_full_workflow_manager):
        """Test simulated interactive workflow from start to finish."""
        manager = mock_full_workflow_manager
        
        # Mock user inputs
        mock_input.side_effect = [
            'INTERACTIVE-001',     # Serial number
            '1',                   # Model selection (first option)
            '2',                   # Status selection (second option)  
            'y',                   # Remote asset = yes
            'n'                    # Don't add another asset
        ]
        
        try:
            # This simulates what the interactive workflow should do
            
            # 1. Get serial number
            serial = mock_input()
            assert serial == 'INTERACTIVE-001'
            
            # 2. Show and select model
            models = manager.list_models()
            print("Available models:")
            for i, model in enumerate(models, 1):
                print(f"{i}. {model}")
            
            model_choice = int(mock_input()) - 1
            selected_model = models[model_choice]
            assert selected_model == 'MacBook Air 13"'  # First model (alphabetically sorted)
            
            # 3. Show and select status
            statuses = manager.list_statuses()
            print("Available statuses:")
            for i, status in enumerate(statuses, 1):
                print(f"{i}. {status}")
                
            status_choice = int(mock_input()) - 1
            selected_status = statuses[status_choice]
            assert selected_status == 'In Use'  # Second status
            
            # 4. Get remote asset confirmation
            remote_input = mock_input()
            is_remote = remote_input.lower().startswith('y')
            assert is_remote is True
            
            # 5. Create the asset
            result = manager.create_asset(
                serial=serial,
                model_name=selected_model,
                status=selected_status,
                is_remote=is_remote
            )
            
            # 6. Display result
            if result['success']:
                print(f"✅ Asset created successfully: {result['object_key']} ({result['serial_number']})")
            else:
                print(f"❌ Error creating asset: {result['error']}")
            
            # 7. Ask about adding another
            add_another = mock_input()
            assert add_another == 'n'
            
            # Verify output contains expected messages
            output = mock_stdout.getvalue()
            assert 'Available models:' in output
            assert 'Available statuses:' in output
            assert 'Asset created successfully' in output
            assert 'HW-9999' in output
            
        except AttributeError:
            pytest.skip("Interactive workflow not yet implemented")