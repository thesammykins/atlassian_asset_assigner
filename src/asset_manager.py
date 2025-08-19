"""
Asset Manager

This module provides high-level functionality for managing Jira Assets,
including attribute extraction, user email to accountId mapping,
and attribute updates with validation.
"""

import logging
import json
from typing import Dict, List, Optional, Any, Union, Tuple
from datetime import datetime

from config import config
from jira_user_client import JiraUserClient, UserNotFoundError, MultipleUsersFoundError, JiraUserAPIError
from jira_assets_client import (
    JiraAssetsClient, 
    AssetNotFoundError, 
    SchemaNotFoundError, 
    ObjectTypeNotFoundError,
    AttributeNotFoundError,
    JiraAssetsAPIError
)


class AssetUpdateError(Exception):
    """Raised when an asset update fails."""
    pass


class ValidationError(Exception):
    """Raised when validation fails."""
    pass


class AssetManager:
    """High-level asset management functionality."""
    
    def __init__(self):
        """Initialize the Asset Manager."""
        self.user_client = JiraUserClient()
        self.assets_client = JiraAssetsClient()
        self.logger = logging.getLogger('jira_assets_manager.asset_manager')
        
        # Configuration
        self.hardware_schema_name = config.hardware_schema_name
        self.laptops_object_schema_name = config.laptops_object_schema_name
        self.user_email_attribute = config.user_email_attribute
        self.assignee_attribute = config.assignee_attribute
        
        self.logger.info("Initialized Asset Manager")
    
    def get_hardware_schema(self) -> Dict[str, Any]:
        """
        Get the Hardware schema information.
        
        Returns:
            Schema information
            
        Raises:
            SchemaNotFoundError: If Hardware schema is not found
        """
        return self.assets_client.get_schema_by_name(self.hardware_schema_name)
    
    def get_laptops_object_type(self) -> Dict[str, Any]:
        """
        Get the Laptops object type within the Hardware schema.
        
        Returns:
            Object type information
            
        Raises:
            SchemaNotFoundError: If Hardware schema is not found
            ObjectTypeNotFoundError: If Laptops object type is not found
        """
        hardware_schema = self.get_hardware_schema()
        schema_id = hardware_schema['id']
        
        return self.assets_client.get_object_type_by_name(schema_id, self.laptops_object_schema_name)
    
    def extract_user_email(self, asset_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract the user email attribute from an asset.
        
        Args:
            asset_data: The asset data from the Assets API
            
        Returns:
            User email address or None if not found
        """
        email = self.assets_client.extract_attribute_value(asset_data, self.user_email_attribute)
        
        if email:
            # Normalize email for consistent processing
            email = str(email).strip().lower()
            self.logger.debug(f"Extracted user email: {email}")
            return email
        
        self.logger.debug(f"No user email found in asset {asset_data.get('objectKey', 'unknown')}")
        return None
    
    def extract_current_assignee(self, asset_data: Dict[str, Any]) -> Optional[str]:
        """
        Extract the current assignee attribute from an asset.
        
        Args:
            asset_data: The asset data from the Assets API
            
        Returns:
            Current assignee or None if not found
        """
        assignee = self.assets_client.extract_attribute_value(asset_data, self.assignee_attribute)
        
        if assignee:
            self.logger.debug(f"Current assignee: {assignee}")
            return str(assignee)
        
        self.logger.debug(f"No assignee found in asset {asset_data.get('objectKey', 'unknown')}")
        return None
    
    def lookup_user_account_id(self, email: str) -> str:
        """
        Look up a Jira user's accountId by email address.
        
        Args:
            email: The user's email address
            
        Returns:
            The user's accountId
            
        Raises:
            UserNotFoundError: If user is not found
            MultipleUsersFoundError: If multiple users are found
            JiraUserAPIError: For other API errors
        """
        self.logger.info(f"Looking up accountId for email: {email}")
        
        try:
            account_id = self.user_client.get_account_id_by_email(email)
            self.logger.info(f"Found accountId {account_id} for email {email}")
            return account_id
            
        except (UserNotFoundError, MultipleUsersFoundError) as e:
            self.logger.warning(f"Failed to lookup user for email {email}: {e}")
            raise
        except JiraUserAPIError as e:
            self.logger.error(f"API error looking up user for email {email}: {e}")
            raise
    
    def validate_account_id(self, account_id: str) -> bool:
        """
        Validate that an accountId exists and is active.
        
        Args:
            account_id: The accountId to validate
            
        Returns:
            True if valid and active, False otherwise
        """
        return self.user_client.validate_account_id(account_id)
    
    def create_assignee_update(self, asset_data: Dict[str, Any], account_id: str) -> Dict[str, Any]:
        """
        Create an attribute update to set the assignee.
        
        Args:
            asset_data: The asset data
            account_id: The new assignee's accountId
            
        Returns:
            Attribute update structure
            
        Raises:
            AttributeNotFoundError: If assignee attribute is not found
        """
        object_type_id = asset_data['objectType']['id']
        
        return self.assets_client.create_attribute_update(
            self.assignee_attribute,
            account_id,
            object_type_id
        )
    
    def process_asset(self, object_key: str, dry_run: bool = False) -> Dict[str, Any]:
        """
        Process a single asset: extract email, lookup user, and update assignee.
        
        Args:
            object_key: The asset object key (e.g., HW-459)
            dry_run: If True, don't actually update the asset
            
        Returns:
            Dictionary with processing results
            
        Raises:
            AssetNotFoundError: If asset is not found
            ValidationError: If validation fails
            AssetUpdateError: If update fails
        """
        self.logger.info(f"Processing asset {object_key} (dry_run={dry_run})")
        
        result = {
            'object_key': object_key,
            'success': False,
            'dry_run': dry_run,
            'user_email': None,
            'account_id': None,
            'current_assignee': None,
            'new_assignee': None,
            'updated': False,
            'skipped': False,
            'skip_reason': None,
            'error': None,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            # 1. Fetch asset details
            self.logger.info(f"Step 1: Fetching asset {object_key}")
            asset_data = self.assets_client.get_object_by_key(object_key)
            
            # 2. Extract user email
            self.logger.info(f"Step 2: Extracting user email from {object_key}")
            user_email = self.extract_user_email(asset_data)
            result['user_email'] = user_email
            
            if not user_email:
                result['skipped'] = True
                result['skip_reason'] = f"No '{self.user_email_attribute}' attribute found"
                self.logger.warning(f"Skipping {object_key}: {result['skip_reason']}")
                return result
            
            # 3. Extract current assignee
            current_assignee = self.extract_current_assignee(asset_data)
            result['current_assignee'] = current_assignee
            
            # 4. Look up Jira user by email
            self.logger.info(f"Step 3: Looking up Jira user for email: {user_email}")
            try:
                account_id = self.lookup_user_account_id(user_email)
                result['account_id'] = account_id
            except (UserNotFoundError, MultipleUsersFoundError) as e:
                result['skipped'] = True
                result['skip_reason'] = f"User lookup failed: {str(e)}"
                self.logger.warning(f"Skipping {object_key}: {result['skip_reason']}")
                return result
            
            # 5. Validate accountId
            if not self.validate_account_id(account_id):
                result['skipped'] = True
                result['skip_reason'] = f"AccountId {account_id} is invalid or inactive"
                self.logger.warning(f"Skipping {object_key}: {result['skip_reason']}")
                return result
            
            # 6. Check if update is needed
            if current_assignee == account_id:
                result['skipped'] = True
                result['skip_reason'] = f"Assignee already set to {account_id}"
                self.logger.info(f"Skipping {object_key}: {result['skip_reason']}")
                return result
            
            result['new_assignee'] = account_id
            
            # 7. Update assignee (unless dry run)
            if not dry_run:
                self.logger.info(f"Step 4: Updating assignee for {object_key} to {account_id}")
                
                attribute_update = self.create_assignee_update(asset_data, account_id)
                object_id = asset_data['id']
                
                updated_asset = self.assets_client.update_object(object_id, [attribute_update])
                result['updated'] = True
                
                # Verify the update - for user attributes, we need to check if update was successful
                # rather than comparing exact values as Assets API returns display names
                updated_assignee = self.assets_client.extract_attribute_value(updated_asset, self.assignee_attribute)
                if updated_assignee is None:
                    raise AssetUpdateError(f"Update verification failed: assignee is still None after update")
                
                self.logger.info(f"Successfully updated {object_key} assignee from '{current_assignee}' to '{account_id}' (displays as: {updated_assignee})")
            else:
                self.logger.info(f"Dry run: Would update {object_key} assignee from '{current_assignee}' to '{account_id}'")
            
            result['success'] = True
            return result
            
        except AssetNotFoundError as e:
            error_msg = f"Asset {object_key} not found: {e}"
            result['error'] = error_msg
            self.logger.error(error_msg)
            raise
            
        except (ValidationError, AssetUpdateError) as e:
            error_msg = f"Failed to process {object_key}: {e}"
            result['error'] = error_msg
            self.logger.error(error_msg)
            raise
            
        except Exception as e:
            error_msg = f"Unexpected error processing {object_key}: {e}"
            result['error'] = error_msg
            self.logger.error(error_msg, exc_info=True)
            raise AssetUpdateError(error_msg)
    
    def get_hardware_laptops_objects(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get all objects from the Hardware schema's Laptops object type.
        
        Args:
            limit: Maximum number of objects to retrieve per query
            
        Returns:
            List of asset objects
            
        Raises:
            SchemaNotFoundError: If Hardware schema is not found
            ObjectTypeNotFoundError: If Laptops object type is not found
            JiraAssetsAPIError: For other API errors
        """
        self.logger.info(f"Retrieving all {self.laptops_object_schema_name} objects from {self.hardware_schema_name} schema")
        
        laptops_object_type = self.get_laptops_object_type()
        object_type_id = laptops_object_type['id']
        
        # Use AQL to find all objects of this type
        aql_query = f'objectType = \"{self.laptops_object_schema_name}\"'
        
        all_objects = []
        start = 0
        
        while True:
            self.logger.debug(f"Fetching objects {start} to {start + limit}")
            
            result = self.assets_client.find_objects_by_aql(aql_query, start=start, limit=limit)
            objects = result.get('values', [])
            
            if not objects:
                break
            
            all_objects.extend(objects)
            
            # Check if there are more results
            if len(objects) < limit:
                break
            
            start += limit
        
        self.logger.info(f"Retrieved {len(all_objects)} {self.laptops_object_schema_name} objects")
        return all_objects
    
    def filter_objects_for_processing(self, objects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter objects to only those that should be processed.
        
        Args:
            objects: List of asset objects from AQL (may have incomplete attributes)
            
        Returns:
            Filtered list of objects that have user email but no assignee
        """
        filtered_objects = []
        
        # AQL responses don't always include complete attributes, so we need to
        # fetch individual objects to properly check attributes
        self.logger.info(f"Checking {len(objects)} objects for processing criteria...")
        
        for i, obj in enumerate(objects):
            object_key = obj.get('objectKey', 'unknown')
            
            try:
                # Fetch the complete object data with all attributes
                complete_obj = self.assets_client.get_object_by_key(object_key)
                
                # Check if object has user email
                user_email = self.extract_user_email(complete_obj)
                if not user_email:
                    self.logger.debug(f"Skipping {object_key}: no user email")
                    continue
                
                # Check if object already has assignee
                current_assignee = self.extract_current_assignee(complete_obj)
                if current_assignee:
                    self.logger.debug(f"Skipping {object_key}: already has assignee '{current_assignee}'")
                    continue
                
                # This object needs processing - add the complete object data
                filtered_objects.append(complete_obj)
                self.logger.debug(f"Added {object_key} for processing (User Email: {user_email}, Current Assignee: {current_assignee})")
                
            except Exception as e:
                self.logger.warning(f"Error checking {object_key} for processing: {e}")
                continue
            
            # Progress indicator for large datasets
            if (i + 1) % 50 == 0:
                self.logger.info(f"Checked {i + 1}/{len(objects)} objects, found {len(filtered_objects)} for processing")
        
        self.logger.info(f"Filtered {len(filtered_objects)} objects for processing from {len(objects)} total")
        return filtered_objects
    
    def get_processing_summary(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate a summary of processing results.
        
        Args:
            results: List of processing results
            
        Returns:
            Summary statistics
        """
        total = len(results)
        successful = sum(1 for r in results if r['success'])
        updated = sum(1 for r in results if r['updated'])
        skipped = sum(1 for r in results if r['skipped'])
        errors = sum(1 for r in results if r.get('error'))
        
        # Group skip reasons
        skip_reasons = {}
        for r in results:
            if r['skipped'] and r['skip_reason']:
                reason = r['skip_reason']
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
        
        # Group errors
        error_types = {}
        for r in results:
            if r.get('error'):
                error = str(r['error'])
                # Simplify error message for grouping
                if 'not found' in error.lower():
                    error_type = 'Not Found'
                elif 'permission' in error.lower() or 'denied' in error.lower():
                    error_type = 'Permission Denied'
                elif 'rate limit' in error.lower():
                    error_type = 'Rate Limited'
                else:
                    error_type = 'Other Error'
                
                error_types[error_type] = error_types.get(error_type, 0) + 1
        
        summary = {
            'total_processed': total,
            'successful': successful,
            'updated': updated,
            'skipped': skipped,
            'errors': errors,
            'success_rate': (successful / total * 100) if total > 0 else 0,
            'skip_reasons': skip_reasons,
            'error_types': error_types,
            'timestamp': datetime.now().isoformat()
        }
        
        return summary
    
    def clear_caches(self):
        """Clear all caches."""
        self.logger.info("Clearing all caches")
        self.user_client.clear_cache()
        self.assets_client.clear_cache()
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics from all clients.
        
        Returns:
            Combined cache statistics
        """
        user_stats = self.user_client.get_cache_stats()
        assets_stats = self.assets_client.get_cache_stats()
        
        return {
            'user_client': user_stats,
            'assets_client': assets_stats
        }
