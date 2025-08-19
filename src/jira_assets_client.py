"""
Jira Assets API Client

This module provides functionality for interacting with Jira's Assets API,
including object retrieval, attribute manipulation, and bulk operations.

Based on the Jira Service Management Assets REST API
Reference: https://developer.atlassian.com/cloud/assets/rest/api-group-object/
"""

import logging
import time
import json
from typing import Dict, List, Optional, Any, Union
import requests
from urllib.parse import quote

from config import config
from oauth_client import OAuthClient, TokenError


class JiraAssetsAPIError(Exception):
    """Base exception for Jira Assets API errors."""
    pass


class AssetNotFoundError(JiraAssetsAPIError):
    """Raised when an asset is not found."""
    pass


class SchemaNotFoundError(JiraAssetsAPIError):
    """Raised when a schema is not found."""
    pass


class ObjectTypeNotFoundError(JiraAssetsAPIError):
    """Raised when an object type is not found."""
    pass


class AttributeNotFoundError(JiraAssetsAPIError):
    """Raised when an attribute is not found."""
    pass


class JiraAssetsClient:
    """Client for interacting with Jira Assets API."""
    
    def __init__(self):
        """Initialize the Jira Assets API client."""
        self.base_url = config.jira_base_url
        self.workspace_id = config.assets_workspace_id
        
        # Assets API uses site-specific routing through api.atlassian.com
        # We'll set the site_id after OAuth authentication
        self.site_id = None
        self.assets_base_url = None
        
        self.session = requests.Session()
        
        # Initialize authentication based on configuration
        if config.auth_method == 'oauth':
            self.oauth_client = OAuthClient()
            self.logger = logging.getLogger('jira_assets_manager.assets_client')
            self._setup_oauth_auth()
        else:
            self.oauth_client = None
            self.session.auth = config.get_basic_auth()
            self.logger = logging.getLogger('jira_assets_manager.assets_client')
        
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 60.0 / config.max_requests_per_minute
        
        # Schema and Object Type caching
        self.schema_cache: Dict[str, Dict[str, Any]] = {}
        self.object_type_cache: Dict[str, Dict[str, Any]] = {}
        self.attribute_cache: Dict[str, List[Dict[str, Any]]] = {}
        
        self.logger = logging.getLogger('jira_assets_manager.assets_client')
        
        self.logger.info(f"Initialized Jira Assets Client for workspace {self.workspace_id}")
    
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
                        # Set the correct Assets API base URL
                        self.assets_base_url = f"https://api.atlassian.com/ex/jira/{self.site_id}/jsm/assets/workspace/{self.workspace_id}/v1"
                        self.logger.info(f"Discovered site ID: {self.site_id}")
                        return
                
                self.logger.error(f"Site not found in accessible resources for {self.base_url}")
            else:
                self.logger.error(f"Failed to get accessible resources: {response.status_code}")
        
        except Exception as e:
            self.logger.error(f"Failed to discover site ID: {e}")
            # Fallback to the old endpoint structure (will likely fail)
            self.assets_base_url = f"{self.base_url}/gateway/api/jsm/assets/workspace/{self.workspace_id}/v1"
    
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
                raise JiraAssetsAPIError(f"OAuth authentication failed: {e}")
    
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
            JiraAssetsAPIError: For various API errors
        """
        # Log response for debugging
        self.logger.debug(f"Assets API Response [{context}]: {response.status_code} - {response.text[:500]}")
        
        # Check for rate limiting
        if response.status_code == 429:
            retry_after = response.headers.get('Retry-After', '60')
            self.logger.warning(f"Rate limit exceeded. Retry after {retry_after} seconds")
            raise JiraAssetsAPIError(f"Rate limit exceeded. Retry after {retry_after} seconds")
        
        # Check for authentication issues
        if response.status_code == 401:
            error_msg = f"Authentication failed [{context}]: Check API credentials"
            self.logger.error(error_msg)
            raise JiraAssetsAPIError(error_msg)
        
        # Check for permission issues
        if response.status_code == 403:
            error_msg = f"Permission denied [{context}]: Check Assets API scopes and permissions"
            self.logger.error(error_msg)
            raise JiraAssetsAPIError(error_msg)
        
        # Check for not found
        if response.status_code == 404:
            if "object" in context.lower():
                raise AssetNotFoundError(f"Asset not found [{context}]")
            elif "schema" in context.lower():
                raise SchemaNotFoundError(f"Schema not found [{context}]")
            elif "objecttype" in context.lower():
                raise ObjectTypeNotFoundError(f"Object type not found [{context}]")
            else:
                raise JiraAssetsAPIError(f"Resource not found [{context}]: {response.text}")
        
        if not response.ok:
            error_msg = f"Assets API request failed [{context}]: {response.status_code} - {response.text}"
            self.logger.error(error_msg)
            raise JiraAssetsAPIError(error_msg)
        
        try:
            return response.json()
        except ValueError as e:
            error_msg = f"Failed to parse JSON response [{context}]: {e}"
            self.logger.error(error_msg)
            raise JiraAssetsAPIError(error_msg)
    
    def get_object_schemas(self) -> List[Dict[str, Any]]:
        """
        Get all object schemas in the Assets workspace.
        
        Returns:
            List of object schema information
            
        Raises:
            JiraAssetsAPIError: For API errors
        """
        self.logger.info("Retrieving object schemas")
        
        # Refresh OAuth headers before making the request
        if self.oauth_client:
            self._refresh_oauth_headers()
        
        self._rate_limit()
        
        url = f"{self.assets_base_url}/objectschema/list?maxResults=50"
        
        try:
            response = self.session.get(url)
            data = self._handle_response(response, "get object schemas")
            
            # Cache schemas for later use
            schemas = data.get('values', [])
            for schema in schemas:
                self.schema_cache[schema['name']] = schema
            
            self.logger.info(f"Retrieved {len(schemas)} object schemas")
            return schemas
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error while retrieving schemas: {e}"
            self.logger.error(error_msg)
            raise JiraAssetsAPIError(error_msg)
    
    def get_schema_by_name(self, schema_name: str) -> Dict[str, Any]:
        """
        Get an object schema by name.
        
        Args:
            schema_name: Name of the schema to retrieve
            
        Returns:
            Schema information
            
        Raises:
            SchemaNotFoundError: If schema is not found
            JiraAssetsAPIError: For other API errors
        """
        # Check cache first
        if schema_name in self.schema_cache:
            self.logger.debug(f"Using cached schema for {schema_name}")
            return self.schema_cache[schema_name]
        
        # Fetch all schemas if not cached
        schemas = self.get_object_schemas()
        
        for schema in schemas:
            if schema['name'] == schema_name:
                return schema
        
        raise SchemaNotFoundError(f"Schema '{schema_name}' not found")
    
    def get_object_types(self, schema_id: int) -> List[Dict[str, Any]]:
        """
        Get all object types for a given schema.
        
        Args:
            schema_id: The schema ID
            
        Returns:
            List of object types
            
        Raises:
            JiraAssetsAPIError: For API errors
        """
        self.logger.info(f"Retrieving object types for schema {schema_id}")
        
        self._rate_limit()
        
        url = f"{self.assets_base_url}/objectschema/{schema_id}/objecttypes"
        
        try:
            response = self.session.get(url)
            data = self._handle_response(response, f"get object types for schema {schema_id}")
            
            # Handle both list and dict responses
            if isinstance(data, list):
                object_types = data
            else:
                object_types = data.get('values', [])
            
            # Cache object types
            for obj_type in object_types:
                cache_key = f"{schema_id}:{obj_type['name']}"
                self.object_type_cache[cache_key] = obj_type
            
            self.logger.info(f"Retrieved {len(object_types)} object types for schema {schema_id}")
            return object_types
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error while retrieving object types: {e}"
            self.logger.error(error_msg)
            raise JiraAssetsAPIError(error_msg)
    
    def get_object_type_by_name(self, schema_id: int, object_type_name: str) -> Dict[str, Any]:
        """
        Get an object type by name within a schema.
        
        Args:
            schema_id: The schema ID
            object_type_name: Name of the object type
            
        Returns:
            Object type information
            
        Raises:
            ObjectTypeNotFoundError: If object type is not found
            JiraAssetsAPIError: For other API errors
        """
        cache_key = f"{schema_id}:{object_type_name}"
        
        # Check cache first
        if cache_key in self.object_type_cache:
            self.logger.debug(f"Using cached object type for {object_type_name}")
            return self.object_type_cache[cache_key]
        
        # Fetch all object types if not cached
        object_types = self.get_object_types(schema_id)
        
        for obj_type in object_types:
            if obj_type['name'] == object_type_name:
                return obj_type
        
        raise ObjectTypeNotFoundError(f"Object type '{object_type_name}' not found in schema {schema_id}")
    
    def get_object_attributes(self, object_type_id: int) -> List[Dict[str, Any]]:
        """
        Get all attributes for a given object type.
        
        Args:
            object_type_id: The object type ID
            
        Returns:
            List of attributes
            
        Raises:
            JiraAssetsAPIError: For API errors
        """
        # Check cache first
        if str(object_type_id) in self.attribute_cache:
            self.logger.debug(f"Using cached attributes for object type {object_type_id}")
            return self.attribute_cache[str(object_type_id)]
        
        self.logger.info(f"Retrieving attributes for object type {object_type_id}")
        
        self._rate_limit()
        
        url = f"{self.assets_base_url}/objecttype/{object_type_id}/attributes"
        
        try:
            response = self.session.get(url)
            data = self._handle_response(response, f"get attributes for object type {object_type_id}")
            
            # Handle both list and dict responses
            if isinstance(data, list):
                attributes = data
            else:
                attributes = data.get('values', [])
            
            # Cache attributes
            self.attribute_cache[str(object_type_id)] = attributes
            
            self.logger.info(f"Retrieved {len(attributes)} attributes for object type {object_type_id}")
            return attributes
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error while retrieving attributes: {e}"
            self.logger.error(error_msg)
            raise JiraAssetsAPIError(error_msg)
    
    def get_object_by_key(self, object_key: str) -> Dict[str, Any]:
        """
        Get an object by its key (e.g., HW-459).
        
        Args:
            object_key: The object key
            
        Returns:
            Object information including attributes
            
        Raises:
            AssetNotFoundError: If object is not found
            JiraAssetsAPIError: For other API errors
        """
        self.logger.info(f"Retrieving object {object_key}")
        
        self._rate_limit()
        
        url = f"{self.assets_base_url}/object/{object_key}"
        
        try:
            response = self.session.get(url)
            data = self._handle_response(response, f"get object {object_key}")
            
            self.logger.info(f"Retrieved object {object_key}")
            return data
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error while retrieving object {object_key}: {e}"
            self.logger.error(error_msg)
            raise JiraAssetsAPIError(error_msg)
    
    def find_objects_by_aql(self, aql_query: str, start: int = 0, limit: int = 25, include_attributes: bool = True) -> Dict[str, Any]:
        """
        Find objects using Assets Query Language (AQL).
        
        Args:
            aql_query: The AQL query
            start: Starting index for pagination
            limit: Maximum number of results
            include_attributes: Whether to include object attributes in response
            
        Returns:
            Query results with objects and pagination info
            
        Raises:
            JiraAssetsAPIError: For API errors
        """
        self.logger.info(f"Executing AQL query: {aql_query}")
        
        # Refresh OAuth headers before making the request
        if self.oauth_client:
            self._refresh_oauth_headers()
        
        self._rate_limit()
        
        # Use the site-specific AQL endpoint (direct jsm endpoint doesn't work with OAuth)
        aql_url = f"{self.assets_base_url}/object/aql"
        
        # Add query parameters
        params = {
            "startAt": start,
            "maxResults": limit,
            "includeAttributes": str(include_attributes).lower()
        }
        
        # Request payload with correct field name
        payload = {
            "qlQuery": aql_query
        }
        
        try:
            self.logger.debug(f"AQL POST to: {aql_url} with params: {params}")
            self.logger.debug(f"AQL payload: {payload}")
            
            response = self.session.post(aql_url, json=payload, params=params)
            data = self._handle_response(response, f"AQL query: {aql_query}")
            
            # Handle response structure
            if isinstance(data, dict) and 'objectEntries' in data:
                objects = data.get('objectEntries', [])
            elif isinstance(data, list):
                objects = data
            else:
                objects = data.get('values', [])
            
            result_count = len(objects)
            self.logger.info(f"AQL query returned {result_count} objects")
            
            # Return in consistent format
            return {
                'values': objects,
                'total': data.get('totalFilterCount', result_count) if isinstance(data, dict) else result_count,
                'startAt': start,
                'maxResults': limit
            }
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error while executing AQL query: {e}"
            self.logger.error(error_msg)
            raise JiraAssetsAPIError(error_msg)
    
    def update_object(self, object_id: int, attributes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Update an object's attributes.
        
        Args:
            object_id: The object ID to update
            attributes: List of attribute updates
            
        Returns:
            Updated object information
            
        Raises:
            JiraAssetsAPIError: For API errors
        """
        self.logger.info(f"Updating object {object_id} with {len(attributes)} attribute changes")
        
        self._rate_limit()
        
        url = f"{self.assets_base_url}/object/{object_id}"
        
        payload = {
            "attributes": attributes
        }
        
        try:
            response = self.session.put(url, json=payload)
            data = self._handle_response(response, f"update object {object_id}")
            
            self.logger.info(f"Successfully updated object {object_id}")
            return data
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error while updating object {object_id}: {e}"
            self.logger.error(error_msg)
            raise JiraAssetsAPIError(error_msg)
    
    def extract_attribute_value(self, object_data: Dict[str, Any], attribute_name: str) -> Any:
        """
        Extract the value of a specific attribute from an object.
        
        Args:
            object_data: The object data from the API
            attribute_name: Name of the attribute to extract
            
        Returns:
            The attribute value, or None if not found
        """
        attributes = object_data.get('attributes', [])
        
        for attribute in attributes:
            if attribute.get('objectTypeAttribute', {}).get('name') == attribute_name:
                # Handle different attribute value types
                attribute_values = attribute.get('objectAttributeValues', [])
                if not attribute_values:
                    return None
                
                # For simple attributes, return the display value
                if len(attribute_values) == 1:
                    return attribute_values[0].get('displayValue')
                
                # For multi-value attributes, return list
                return [val.get('displayValue') for val in attribute_values]
        
        return None
    
    def create_attribute_update(self, attribute_name: str, value: Any, object_type_id: int) -> Dict[str, Any]:
        """
        Create an attribute update structure.
        
        Args:
            attribute_name: Name of the attribute to update
            value: New value for the attribute
            object_type_id: The object type ID
            
        Returns:
            Attribute update structure
            
        Raises:
            AttributeNotFoundError: If attribute is not found
        """
        # Get attributes for the object type
        attributes = self.get_object_attributes(object_type_id)
        
        # Find the attribute by name
        target_attribute = None
        for attr in attributes:
            if attr['name'] == attribute_name:
                target_attribute = attr
                break
        
        if not target_attribute:
            raise AttributeNotFoundError(f"Attribute '{attribute_name}' not found in object type {object_type_id}")
        
        # Create the update structure
        attribute_update = {
            "objectTypeAttributeId": target_attribute['id'],
            "objectAttributeValues": [
                {
                    "value": str(value)
                }
            ]
        }
        
        return attribute_update
    
    def clear_cache(self):
        """Clear all cached data."""
        self.logger.info("Clearing Assets API cache")
        self.schema_cache.clear()
        self.object_type_cache.clear()
        self.attribute_cache.clear()
    
    def get_cache_stats(self) -> Dict[str, int]:
        """
        Get statistics about the cache.
        
        Returns:
            Dictionary with cache statistics
        """
        return {
            'cached_schemas': len(self.schema_cache),
            'cached_object_types': len(self.object_type_cache),
            'cached_attributes': len(self.attribute_cache)
        }
