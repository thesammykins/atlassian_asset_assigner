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

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import colorama
from colorama import Fore, Style
from tqdm import tqdm

# Add src directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from asset_manager import AssetManager, AssetUpdateError, ValidationError
from config import ConfigurationError, setup_logging
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
        batch_size = config.config.batch_size
    
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
        batch_size = config.config.batch_size
    
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
        '--oauth-setup',
        action='store_true',
        help='Set up OAuth 2.0 authentication (required for bulk operations with schema access)'
    )
    group.add_argument(
        '--csv-migrate',
        action='store_true',
        help='Migrate assets between object types using CSV file with SERIAL_NUMBER column'
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
        help=f'Batch size for bulk operations (default: {config.config.batch_size})'
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


def setup_oauth_authentication():
    """Set up OAuth 2.0 authentication interactively."""
    print_info("Setting up OAuth 2.0 authentication for Jira Assets Manager")
    print()
    
    # Check if OAuth is already configured
    if not config.config.is_oauth_configured():
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
        _ = config.config.jira_base_url
        _ = config.config.assets_workspace_id
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
