#!/usr/bin/env python3
"""
Jira Assets Manager - Main CLI Application

This script manages Jira Assets by extracting user email attributes,
looking up corresponding Jira accountIds, and updating assignee attributes.

Usage:
    python main.py --test-asset HW-459  # Test on specific asset
    python main.py --bulk --dry-run     # Preview bulk operation
    python main.py --bulk               # Execute bulk operation
"""

import sys
import os
import argparse
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import colorama
from colorama import Fore, Style, Back
from tqdm import tqdm

# Add src directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from config import setup_logging, ConfigurationError
import asset_manager
from asset_manager import (
    AssetManager, 
    AssetUpdateError, 
    ValidationError
)
import jira_assets_client
from jira_assets_client import (
    AssetNotFoundError,
    SchemaNotFoundError,
    ObjectTypeNotFoundError,
    JiraAssetsAPIError
)
import jira_user_client
from jira_user_client import (
    UserNotFoundError,
    MultipleUsersFoundError,
    JiraUserAPIError
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


def setup_argument_parser() -> argparse.ArgumentParser:
    """Set up command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Jira Assets Manager - Automate user email to assignee mapping",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --test-asset HW-459              Test on specific asset
  %(prog)s --test-asset HW-459 --execute   Test and execute update
  %(prog)s --bulk --dry-run                Preview bulk operation
  %(prog)s --bulk                          Execute bulk operation
  %(prog)s --bulk --batch-size 5           Process in smaller batches
        """
    )
    
    # Operation modes
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--test-asset',
        metavar='KEY',
        help='Test processing on a specific asset (e.g., HW-459)'
    )
    group.add_argument(
        '--bulk',
        action='store_true',
        help='Process all assets in Hardware/Laptops schema'
    )
    group.add_argument(
        '--oauth-setup',
        action='store_true',
        help='Set up OAuth 2.0 authentication (required for bulk operations with schema access)'
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
            access_token = oauth_client.get_valid_access_token()
            print_success(f"OAuth 2.0 already configured with valid token")
            print_info("You can now use bulk operations that require schema access")
            return True
        except TokenError:
            pass  # Need to authorize
        
        print_info("Starting OAuth 2.0 authorization flow...")
        print("This will open a browser window for you to authorize the application.")
        print()
        
        # Perform authorization
        access_token = oauth_client.authorize()
        
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
                
        elif args.oauth_setup:
            # OAuth 2.0 setup
            if setup_oauth_authentication():
                print_success("OAuth setup completed successfully!")
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
