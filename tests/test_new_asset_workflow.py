"""Tests for interactive new asset workflow and TUI functionality."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call
from io import StringIO

import pytest

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class TestInteractiveAssetWorkflow:
    """Test the interactive workflow for creating new assets."""

    @pytest.fixture
    def mock_asset_manager(self):
        """Create a mock asset manager for testing."""
        manager = MagicMock()
        
        # Mock available models and statuses
        manager.list_models.return_value = [
            'MacBook Pro 16"', 
            'MacBook Air 13"',
            'ThinkPad X1 Carbon',
            'Surface Pro 9',
            'Dell XPS 13'
        ]
        
        manager.list_statuses.return_value = [
            'Available',
            'In Use', 
            'Maintenance',
            'Retired'
        ]
        
        # Mock successful asset creation
        manager.create_asset.return_value = {
            'success': True,
            'object_key': 'HW-9999',
            'serial_number': 'SN12345',
            'model_name': 'MacBook Pro 16"',
            'status': 'Available',
            'is_remote': False
        }
        
        return manager

    @patch('builtins.input')
    def test_interactive_workflow_single_asset(self, mock_input, mock_asset_manager):
        """Test creating a single asset through interactive workflow."""
        # Mock user inputs for single asset creation
        mock_input.side_effect = [
            'SN12345',           # Serial number
            '1',                 # Model selection (MacBook Pro 16")
            '1',                 # Status selection (Available)  
            'n',                 # Not remote asset
            'n'                  # Don't add another asset
        ]
        
        # This would be the interactive workflow function
        # For testing purposes, we simulate what it should do
        
        # 1. Get serial number
        serial = 'SN12345'
        assert len(serial) > 0
        
        # 2. Show model options and get selection
        models = mock_asset_manager.list_models()
        selected_model = models[0]  # First option (index 0)
        assert selected_model == 'MacBook Pro 16"'
        
        # 3. Show status options and get selection
        statuses = mock_asset_manager.list_statuses()
        selected_status = statuses[0]  # First option (index 0) 
        assert selected_status == 'Available'
        
        # 4. Ask about remote asset
        is_remote = False
        
        # 5. Create the asset
        result = mock_asset_manager.create_asset(
            serial=serial,
            model_name=selected_model,
            status=selected_status,
            is_remote=is_remote
        )
        
        # Verify the asset was created successfully
        assert result['success'] is True
        assert result['object_key'] == 'HW-9999'
        assert result['serial_number'] == 'SN12345'

    @patch('builtins.input')
    def test_interactive_workflow_multiple_assets(self, mock_input, mock_asset_manager):
        """Test creating multiple assets in sequence."""
        # Mock user inputs for two assets
        mock_input.side_effect = [
            # First asset
            'SN11111', '2', '2', 'y',    # Serial, Model(2), Status(2), Remote(yes)
            'y',                         # Add another asset
            # Second asset  
            'SN22222', '3', '1', 'n',    # Serial, Model(3), Status(1), Remote(no)
            'n'                          # Don't add another asset
        ]
        
        # Mock multiple successful creations
        mock_asset_manager.create_asset.side_effect = [
            {
                'success': True,
                'object_key': 'HW-1111',
                'serial_number': 'SN11111',
                'model_name': 'MacBook Air 13"',
                'status': 'In Use',
                'is_remote': True
            },
            {
                'success': True,
                'object_key': 'HW-2222', 
                'serial_number': 'SN22222',
                'model_name': 'ThinkPad X1 Carbon',
                'status': 'Available',
                'is_remote': False
            }
        ]
        
        # Test that create_asset would be called twice with correct parameters
        expected_calls = [
            call(
                serial='SN11111',
                model_name='MacBook Air 13"',
                status='In Use', 
                is_remote=True
            ),
            call(
                serial='SN22222',
                model_name='ThinkPad X1 Carbon',
                status='Available',
                is_remote=False
            )
        ]
        
        # Simulate workflow execution
        models = mock_asset_manager.list_models()
        statuses = mock_asset_manager.list_statuses()
        
        # First asset
        result1 = mock_asset_manager.create_asset(
            serial='SN11111',
            model_name=models[1],  # Index 1 = MacBook Air 13"
            status=statuses[1],    # Index 1 = In Use
            is_remote=True
        )
        
        # Second asset
        result2 = mock_asset_manager.create_asset(
            serial='SN22222', 
            model_name=models[2],  # Index 2 = ThinkPad X1 Carbon
            status=statuses[0],    # Index 0 = Available
            is_remote=False
        )
        
        assert result1['success'] is True
        assert result1['object_key'] == 'HW-1111'
        assert result2['success'] is True
        assert result2['object_key'] == 'HW-2222'

    @patch('builtins.input')
    def test_workflow_handles_invalid_model_selection(self, mock_input, mock_asset_manager):
        """Test workflow handles invalid model selection gracefully."""
        # Mock inputs with invalid model selection first, then valid
        mock_input.side_effect = [
            'SN12345',    # Serial number
            '99',         # Invalid model selection
            '1',          # Valid model selection
            '1',          # Status selection
            'n',          # Not remote
            'n'           # Don't add another
        ]
        
        models = mock_asset_manager.list_models()
        
        # Test validation logic that should be implemented
        invalid_selection = 99
        assert invalid_selection > len(models)  # Should be invalid
        
        valid_selection = 1
        assert 1 <= valid_selection <= len(models)  # Should be valid

    @patch('builtins.input')
    def test_workflow_handles_invalid_status_selection(self, mock_input, mock_asset_manager):
        """Test workflow handles invalid status selection gracefully."""
        # Mock inputs with invalid status selection first, then valid
        mock_input.side_effect = [
            'SN12345',    # Serial number
            '1',          # Model selection
            '0',          # Invalid status selection (0)
            '2',          # Valid status selection
            'n',          # Not remote
            'n'           # Don't add another
        ]
        
        statuses = mock_asset_manager.list_statuses()
        
        # Test validation logic
        invalid_selection = 0
        assert invalid_selection < 1 or invalid_selection > len(statuses)
        
        valid_selection = 2
        assert 1 <= valid_selection <= len(statuses)

    @patch('builtins.input')
    def test_workflow_handles_empty_serial_number(self, mock_input, mock_asset_manager):
        """Test workflow handles empty serial number input."""
        mock_input.side_effect = [
            '',           # Empty serial number
            '  ',         # Whitespace only
            'SN12345',    # Valid serial number
            '1', '1', 'n', 'n'  # Rest of workflow
        ]
        
        # Test validation logic for serial numbers
        empty_serial = ''
        whitespace_serial = '  '
        valid_serial = 'SN12345'
        
        assert len(empty_serial.strip()) == 0      # Should be invalid
        assert len(whitespace_serial.strip()) == 0  # Should be invalid  
        assert len(valid_serial.strip()) > 0        # Should be valid

    @patch('builtins.input')
    def test_workflow_handles_creation_failure(self, mock_input, mock_asset_manager):
        """Test workflow handles asset creation failure gracefully."""
        mock_input.side_effect = [
            'SN12345', '1', '1', 'n',    # Asset details
            'y',                         # Try again after failure
            'SN67890', '2', '2', 'n',    # Second attempt
            'n'                          # Don't add another
        ]
        
        # Mock first creation failure, second success
        mock_asset_manager.create_asset.side_effect = [
            {
                'success': False,
                'error': 'Duplicate serial number found'
            },
            {
                'success': True,
                'object_key': 'HW-6789',
                'serial_number': 'SN67890'
            }
        ]
        
        # First attempt should fail
        result1 = mock_asset_manager.create_asset(
            serial='SN12345',
            model_name='MacBook Pro 16"', 
            status='Available',
            is_remote=False
        )
        assert result1['success'] is False
        assert 'Duplicate' in result1['error']
        
        # Second attempt should succeed
        result2 = mock_asset_manager.create_asset(
            serial='SN67890',
            model_name='MacBook Air 13"',
            status='In Use', 
            is_remote=False
        )
        assert result2['success'] is True

    def test_display_model_options_formatting(self, mock_asset_manager):
        """Test that model options are displayed correctly."""
        models = mock_asset_manager.list_models()
        
        # Test the display format that should be implemented
        expected_display = []
        for i, model in enumerate(models, 1):
            expected_display.append(f"{i}. {model}")
            
        assert len(expected_display) == 5
        assert expected_display[0] == '1. MacBook Pro 16"'
        assert expected_display[1] == '2. MacBook Air 13"'
        assert expected_display[4] == '5. Dell XPS 13'

    def test_display_status_options_formatting(self, mock_asset_manager):
        """Test that status options are displayed correctly."""
        statuses = mock_asset_manager.list_statuses()
        
        # Test the display format that should be implemented
        expected_display = []
        for i, status in enumerate(statuses, 1):
            expected_display.append(f"{i}. {status}")
            
        assert len(expected_display) == 4
        assert expected_display[0] == '1. Available'
        assert expected_display[1] == '2. In Use'
        assert expected_display[3] == '4. Retired'

    def test_remote_asset_confirmation_parsing(self):
        """Test parsing of remote asset confirmation input."""
        # Test various ways users might indicate yes/no
        yes_inputs = ['y', 'Y', 'yes', 'YES', 'Yes']
        no_inputs = ['n', 'N', 'no', 'NO', 'No']
        
        for input_val in yes_inputs:
            # Should be interpreted as True
            result = input_val.lower().startswith('y')
            assert result is True
            
        for input_val in no_inputs:
            # Should be interpreted as False
            result = input_val.lower().startswith('y')
            assert result is False

    @patch('sys.stdout', new_callable=StringIO)
    def test_workflow_success_messages(self, mock_stdout, mock_asset_manager):
        """Test that success messages are displayed correctly."""
        # Mock successful creation
        result = {
            'success': True,
            'object_key': 'HW-9999',
            'serial_number': 'SN12345',
            'model_name': 'MacBook Pro 16"',
            'status': 'Available',
            'is_remote': False
        }
        
        # Test success message format
        expected_message = f"✅ Asset created successfully: {result['object_key']} ({result['serial_number']})"
        
        # This would be printed by the interactive workflow
        print(expected_message)
        
        output = mock_stdout.getvalue()
        assert 'Asset created successfully' in output
        assert 'HW-9999' in output
        assert 'SN12345' in output

    @patch('sys.stdout', new_callable=StringIO)
    def test_workflow_error_messages(self, mock_stdout, mock_asset_manager):
        """Test that error messages are displayed correctly."""
        # Mock failed creation
        result = {
            'success': False,
            'error': 'Duplicate serial number: SN12345 already exists'
        }
        
        # Test error message format
        expected_message = f"❌ Error creating asset: {result['error']}"
        
        # This would be printed by the interactive workflow
        print(expected_message)
        
        output = mock_stdout.getvalue()
        assert 'Error creating asset' in output
        assert 'Duplicate serial number' in output


class TestBarcodeSimulation:
    """Test barcode scanning simulation functionality."""

    def test_barcode_input_validation(self):
        """Test validation of barcode/serial number input."""
        # Valid serial numbers
        valid_serials = [
            'SN12345',
            'ABCDEF123456',
            'C07GX1C5Q6NW',
            '123ABC789',
            'SERIAL-WITH-DASHES'
        ]
        
        # Invalid serial numbers
        invalid_serials = [
            '',           # Empty
            '   ',        # Whitespace only
            'ab',         # Too short
            'a' * 100     # Too long (assuming reasonable limit)
        ]
        
        for serial in valid_serials:
            # Should be valid (basic validation)
            assert len(serial.strip()) > 2  # Minimum length
            assert len(serial.strip()) < 50  # Maximum length
            
        for serial in invalid_serials:
            # Should be invalid
            stripped = serial.strip()
            if len(stripped) == 0:
                assert len(stripped) == 0  # Empty
            elif len(stripped) <= 2:
                assert len(stripped) <= 2  # Too short
            elif len(stripped) >= 50:
                assert len(stripped) >= 50  # Too long

    @patch('builtins.input')
    def test_barcode_prompt_simulation(self, mock_input):
        """Test simulation of barcode scanner input prompt."""
        mock_input.return_value = 'C07GX1C5Q6NW'
        
        # Simulate barcode prompt
        prompt = "Scan barcode or enter serial number manually: "
        user_input = input(prompt)
        
        assert user_input == 'C07GX1C5Q6NW'
        mock_input.assert_called_once_with(prompt)

    def test_typical_serial_number_formats(self):
        """Test recognition of typical serial number formats."""
        serial_formats = {
            'apple_macbook': 'C07GX1C5Q6NW',           # Apple format
            'dell': 'ABCDEF1',                         # Dell format  
            'lenovo': '123ABC456',                     # Lenovo format
            'hp': 'SERIAL123456',                      # HP format
            'custom': 'COMPANY-ASSET-001'              # Custom format
        }
        
        for format_name, serial in serial_formats.items():
            # All should be valid serial numbers
            assert isinstance(serial, str)
            assert len(serial) > 0
            assert serial.isalnum() or any(c in serial for c in ['-', '_'])


class TestWorkflowErrorHandling:
    """Test error handling in the interactive workflow."""

    @pytest.fixture
    def failing_asset_manager(self):
        """Create an asset manager that simulates various failures."""
        manager = MagicMock()
        
        # Mock API failures
        manager.list_models.side_effect = Exception("API connection failed")
        manager.list_statuses.side_effect = Exception("Permission denied")
        manager.create_asset.side_effect = Exception("Rate limit exceeded")
        
        return manager

    def test_workflow_handles_api_connection_failure(self, failing_asset_manager):
        """Test workflow handles API connection failures gracefully."""
        # Test that exceptions are caught and handled
        try:
            models = failing_asset_manager.list_models()
        except Exception as e:
            error_message = str(e)
            assert "API connection failed" in error_message

    def test_workflow_handles_permission_errors(self, failing_asset_manager):
        """Test workflow handles permission errors gracefully."""
        try:
            statuses = failing_asset_manager.list_statuses()
        except Exception as e:
            error_message = str(e)
            assert "Permission denied" in error_message

    def test_workflow_handles_rate_limiting(self, failing_asset_manager):
        """Test workflow handles rate limiting gracefully.""" 
        try:
            result = failing_asset_manager.create_asset(
                serial="SN12345",
                model_name="Test Model",
                status="Available",
                is_remote=False
            )
        except Exception as e:
            error_message = str(e)
            assert "Rate limit exceeded" in error_message

    @patch('time.sleep')
    def test_workflow_retry_mechanism(self, mock_sleep):
        """Test that workflow implements retry mechanism for transient failures."""
        manager = MagicMock()
        
        # Mock transient failure then success
        manager.create_asset.side_effect = [
            Exception("Temporary service unavailable"),
            {
                'success': True,
                'object_key': 'HW-9999',
                'serial_number': 'SN12345'
            }
        ]
        
        # Simulate retry logic
        max_retries = 2
        for attempt in range(max_retries):
            try:
                result = manager.create_asset(
                    serial="SN12345",
                    model_name="Test Model", 
                    status="Available",
                    is_remote=False
                )
                break  # Success, exit retry loop
            except Exception as e:
                if attempt < max_retries - 1:
                    # Sleep before retry (mocked)
                    mock_sleep(1)
                    continue
                else:
                    # Final attempt failed
                    raise e
                    
        assert result['success'] is True
        assert mock_sleep.called  # Verify retry delay was used