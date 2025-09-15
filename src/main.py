#!/usr/bin/env python3
"""
Jira Assets Manager - Main CLI Application

This script manages Jira Assets by:
1. Extracting user email attributes and updating assignee attributes
2. Automatically retiring assets that have retirement dates set

Features:
- User email → Assignee mapping: Extract user email, lookup Jira accountId, update assignee
- Asset retirement: Find assets with retirement dates and update status to "Retired"
- Bulk operations with progress tracking and error handling
- Dry-run mode for safe testing before applying changes

Usage:
    python main.py --test-asset HW-0003      # Test on specific asset
    python main.py --bulk --dry-run          # Preview bulk assignee operation
    python main.py --bulk --execute          # Execute bulk assignee operation
    python main.py --retire-assets --dry-run # Preview retirement operation
    python main.py --retire-assets --execute # Execute retirement operation
"""

# Ensure local imports resolve when running as a script
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import colorama
from colorama import Fore, Style
from tqdm import tqdm

from asset_manager import AssetManager, AssetUpdateError, ValidationError
from config import ConfigurationError, config, setup_logging
from jira_assets_client import (
    AssetNotFoundError,
    JiraAssetsAPIError,
    ObjectTypeNotFoundError,
    SchemaNotFoundError,
)
from oauth_client import OAuthClient, OAuthError, OAuthFlowError, TokenError

# Initialize colorama for cross-platform colored output
colorama.init()


class ProgressTracker:
    """Track and display progress for bulk operations."""
    
    def __init__(self, total_items: int, description: str = "Processing"):
        """Initialize progress tracker."""
        self.total_items = total_items
        self.description = description
        self.current = 0
        self.successful = 0
        self.skipped = 0
        self.errors = 0
        self.progress_bar = None
        
        if total_items > 0:
            self.progress_bar = tqdm(
                total=total_items,
                desc=description,
                unit="assets",
                bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]"
            )
    
    def update(self, result: Dict[str, Any]):
        """Update progress based on result."""
        self.current += 1
        
        if result.get('success'):
            self.successful += 1
        if result.get('skipped'):
            self.skipped += 1
        if result.get('error'):
            self.errors += 1
        
        if self.progress_bar:
            # Update description with current stats
            status = f"{self.description} (✓{self.successful} ⚠{self.skipped} ✗{self.errors})"
            self.progress_bar.set_description(status)
            self.progress_bar.update(1)
    
    def close(self):
        """Close progress bar."""
        if self.progress_bar:
            self.progress_bar.close()
    
    def get_stats(self) -> str:
        """Get summary statistics."""
        return f"Processed: {self.current}/{self.total_items}, Success: {self.successful}, Skipped: {self.skipped}, Errors: {self.errors}"


def print_banner():
    """Print application banner."""
    banner = f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗
║                    Jira Assets Manager                      ║
║              User Email → Assignee Automation               ║
╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}
"""
    print(banner)


def print_colored(message: str, color: str = Fore.WHITE, style: str = Style.NORMAL):
    """Print colored message."""
    print(f"{style}{color}{message}{Style.RESET_ALL}")


def print_error(message: str):
    """Print error message in red."""
    print_colored(f"ERROR: {message}", Fore.RED, Style.BRIGHT)


def print_warning(message: str):
    """Print warning message in yellow."""
    print_colored(f"WARNING: {message}", Fore.YELLOW, Style.BRIGHT)


def print_success(message: str):
    """Print success message in green."""
    print_colored(f"SUCCESS: {message}", Fore.GREEN, Style.BRIGHT)


def print_info(message: str):
    """Print info message in blue."""
    print_colored(f"INFO: {message}", Fore.BLUE)


def save_results(results: List[Dict[str, Any]], filename: str):
    """Save processing results to JSON file."""
    # Ensure backups directory exists
    backups_dir = Path("backups")
    backups_dir.mkdir(exist_ok=True)
    
    filepath = backups_dir / filename
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print_info(f"Results saved to: {filepath}")
        return str(filepath)
    except Exception as e:
        print_error(f"Failed to save results: {e}")
        return None


def display_asset_details(result: Dict[str, Any]):
    """Display detailed information about an asset processing result."""
    object_key = result.get('object_key', 'Unknown')
    
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"Asset: {object_key}")
    print(f"{'='*60}{Style.RESET_ALL}")
    
    # Basic info
    print(f"{'User Email:':<20} {result.get('user_email', 'Not found')}")
    print(f"{'Current Assignee:':<20} {result.get('current_assignee', 'None')}")
    print(f"{'Account ID:':<20} {result.get('account_id', 'Not found')}")
    print(f"{'New Assignee:':<20} {result.get('new_assignee', 'No change')}")
    
    # Status
    if result.get('success'):
        if result.get('updated'):
            print_success("Status: Successfully updated")
        elif result.get('skipped'):
            print_warning(f"Status: Skipped - {result.get('skip_reason', 'Unknown reason')}")
        else:
            print_info("Status: Processed (dry run)")
    else:
        error_msg = result.get('error', 'Unknown error')
        print_error(f"Status: Failed - {error_msg}")
    
    print()


def display_summary(summary: Dict[str, Any]):
    """Display processing summary."""
    print(f"\n{Fore.MAGENTA}{'='*60}")
    print("PROCESSING SUMMARY")
    print(f"{'='*60}{Style.RESET_ALL}")
    
    # Main statistics
    total = summary.get('total_processed', 0)
    successful = summary.get('successful', 0)
    updated = summary.get('updated', 0)
    skipped = summary.get('skipped', 0)
    errors = summary.get('errors', 0)
    success_rate = summary.get('success_rate', 0)
    
    print(f"{'Total Processed:':<20} {total}")
    print(f"{'Successful:':<20} {successful}")
    print(f"{'Updated:':<20} {updated}")
    print(f"{'Skipped:':<20} {skipped}")
    print(f"{'Errors:':<20} {errors}")
    print(f"{'Success Rate:':<20} {success_rate:.1f}%")
    
    # Skip reasons
    skip_reasons = summary.get('skip_reasons', {})
    if skip_reasons:
        print(f"\n{Fore.YELLOW}Skip Reasons:{Style.RESET_ALL}")
        for reason, count in skip_reasons.items():
            print(f"  • {reason}: {count}")
    
    # Error types
    error_types = summary.get('error_types', {})
    if error_types:
        print(f"\n{Fore.RED}Error Types:{Style.RESET_ALL}")
        for error_type, count in error_types.items():
            print(f"  • {error_type}: {count}")
    
    print()


def test_single_asset(asset_manager: AssetManager, object_key: str, dry_run: bool = True) -> Dict[str, Any]:
    """Test processing a single asset."""
    print_info(f"Testing asset: {object_key} (dry_run={dry_run})")
    
    try:
        result = asset_manager.process_asset(object_key, dry_run=dry_run)
        display_asset_details(result)
        return result
        
    except AssetNotFoundError:
        print_error(f"Asset {object_key} not found")
        return {'object_key': object_key, 'success': False, 'error': 'Asset not found'}
    except (ValidationError, AssetUpdateError) as e:
        print_error(f"Processing failed: {e}")
        return {'object_key': object_key, 'success': False, 'error': str(e)}
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return {'object_key': object_key, 'success': False, 'error': f"Unexpected error: {e}"}


def process_bulk_assets(asset_manager: AssetManager, dry_run: bool = True, batch_size: int = None) -> List[Dict[str, Any]]:
    """Process all assets in bulk."""
    if batch_size is None:
        batch_size = config.batch_size
    
    print_info(f"Starting bulk processing (dry_run={dry_run}, batch_size={batch_size})")
    
    try:
        # Get all laptops objects
        print_info("Fetching all laptop assets...")
        all_objects = asset_manager.get_hardware_laptops_objects()
        
        # Filter objects that need processing
        print_info("Filtering assets for processing...")
        objects_to_process = asset_manager.filter_objects_for_processing(all_objects)
        
        if not objects_to_process:
            print_warning("No assets found that need processing")
            return []
        
        print_info(f"Found {len(objects_to_process)} assets to process")
        
        # Process assets with progress tracking
        results = []
        progress = ProgressTracker(len(objects_to_process), "Processing assets")
        
        try:
            for i, asset_obj in enumerate(objects_to_process):
                object_key = asset_obj.get('objectKey', f'unknown_{i}')
                
                try:
                    result = asset_manager.process_asset(object_key, dry_run=dry_run)
                    results.append(result)
                    progress.update(result)
                    
                    # Optional: Add small delay for rate limiting
                    # time.sleep(0.1)
                    
                except Exception as e:
                    error_result = {
                        'object_key': object_key,
                        'success': False,
                        'error': str(e),
                        'dry_run': dry_run,
                        'timestamp': datetime.now().isoformat()
                    }
                    results.append(error_result)
                    progress.update(error_result)
        
        finally:
            progress.close()
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"bulk_processing_results_{timestamp}.json"
        save_results(results, filename)
        
        # Display summary
        summary = asset_manager.get_processing_summary(results)
        display_summary(summary)
        
        return results
        
    except (SchemaNotFoundError, ObjectTypeNotFoundError) as e:
        print_error(f"Configuration error: {e}")
        return []
    except JiraAssetsAPIError as e:
        print_error(f"Assets API error: {e}")
        return []
    except Exception as e:
        print_error(f"Unexpected error during bulk processing: {e}")
        return []


def display_retirement_details(result: Dict[str, Any]):
    """Display detailed information about an asset retirement result."""
    object_key = result.get('object_key', 'Unknown')
    
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"Asset: {object_key}")
    print(f"{'='*60}{Style.RESET_ALL}")
    
    # Basic info
    print(f"{'Retirement Date:':<20} {result.get('retirement_date', 'Not found')}")
    print(f"{'Current Status:':<20} {result.get('current_status', 'None')}")
    print(f"{'New Status:':<20} {result.get('new_status', 'No change')}")
    
    # Status
    if result.get('success'):
        if result.get('updated'):
            print_success("Status: Successfully retired")
        elif result.get('skipped'):
            print_warning(f"Status: Skipped - {result.get('skip_reason', 'Unknown reason')}")
        else:
            print_info("Status: Processed (dry run)")
    else:
        error_msg = result.get('error', 'Unknown error')
        print_error(f"Status: Failed - {error_msg}")
    
    print()


def test_single_retirement(asset_manager: AssetManager, object_key: str, dry_run: bool = True) -> Dict[str, Any]:
    """Test processing a single asset retirement."""
    print_info(f"Testing retirement for asset: {object_key} (dry_run={dry_run})")
    
    try:
        result = asset_manager.process_retirement(object_key, dry_run=dry_run)
        display_retirement_details(result)
        return result
        
    except AssetNotFoundError:
        print_error(f"Asset {object_key} not found")
        return {'object_key': object_key, 'success': False, 'error': 'Asset not found'}
    except (ValidationError, AssetUpdateError) as e:
        print_error(f"Retirement processing failed: {e}")
        return {'object_key': object_key, 'success': False, 'error': str(e)}
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return {'object_key': object_key, 'success': False, 'error': f"Unexpected error: {e}"}


def process_asset_retirements(asset_manager: AssetManager, dry_run: bool = True, batch_size: int = None) -> List[Dict[str, Any]]:
    """Process all assets that need to be retired."""
    if batch_size is None:
        batch_size = config.batch_size
    
    print_info(f"Starting asset retirement processing (dry_run={dry_run}, batch_size={batch_size})")
    
    try:
        # Get all laptops objects with retirement dates
        print_info("Fetching all laptop assets with retirement dates...")
        all_objects = asset_manager.get_assets_pending_retirement()
        
        if not all_objects:
            print_warning("No assets found with retirement dates")
            return []
        
        print_info(f"Found {len(all_objects)} assets with retirement dates")
        
        # Filter objects that need to be retired (not already retired)
        print_info("Filtering assets for retirement...")
        objects_to_retire = asset_manager.filter_assets_for_retirement(all_objects)
        
        if not objects_to_retire:
            print_warning("No assets found that need to be retired (all may already be retired)")
            return []
        
        print_info(f"Found {len(objects_to_retire)} assets to retire")
        
        # Process assets with progress tracking
        results = []
        progress = ProgressTracker(len(objects_to_retire), "Retiring assets")
        
        try:
            for i, asset_obj in enumerate(objects_to_retire):
                object_key = asset_obj.get('objectKey', f'unknown_{i}')
                
                try:
                    result = asset_manager.process_retirement(object_key, dry_run=dry_run)
                    results.append(result)
                    progress.update(result)
                    
                    # Optional: Add small delay for rate limiting
                    # time.sleep(0.1)
                    
                except Exception as e:
                    error_result = {
                        'object_key': object_key,
                        'success': False,
                        'error': str(e),
                        'dry_run': dry_run,
                        'timestamp': datetime.now().isoformat()
                    }
                    results.append(error_result)
                    progress.update(error_result)
        
        finally:
            progress.close()
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"retirement_processing_results_{timestamp}.json"
        save_results(results, filename)
        
        # Display summary
        summary = asset_manager.get_processing_summary(results)
        display_summary(summary)
        
        return results
        
    except (SchemaNotFoundError, ObjectTypeNotFoundError) as e:
        print_error(f"Configuration error: {e}")
        return []
    except JiraAssetsAPIError as e:
        print_error(f"Assets API error: {e}")
        return []
    except Exception as e:
        print_error(f"Unexpected error during retirement processing: {e}")
        return []


def setup_argument_parser() -> argparse.ArgumentParser:
    """Set up command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Jira Assets Manager - Automate user email to assignee mapping",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --test-asset HW-0003             Test on specific asset
  %(prog)s --test-asset HW-0003 --execute  Test and execute update
  %(prog)s --bulk --dry-run                Preview bulk operation
  %(prog)s --bulk                          Execute bulk operation
  %(prog)s --bulk --batch-size 5           Process in smaller batches
  %(prog)s --retire-assets --dry-run       Preview retirement processing
  %(prog)s --retire-assets --execute       Execute retirement processing
  %(prog)s --csv-migrate --csv file.csv --from=8 --to=28 --dry-run         Preview CSV clone migration
  %(prog)s --csv-migrate --csv file.csv --from=8 --to=28 --execute          Execute CSV clone migration
  %(prog)s --csv-migrate --csv file.csv --from=8 --to=28 --delete-original --execute  Execute CSV move migration
        """
    )
    
    # Operation modes
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--test-asset',
        metavar='KEY',
        help='Test processing on a specific asset (e.g., HW-0003)'
    )
    group.add_argument(
        '--bulk',
        action='store_true',
        help='Process all assets in Hardware/Laptops schema'
    )
    group.add_argument(
        '--retire-assets',
        action='store_true',
        help='Retire assets that have a retirement date set'
    )
    group.add_argument(
        '--new',
        action='store_true',
        help='Create new assets interactively with barcode/serial input and model selection'
    )
    group.add_argument(
        '--oauth-setup',
        action='store_true',
        help='Set up OAuth 2.0 authentication (required for bulk operations with schema access)'
    )
    group.add_argument(
        '--csv-migrate',
        action='store_true',
        help='Migrate assets between object types using CSV file with SERIAL_NUMBER column'
    )
    group.add_argument(
        '--cache-info',
        action='store_true',
        help='Show cache information and statistics'
    )
    group.add_argument(
        '--cache-cleanup',
        action='store_true',
        help='Remove expired cache files (older than 24 hours)'
    )
    
    # Execution options
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Preview changes without applying them (default)'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually apply changes (overrides --dry-run)'
    )
    
    # Processing options
    parser.add_argument(
        '--batch-size',
        type=int,
        metavar='N',
        help=f'Batch size for bulk operations (default: {config.batch_size})'
    )
    
    # CSV migration options
    parser.add_argument(
        '--csv',
        metavar='FILE',
        help='Path to CSV file containing SERIAL_NUMBER column for asset migration'
    )
    parser.add_argument(
        '--from',
        dest='from_type_id',
        type=int,
        metavar='ID',
        help='Source object type ID to migrate assets from'
    )
    parser.add_argument(
        '--to',
        dest='to_type_id',
        type=int,
        metavar='ID',
        help='Destination object type ID to migrate assets to'
    )
    parser.add_argument(
        '--delete-original',
        action='store_true',
        help='Delete original assets after successful migration (creates true "move" instead of "clone")'
    )
    
    # Logging options
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Suppress non-error output'
    )
    
    # Utility options
    parser.add_argument(
        '--clear-cache',
        action='store_true',
        help='Clear all caches before processing'
    )
    
    return parser


def show_cache_info(asset_manager: AssetManager):
    """Show cache information and statistics."""
    try:
        cache_info = asset_manager.get_cache_info()
        
        print_info("Cache Information")
        print(f"{'='*60}")
        print(f"{'Cache Directory:':<20} {cache_info['cache_directory']}")
        print(f"{'Cache TTL:':<20} {cache_info['cache_ttl_hours']} hours")
        print(f"{'Total Files:':<20} {cache_info['total_cache_files']}")
        print(f"{'Valid Files:':<20} {cache_info['valid_cache_files']}")
        print(f"{'Expired Files:':<20} {cache_info['expired_cache_files']}")
        print()
        
        if cache_info['cache_files']:
            print_info("Cache Files Details:")
            print(f"{'Name':<30} {'Age (hrs)':<10} {'Status':<10} {'Size (bytes)':<12}")
            print('-' * 64)
            
            for file_info in cache_info['cache_files']:
                status = "✓ Valid" if file_info['is_valid'] else "✗ Expired"
                color = Fore.GREEN if file_info['is_valid'] else Fore.RED
                
                print(f"{file_info['name']:<30} {file_info['age_hours']:<10.1f} {color}{status:<10}{Style.RESET_ALL} {file_info['size_bytes']:<12}")
        else:
            print_info("No cache files found")
            
        return True
        
    except Exception as e:
        print_error(f"Failed to get cache information: {e}")
        return False


def cleanup_cache(asset_manager: AssetManager):
    """Clean up expired cache files."""
    try:
        print_info("Cleaning up expired cache files...")
        
        removed_count = asset_manager.cleanup_expired_cache()
        
        if removed_count > 0:
            print_success(f"Removed {removed_count} expired cache files")
        else:
            print_info("No expired cache files found")
            
        return True
        
    except Exception as e:
        print_error(f"Failed to cleanup cache: {e}")
        return False


def setup_oauth_authentication():
    """Set up OAuth 2.0 authentication interactively."""
    print_info("Setting up OAuth 2.0 authentication for Jira Assets Manager")
    print()
    
    # Check if OAuth is already configured
    if not config.is_oauth_configured():
        print_error("OAuth 2.0 is not configured. Please update your .env file first:")
        print()
        print(f"{Fore.YELLOW}Required OAuth settings in .env:{Style.RESET_ALL}")
        print("AUTH_METHOD=oauth")
        print("OAUTH_CLIENT_ID=your-client-id-here")
        print("OAUTH_CLIENT_SECRET=your-client-secret-here")
        print("OAUTH_REDIRECT_URI=http://localhost:8080/callback")
        print("OAUTH_SCOPES=read:jira-user read:cmdb-object:jira read:cmdb-schema:jira write:cmdb-object:jira")
        print()
        print_info("See the README.md for detailed OAuth setup instructions")
        return False
    
    try:
        oauth_client = OAuthClient()
        
        # Check if we already have valid tokens
        try:
            oauth_client.get_valid_access_token()
            print_success("OAuth 2.0 already configured with valid token")
            print_info("You can now use bulk operations that require schema access")
            return True
        except TokenError:
            pass  # Need to authorize
        
        print_info("Starting OAuth 2.0 authorization flow...")
        print("This will open a browser window for you to authorize the application.")
        print()
        
        # Perform authorization
        oauth_client.authorize()
        
        print()
        print_success("OAuth 2.0 setup completed successfully!")
        print_info("Access token has been saved securely for future use")
        print_info("You can now use bulk operations that require schema access")
        return True
        
    except (OAuthError, OAuthFlowError) as e:
        print_error(f"OAuth setup failed: {e}")
        return False
    except Exception as e:
        print_error(f"Unexpected error during OAuth setup: {e}")
        return False


def validate_environment():
    """Validate environment and configuration."""
    try:
        # This will raise ConfigurationError if something is wrong
        _ = config.jira_base_url
        _ = config.assets_workspace_id
        print_success("Environment configuration validated")
        return True
        
    except ConfigurationError as e:
        print_error(f"Configuration error: {e}")
        print_info("Please check your .env file and ensure all required variables are set")
        return False
    except Exception as e:
        print_error(f"Unexpected configuration error: {e}")
        return False


def display_migration_details(result: Dict[str, Any]):
    """Display detailed information about an asset migration result."""
    serial_number = result.get('serial_number', 'Unknown')
    source_object_key = result.get('source_object_key', 'Not found')
    
    print(f"\n{Fore.CYAN}{'='*60}")
    print(f"Serial Number: {serial_number}")
    print(f"{'='*60}{Style.RESET_ALL}")
    
    # Basic info
    print(f"{'Source Asset:':<20} {source_object_key}")
    print(f"{'Source Type ID:':<20} {result.get('source_object_type_id', 'Unknown')}")
    print(f"{'Target Type ID:':<20} {result.get('target_object_type_id', 'Unknown')}")
    print(f"{'New Asset:':<20} {result.get('new_object_key', 'Not created')}")
    print(f"{'Mapped Attributes:':<20} {result.get('mapped_attributes', 0)}")
    
    # Warnings and unmapped attributes
    warnings = result.get('warnings', [])
    if warnings:
        print(f"\n{Fore.YELLOW}Warnings:{Style.RESET_ALL}")
        for warning in warnings:
            print(f"  • {warning}")
    
    unmapped_attrs = result.get('unmapped_attributes', [])
    if unmapped_attrs:
        print(f"\n{Fore.YELLOW}Unmapped Attributes ({len(unmapped_attrs)}):{Style.RESET_ALL}")
        for attr in unmapped_attrs[:10]:  # Limit to first 10
            print(f"  • {attr}")
        if len(unmapped_attrs) > 10:
            print(f"  ... and {len(unmapped_attrs) - 10} more")
    
    # Status
    if result.get('success'):
        if result.get('dry_run'):
            print_info("Status: Migration preview (dry run)")
        else:
            if result.get('original_deleted'):
                print_success("Status: Migrated and original deleted")
            else:
                print_success("Status: Migrated successfully")
    elif result.get('skipped'):
        print_warning(f"Status: Skipped - {result.get('skip_reason', 'Unknown reason')}")
    else:
        error_msg = result.get('error', 'Unknown error')
        print_error(f"Status: Failed - {error_msg}")
    
    print()


def process_csv_migration(asset_manager: AssetManager, csv_file: str, from_type_id: int, 
                        to_type_id: int, dry_run: bool = True, delete_original: bool = False) -> List[Dict[str, Any]]:
    """Process CSV-based asset migration."""
    migration_type = "move" if delete_original else "clone"
    print_info(f"Starting CSV migration ({migration_type}) (csv={csv_file}, from={from_type_id}, to={to_type_id}, dry_run={dry_run})")
    
    try:
        # Validate arguments
        if not csv_file:
            raise ValidationError("CSV file path is required")
        if not from_type_id:
            raise ValidationError("Source object type ID (--from) is required")
        if not to_type_id:
            raise ValidationError("Target object type ID (--to) is required")
        if from_type_id == to_type_id:
            raise ValidationError("Source and target object type IDs cannot be the same")
        
        # Process migration
        results = asset_manager.process_asset_migration(
            csv_file, from_type_id, to_type_id, dry_run, delete_original=delete_original
        )
        
        if not results:
            print_warning("No assets were processed")
            return []
        
        # Display results for dry run or small numbers of assets
        if dry_run or len(results) <= 5:
            for result in results:
                display_migration_details(result)
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        operation_type = "migration_dry_run" if dry_run else "migration_execute"
        filename = f"{operation_type}_results_{timestamp}.json"
        save_results(results, filename)
        
        # Display summary
        summary = asset_manager.get_processing_summary(results)
        display_summary(summary)
        
        return results
        
    except (ValidationError, FileNotFoundError) as e:
        print_error(f"Migration failed: {e}")
        return []
    except (SchemaNotFoundError, ObjectTypeNotFoundError) as e:
        print_error(f"Configuration error: {e}")
        return []
    except JiraAssetsAPIError as e:
        print_error(f"Assets API error: {e}")
        return []
    except Exception as e:
        print_error(f"Unexpected error during migration: {e}")
        return []


def validate_csv_migration_args(args) -> bool:
    """Validate CSV migration arguments."""
    if not args.csv:
        print_error("--csv argument is required for CSV migration")
        return False
    if not args.from_type_id:
        print_error("--from argument is required for CSV migration")
        return False
    if not args.to_type_id:
        print_error("--to argument is required for CSV migration")
        return False
    return True


def run_new_asset_workflow(asset_manager: AssetManager) -> int:
    """Run interactive new asset creation workflow."""
    print_colored("🚀 Starting new asset creation workflow...", Fore.CYAN, Style.BRIGHT)
    print_colored("Type 'q' at any prompt to quit.", Fore.YELLOW)
    print()
    
    try:
        while True:
            # 1. Prompt for serial number
            while True:
                try:
                    serial = input(f"{Fore.CYAN}🏷️  Scan/enter serial number (or 'q' to quit): {Style.RESET_ALL}").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n👋 Goodbye!")
                    return 0
                    
                if serial.lower() == 'q':
                    print("👋 Goodbye!")
                    return 0
                    
                if not serial:
                    print_error("Serial number cannot be empty. Please try again.")
                    continue
                    
                if len(serial) < 2 or len(serial) > 128:
                    print_error(f"Serial number must be between 2 and 128 characters. Got {len(serial)} characters.")
                    continue
                    
                # Serial number looks valid
                break
            
            # 2. Fetch and display models
            print_info("📦 Loading available models...")
            try:
                models = asset_manager.list_models()
            except Exception as e:
                print_error(f"Error loading models: {e}")
                print_warning("You may need to enter a custom model name.")
                models = []
                
            if not models:
                print_warning("No existing models found. You'll need to enter a custom model.")
                while True:
                    try:
                        model_name = input(f"{Fore.CYAN}📱 Enter model name (or 'q' to quit): {Style.RESET_ALL}").strip()
                    except (EOFError, KeyboardInterrupt):
                        print("\n👋 Goodbye!")
                        return 0
                        
                    if model_name.lower() == 'q':
                        print("👋 Goodbye!")
                        return 0
                        
                    if model_name:
                        break
                    else:
                        print_error("Model name cannot be empty.")
            else:
                print(f"\n{Fore.BLUE}Available models:{Style.RESET_ALL}")
                for i, model in enumerate(models, 1):
                    print(f"  {i}. {model}")
                print(f"  {len(models) + 1}. Enter a custom model")
                print(f"  {Fore.YELLOW}q. Quit{Style.RESET_ALL}")
                
                while True:
                    try:
                        choice = input(f"\n{Fore.CYAN}Choose a model [1-{len(models) + 1}] or 'q': {Style.RESET_ALL}").strip()
                    except (EOFError, KeyboardInterrupt):
                        print("\n👋 Goodbye!")
                        return 0
                        
                    if choice.lower() == 'q':
                        print("👋 Goodbye!")
                        return 0
                    
                    # Check if it's a direct model name match first
                    if choice in models:
                        model_name = choice
                        break
                        
                    # Try numeric selection
                    try:
                        choice_num = int(choice)
                        if 1 <= choice_num <= len(models):
                            model_name = models[choice_num - 1]
                            break
                        elif choice_num == len(models) + 1:
                            # Custom model
                            while True:
                                try:
                                    model_name = input(f"{Fore.CYAN}📱 Enter custom model name (or 'q' to quit): {Style.RESET_ALL}").strip()
                                except (EOFError, KeyboardInterrupt):
                                    print("\n👋 Goodbye!")
                                    return 0
                                    
                                if model_name.lower() == 'q':
                                    print("👋 Goodbye!")
                                    return 0
                                    
                                if model_name:
                                    break
                                else:
                                    print_error("Model name cannot be empty.")
                            break
                        else:
                            print_error(f"Please enter a number between 1 and {len(models) + 1}.")
                    except ValueError:
                        # Not a number, and not an exact model name match, treat as custom model if non-empty
                        if choice.strip():
                            model_name = choice.strip()
                            break
                        else:
                            print_error(f"Please enter a valid number between 1 and {len(models) + 1}.")
            
            # 3. Fetch and display statuses
            print_info("📊 Loading available statuses...")
            try:
                statuses = asset_manager.list_statuses()
            except Exception as e:
                print_error(f"Error loading statuses: {e}")
                print_error("Cannot create asset without valid statuses.")
                continue
                
            if not statuses:
                print_error("No statuses available. Cannot create asset.")
                continue
                
            print(f"\n{Fore.BLUE}Available statuses:{Style.RESET_ALL}")
            for i, status in enumerate(statuses, 1):
                print(f"  {i}. {status}")
            print(f"  {Fore.YELLOW}q. Quit{Style.RESET_ALL}")
            
            while True:
                try:
                    choice = input(f"\n{Fore.CYAN}Choose a status [1-{len(statuses)}] or 'q': {Style.RESET_ALL}").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n👋 Goodbye!")
                    return 0
                    
                if choice.lower() == 'q':
                    print("👋 Goodbye!")
                    return 0
                
                # Check if it's a direct status name match first
                if choice in statuses:
                    status_name = choice
                    break
                    
                # Try numeric selection
                try:
                    choice_num = int(choice)
                    if 1 <= choice_num <= len(statuses):
                        status_name = statuses[choice_num - 1]
                        break
                    else:
                        print_error(f"Please enter a number between 1 and {len(statuses)}.")
                except ValueError:
                    print_error(f"Please enter a valid number between 1 and {len(statuses)} or exact status name.")
            
            # 4. Ask if this is for a remote user
            while True:
                try:
                    remote_input = input(f"\n{Fore.CYAN}🌍 Is this asset for a remote user? (y/n/q): {Style.RESET_ALL}").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("\n👋 Goodbye!")
                    return 0
                    
                if remote_input == 'q':
                    print("👋 Goodbye!")
                    return 0
                    
                if remote_input in ['y', 'yes']:
                    is_remote = True
                    break
                elif remote_input in ['n', 'no']:
                    is_remote = False
                    break
                else:
                    print_error("Please enter 'y' for yes, 'n' for no, or 'q' to quit.")
            
            # 5. Collect optional fields (all can be skipped)
            optional_fields = {}
            
            # Invoice Number (optional)
            while True:
                try:
                    invoice_input = input(f"\n{Fore.CYAN}🧾 Invoice Number (optional, press Enter to skip): {Style.RESET_ALL}").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n👋 Goodbye!")
                    return 0
                
                if invoice_input.lower() == 'q':
                    print("👋 Goodbye!")
                    return 0
                
                # Allow empty input (skip)
                optional_fields['invoice_number'] = invoice_input if invoice_input else None
                break
            
            # Purchase Date (optional)
            while True:
                try:
                    date_input = input(f"\n{Fore.CYAN}📅 Purchase Date (optional, format: YYYY-MM-DD, press Enter to skip): {Style.RESET_ALL}").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n👋 Goodbye!")
                    return 0
                
                if date_input.lower() == 'q':
                    print("👋 Goodbye!")
                    return 0
                
                # Allow empty input (skip)
                optional_fields['purchase_date'] = date_input if date_input else None
                break
            
            # Cost (optional)
            while True:
                try:
                    cost_input = input(f"\n{Fore.CYAN}💰 Cost (optional, press Enter to skip): {Style.RESET_ALL}").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n👋 Goodbye!")
                    return 0
                
                if cost_input.lower() == 'q':
                    print("👋 Goodbye!")
                    return 0
                
                # Allow empty input (skip)
                optional_fields['cost'] = cost_input if cost_input else None
                break
            
            # Colour (optional)
            while True:
                try:
                    colour_input = input(f"\n{Fore.CYAN}🎨 Colour (optional, press Enter to skip): {Style.RESET_ALL}").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n👋 Goodbye!")
                    return 0
                
                if colour_input.lower() == 'q':
                    print("👋 Goodbye!")
                    return 0
                
                # Allow empty input (skip)
                optional_fields['colour'] = colour_input if colour_input else None
                break
            
            # Supplier (optional)
            supplier_choice = None
            try:
                print_info("🏢 Loading available suppliers...")
                suppliers = asset_manager.list_suppliers()
                
                if suppliers:
                    print(f"\n{Fore.BLUE}Available suppliers:{Style.RESET_ALL}")
                    for i, supplier in enumerate(suppliers, 1):
                        print(f"  {i}. {supplier['name']}")
                    print(f"  {len(suppliers) + 1}. Enter a new supplier name")
                    print(f"  {Fore.YELLOW}s. Skip supplier{Style.RESET_ALL}")
                    print(f"  {Fore.YELLOW}q. Quit{Style.RESET_ALL}")
                    
                    while True:
                        try:
                            choice = input(f"\n{Fore.CYAN}Choose a supplier [1-{len(suppliers) + 1}], 's' to skip, or 'q': {Style.RESET_ALL}").strip()
                        except (EOFError, KeyboardInterrupt):
                            print("\n👋 Goodbye!")
                            return 0
                            
                        if choice.lower() == 'q':
                            print("👋 Goodbye!")
                            return 0
                        elif choice.lower() == 's':
                            supplier_choice = None
                            break
                        
                        # Check if it's a direct supplier name match first
                        supplier_names = [s['name'] for s in suppliers]
                        if choice in supplier_names:
                            supplier_choice = choice
                            break
                            
                        # Try numeric selection
                        try:
                            choice_num = int(choice)
                            if 1 <= choice_num <= len(suppliers):
                                supplier_choice = suppliers[choice_num - 1]['name']
                                break
                            elif choice_num == len(suppliers) + 1:
                                # Custom supplier
                                while True:
                                    try:
                                        supplier_choice = input(f"{Fore.CYAN}🏢 Enter supplier name (will be created if new, or 's' to skip): {Style.RESET_ALL}").strip()
                                    except (EOFError, KeyboardInterrupt):
                                        print("\n👋 Goodbye!")
                                        return 0
                                        
                                    if supplier_choice.lower() == 's':
                                        supplier_choice = None
                                        break
                                    elif supplier_choice.lower() == 'q':
                                        print("👋 Goodbye!")
                                        return 0
                                        
                                    if supplier_choice:
                                        print_info(f"✨ Will use supplier: '{supplier_choice}' (will create if new)")
                                        break
                                    else:
                                        print_error("Supplier name cannot be empty. Use 's' to skip.")
                                break
                            else:
                                print_error(f"Please enter a number between 1 and {len(suppliers) + 1}.")
                        except ValueError:
                            print_error("Please enter a valid number, supplier name, 's' to skip, or 'q' to quit.")
                else:
                    print_warning("No suppliers found. Supplier field will be skipped.")
                    supplier_choice = None
                    
            except Exception as e:
                print_error(f"Error loading suppliers: {e}")
                print_warning("Supplier field will be skipped.")
                supplier_choice = None
            
            optional_fields['supplier'] = supplier_choice
            
            # 6. Attempt to create the asset
            print_info("🔧 Creating asset...")
            try:
                result = asset_manager.create_asset(
                    serial=serial,
                    model_name=model_name,
                    status=status_name,
                    is_remote=is_remote,
                    invoice_number=optional_fields.get('invoice_number'),
                    purchase_date=optional_fields.get('purchase_date'),
                    cost=optional_fields.get('cost'),
                    colour=optional_fields.get('colour'),
                    supplier=optional_fields.get('supplier')
                )
                
                if result.get('success'):
                    object_key = result.get('object_key', 'Unknown')
                    print_success(f"Created asset {object_key}!")
                    print(f"   Model: {model_name}")
                    print(f"   Serial: {serial}")
                    print(f"   Status: {status_name}")
                    print(f"   Remote: {'Yes' if is_remote else 'No'}")
                    
                    # Show optional fields if provided
                    if optional_fields.get('invoice_number'):
                        print(f"   Invoice: {optional_fields['invoice_number']}")
                    if optional_fields.get('purchase_date'):
                        print(f"   Purchase Date: {optional_fields['purchase_date']}")
                    if optional_fields.get('cost'):
                        print(f"   Cost: {optional_fields['cost']}")
                    if optional_fields.get('colour'):
                        print(f"   Colour: {optional_fields['colour']}")
                    if optional_fields.get('supplier'):
                        print(f"   Supplier: {optional_fields['supplier']}")
                else:
                    error_msg = result.get('error', 'Unknown error')
                    print_error(f"Failed to create asset: {error_msg}")
                    
                    # Offer guidance based on error type
                    if 'already exists' in error_msg.lower() or 'duplicate' in error_msg.lower():
                        print_warning("💡 Try scanning a different serial number.")
                    elif 'permission' in error_msg.lower():
                        print_warning("💡 Check your Jira Service Management permissions for Assets.")
                    elif 'invalid status' in error_msg.lower():
                        print_warning("💡 The status selection may be invalid. Try a different status.")
                    elif 'unauthorized' in error_msg.lower() or '401' in error_msg:
                        print_warning("💡 Check your API credentials and AUTH_METHOD in .env file.")
                    elif 'forbidden' in error_msg.lower() or '403' in error_msg:
                        print_warning("💡 Check your JSM Assets permissions.")
                        
            except KeyboardInterrupt:
                print("\n🛑 Asset creation interrupted!")
                return 0
            except Exception as e:
                print_error(f"Unexpected error creating asset: {e}")
                
            # 6. Ask if user wants to add another asset
            print()
            while True:
                try:
                    continue_input = input(f"{Fore.CYAN}➕ Add another asset? (y/n): {Style.RESET_ALL}").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("\n👋 Thanks for using the asset creation workflow!")
                    return 0
                    
                if continue_input in ['y', 'yes']:
                    print(f"\n{Fore.MAGENTA}{'=' * 50}{Style.RESET_ALL}")
                    break  # Continue outer loop
                elif continue_input in ['n', 'no', 'q']:
                    print_success("👋 Thanks for using the asset creation workflow!")
                    return 0  # Exit function
                else:
                    print_error("Please enter 'y' for yes or 'n' for no.")
                    
    except KeyboardInterrupt:
        print(f"\n\n{Fore.RED}🛑 Asset creation workflow interrupted. Goodbye!{Style.RESET_ALL}")
        return 0
    except Exception as e:
        print_error(f"Unexpected error in workflow: {e}")
        return 1


def main():
    """Main application entry point."""
    print_banner()
    
    # Parse arguments
    parser = setup_argument_parser()
    args = parser.parse_args()
    
    # Set up logging
    try:
        logger = setup_logging()
        
        # Adjust logging level based on arguments
        if args.verbose:
            logger.setLevel('DEBUG')
        elif args.quiet:
            logger.setLevel('ERROR')
        
    except Exception as e:
        print_error(f"Failed to set up logging: {e}")
        return 1
    
    # Validate environment
    if not validate_environment():
        return 1
    
    # Determine dry run mode
    dry_run = not args.execute  # If --execute is specified, dry_run = False, otherwise True
    if args.execute:
        print_warning("EXECUTE mode enabled - changes will be applied!")
        print_info("To preview changes first, use --dry-run")
    else:
        print_info("DRY RUN mode - no changes will be applied")
    
    print()
    
    # Initialize asset manager
    try:
        asset_manager = AssetManager()
        
        # Clear cache if requested
        if args.clear_cache:
            print_info("Clearing all caches...")
            asset_manager.clear_caches()
        
    except Exception as e:
        print_error(f"Failed to initialize Asset Manager: {e}")
        return 1
    
    # Execute requested operation
    try:
        if args.test_asset:
            # Test single asset
            result = test_single_asset(asset_manager, args.test_asset, dry_run)
            
            if result.get('success'):
                if not dry_run and result.get('updated'):
                    print_success("Asset updated successfully!")
                elif dry_run:
                    print_info("Test completed successfully (dry run)")
                return 0
            else:
                return 1
                
        elif args.bulk:
            # Bulk processing
            results = process_bulk_assets(asset_manager, dry_run, args.batch_size)
            
            if results:
                summary = asset_manager.get_processing_summary(results)
                if summary.get('errors', 0) == 0:
                    print_success("Bulk processing completed successfully!")
                    return 0
                else:
                    print_warning("Bulk processing completed with some errors")
                    return 1
            else:
                print_error("Bulk processing failed")
                return 1
        
        elif args.retire_assets:
            # Asset retirement processing
            results = process_asset_retirements(asset_manager, dry_run, args.batch_size)
            
            if results:
                summary = asset_manager.get_processing_summary(results)
                if summary.get('errors', 0) == 0:
                    print_success("Asset retirement processing completed successfully!")
                    return 0
                else:
                    print_warning("Asset retirement processing completed with some errors")
                    return 1
            else:
                print_error("Asset retirement processing failed")
                return 1
                
        elif args.oauth_setup:
            # OAuth 2.0 setup
            if setup_oauth_authentication():
                print_success("OAuth setup completed successfully!")
                return 0
            else:
                return 1
                
        elif args.new:
            # Interactive new asset creation
            return run_new_asset_workflow(asset_manager)
                
        elif args.csv_migrate:
            # CSV-based asset migration
            if not validate_csv_migration_args(args):
                return 1
                
            results = process_csv_migration(
                asset_manager, args.csv, args.from_type_id, args.to_type_id, dry_run, args.delete_original
            )
            
            if results:
                summary = asset_manager.get_processing_summary(results)
                if summary.get('errors', 0) == 0:
                    if dry_run:
                        print_success("CSV migration preview completed successfully!")
                        print_info("Use --execute to perform the actual migration")
                    else:
                        print_success("CSV migration completed successfully!")
                    return 0
                else:
                    print_warning("CSV migration completed with some errors")
                    return 1
            else:
                print_error("CSV migration failed")
                return 1
                
        elif args.cache_info:
            # Show cache information
            if show_cache_info(asset_manager):
                return 0
            else:
                return 1
                
        elif args.cache_cleanup:
            # Clean up expired cache files
            if cleanup_cache(asset_manager):
                return 0
            else:
                return 1
                
    except KeyboardInterrupt:
        print_warning("\\nOperation cancelled by user")
        return 130
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return 1
    
    return 0


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
