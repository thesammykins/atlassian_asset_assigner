# 📊 Bulk Data Retrieval and Schema Discovery

This document provides comprehensive technical documentation on how the Jira Assets Manager discovers schema information, validates field structures, and retrieves bulk asset data from Jira Assets.

## Table of Contents

- [Overview](#overview)
- [Authentication Requirements](#authentication-requirements)
- [Schema Discovery Process](#schema-discovery-process)
- [Bulk Data Retrieval](#bulk-data-retrieval)
- [Data Processing Pipeline](#data-processing-pipeline)
- [Caching Mechanisms](#caching-mechanisms)
- [Validation and Error Handling](#validation-and-error-handling)
- [API Endpoints and Rate Limiting](#api-endpoints-and-rate-limiting)
- [Code Examples](#code-examples)
- [Performance Considerations](#performance-considerations)
- [Troubleshooting](#troubleshooting)

## Overview

The Jira Assets Manager implements a sophisticated multi-layered approach to discover, validate, and process asset data at scale. The system automatically discovers schema structures, validates field configurations, and efficiently processes large datasets while respecting API rate limits and maintaining data integrity.

### Key Components

- **Schema Discovery**: Automatic detection and caching of workspace schemas, object types, and attributes
- **Bulk Data Retrieval**: Efficient pagination and AQL-based querying for large datasets
- **Field Validation**: Runtime validation of configured field names against actual schema structures
- **Intelligent Caching**: Multi-level caching to minimize API calls and improve performance
- **Dual Authentication**: Support for both Basic Auth and OAuth 2.0 with different capabilities

## Authentication Requirements

The system's bulk data capabilities are directly tied to the authentication method used:

### Basic Authentication (API Token)
```bash
AUTH_METHOD=basic
JIRA_API_TOKEN=your_api_token_here
```

**Capabilities:**
- ✅ Single asset operations
- ✅ User lookups and validation
- ✅ Asset attribute updates
- ❌ **Schema discovery** (cannot access schema endpoints)
- ❌ **Bulk operations** (requires schema access)

**Limitations:** Basic Auth cannot access the `read:cmdb-schema:jira` scope required for schema discovery endpoints.

### OAuth 2.0 Authentication
```bash
AUTH_METHOD=oauth
OAUTH_CLIENT_ID=your-client-id
OAUTH_CLIENT_SECRET=your-client-secret
OAUTH_SCOPES=read:jira-user read:cmdb-object:jira read:cmdb-schema:jira write:cmdb-object:jira
```

**Capabilities:**
- ✅ All single asset operations
- ✅ **Complete schema discovery**
- ✅ **Bulk operations with schema validation**
- ✅ Advanced filtering and validation
- ✅ Automatic token refresh

**API Routing Differences:**
- **Basic Auth**: `https://domain.atlassian.net/rest/api/3/...`
- **OAuth**: `https://api.atlassian.com/ex/jira/{site_id}/rest/api/3/...`

## Schema Discovery Process

The schema discovery process follows a hierarchical approach to understand the complete structure of your Assets workspace:

### 1. Workspace → Schema Discovery

The system starts by discovering all available schemas in the workspace:

**Code Reference:** [`JiraAssetsClient.get_object_schemas()`](src/jira_assets_client.py#L213-L248)

```python
def get_object_schemas(self) -> List[Dict[str, Any]]:
    """Get all object schemas in the Assets workspace."""
    url = f"{self.assets_base_url}/objectschema/list?maxResults=50"
    response = self.session.get(url)
    schemas = data.get('values', [])
    
    # Cache schemas for later use
    for schema in schemas:
        self.schema_cache[schema['name']] = schema
    
    return schemas
```

**API Endpoint:** `/gateway/api/jsm/assets/workspace/{workspaceId}/v1/objectschema/list`

**Schema Data Structure:**
```json
{
  "id": 1,
  "name": "Hardware",
  "objectSchemaKey": "HW",
  "description": "IT Hardware Assets",
  "status": "Ok",
  "created": "2023-01-15T10:00:00.000Z"
}
```

### 2. Schema → Object Type Discovery

For each schema, the system discovers all available object types:

**Code Reference:** [`JiraAssetsClient.get_object_types()`](src/jira_assets_client.py#L278-L318)

```python
def get_object_types(self, schema_id: int) -> List[Dict[str, Any]]:
    """Get all object types for a given schema."""
    url = f"{self.assets_base_url}/objectschema/{schema_id}/objecttypes"
    response = self.session.get(url)
    
    # Cache object types with composite key
    for obj_type in object_types:
        cache_key = f"{schema_id}:{obj_type['name']}"
        self.object_type_cache[cache_key] = obj_type
    
    return object_types
```

**API Endpoint:** `/gateway/api/jsm/assets/workspace/{workspaceId}/v1/objectschema/{schema_id}/objecttypes`

### 3. Object Type → Attribute Discovery

For each object type, the system discovers all available attributes (fields):

**Code Reference:** [`JiraAssetsClient.get_object_attributes()`](src/jira_assets_client.py#L351-L394)

```python
def get_object_attributes(self, object_type_id: int) -> List[Dict[str, Any]]:
    """Get all attributes for a given object type."""
    url = f"{self.assets_base_url}/objecttype/{object_type_id}/attributes"
    response = self.session.get(url)
    
    # Cache attributes by object type ID
    self.attribute_cache[str(object_type_id)] = attributes
    
    return attributes
```

**API Endpoint:** `/gateway/api/jsm/assets/workspace/{workspaceId}/v1/objecttype/{object_type_id}/attributes`

**Attribute Data Structure:**
```json
{
  "id": 123,
  "name": "User Email",
  "type": {
    "name": "Text",
    "id": 0
  },
  "defaultType": {
    "name": "Text"
  },
  "editable": true,
  "system": false,
  "required": false
}
```

### 4. Schema Hierarchy Overview

```
Workspace
├── Schema: "Hardware" (id: 1)
│   ├── Object Type: "Laptops" (id: 10)
│   │   ├── Attribute: "User Email" (id: 123)
│   │   ├── Attribute: "Assignee" (id: 124)
│   │   ├── Attribute: "Asset Status" (id: 125)
│   │   └── Attribute: "Retirement Date" (id: 126)
│   └── Object Type: "Desktops" (id: 11)
└── Schema: "Software" (id: 2)
    └── Object Type: "Licenses" (id: 20)
```

## Bulk Data Retrieval

The bulk data retrieval process uses AQL (Assets Query Language) to efficiently fetch large datasets:

### 1. AQL Query Construction

**Code Reference:** [`JiraAssetsClient.find_objects_by_aql()`](src/jira_assets_client.py#L428-L496)

The system constructs SQL-like queries to filter assets:

```python
# Basic query for all laptops
aql_query = 'objectType = "Laptops"'

# Advanced filtering
aql_query = 'objectType = "Laptops" AND "User Email" IS NOT EMPTY AND "Assignee" IS EMPTY'

# Retirement processing
aql_query = 'objectType = "Laptops" AND "Retirement Date" IS NOT EMPTY'
```

**AQL Features:**
- SQL-like syntax with `AND`, `OR`, `IS NOT EMPTY` operators
- Object type filtering
- Attribute value filtering
- Date comparisons
- Text pattern matching

### 2. Paginated Data Retrieval

**Code Reference:** [`AssetManager.get_hardware_laptops_objects()`](src/asset_manager.py#L307-L351)

```python
def get_hardware_laptops_objects(self, limit: int = 100) -> List[Dict[str, Any]]:
    """Get all objects from the Hardware schema's Laptops object type."""
    aql_query = f'objectType = "{self.laptops_object_schema_name}"'
    
    all_objects = []
    start = 0
    
    while True:
        result = self.assets_client.find_objects_by_aql(
            aql_query, 
            start=start, 
            limit=limit
        )
        objects = result.get('values', [])
        
        if not objects:
            break
            
        all_objects.extend(objects)
        
        # Check if there are more results
        if len(objects) < limit:
            break
            
        start += limit
    
    return all_objects
```

**Pagination Parameters:**
- `startAt`: Starting index for results (0-based)
- `maxResults`: Maximum number of results per request (default: 100)
- `includeAttributes`: Whether to include object attributes in response

### 3. Complete Object Resolution

AQL responses often contain incomplete attribute data. The system performs individual API calls to get complete object information:

**Code Reference:** [`AssetManager.filter_objects_for_processing()`](src/asset_manager.py#L353-L401)

```python
def filter_objects_for_processing(self, objects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter objects to only those that should be processed."""
    filtered_objects = []
    
    for obj in objects:
        object_key = obj.get('objectKey', 'unknown')
        
        # Fetch the complete object data with all attributes
        complete_obj = self.assets_client.get_object_by_key(object_key)
        
        # Check if object has user email
        user_email = self.extract_user_email(complete_obj)
        if not user_email:
            continue
            
        # Check if object already has assignee
        current_assignee = self.extract_current_assignee(complete_obj)
        if current_assignee:
            continue
            
        # This object needs processing
        filtered_objects.append(complete_obj)
    
    return filtered_objects
```

## Data Processing Pipeline

The complete bulk processing pipeline involves several coordinated steps:

### 1. Schema Discovery and Validation

```python
# Step 1: Discover Hardware schema
hardware_schema = asset_manager.get_hardware_schema()
schema_id = hardware_schema['id']

# Step 2: Get Laptops object type
laptops_object_type = asset_manager.get_laptops_object_type()
object_type_id = laptops_object_type['id']

# Step 3: Discover and cache all attributes for validation
attributes = assets_client.get_object_attributes(object_type_id)
```

### 2. Bulk Asset Query

```python
# Step 4: Fetch all laptop assets using AQL
all_objects = asset_manager.get_hardware_laptops_objects()
```

### 3. Intelligent Filtering

```python
# Step 5: Filter assets that need processing
objects_to_process = asset_manager.filter_objects_for_processing(all_objects)
```

### 4. Batch Processing with Progress Tracking

**Code Reference:** [`main.py - process_bulk_assets()`](src/main.py#L253-L324)

```python
# Step 6: Process assets in batches with progress tracking
progress = ProgressTracker(len(objects_to_process), "Processing assets")

for asset_obj in objects_to_process:
    object_key = asset_obj.get('objectKey')
    
    try:
        result = asset_manager.process_asset(object_key, dry_run=dry_run)
        results.append(result)
        progress.update(result)
        
    except Exception as e:
        error_result = {
            'object_key': object_key,
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }
        results.append(error_result)
        progress.update(error_result)
```

### 5. Result Tracking and Backup

```python
# Step 7: Save detailed results to JSON
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
filename = f"bulk_processing_results_{timestamp}.json"
save_results(results, filename)

# Step 8: Generate processing summary
summary = asset_manager.get_processing_summary(results)
display_summary(summary)
```

## Caching Mechanisms

The system implements a sophisticated multi-level caching strategy to minimize API calls and improve performance:

### 1. Schema-Level Caching

**Code Reference:** [`JiraAssetsClient.__init__()`](src/jira_assets_client.py#L82-L84)

```python
# Schema and Object Type caching
self.schema_cache: Dict[str, Dict[str, Any]] = {}
self.object_type_cache: Dict[str, Dict[str, Any]] = {}
self.attribute_cache: Dict[str, List[Dict[str, Any]]] = {}
```

**Cache Structure:**
- `schema_cache`: `{"Hardware": {schema_data}, "Software": {schema_data}}`
- `object_type_cache`: `{"1:Laptops": {object_type_data}, "1:Desktops": {object_type_data}}`
- `attribute_cache`: `{"10": [attribute_list], "11": [attribute_list]}`

### 2. Cache Hit Example

**Code Reference:** [`JiraAssetsClient.get_schema_by_name()`](src/jira_assets_client.py#L250-L276)

```python
def get_schema_by_name(self, schema_name: str) -> Dict[str, Any]:
    """Get an object schema by name."""
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
```

### 3. User Account Caching

**Code Reference:** [`JiraUserClient`](src/jira_user_client.py)

The system also caches user lookups to avoid repeated API calls:

```python
# Email-to-AccountID mapping cache
self.user_cache: Dict[str, str] = {}

def get_account_id_by_email(self, email: str) -> str:
    # Check cache first
    if email in self.user_cache:
        return self.user_cache[email]
    
    # Perform user search and cache result
    user_info = self.search_user_by_email(email)
    account_id = user_info['accountId']
    self.user_cache[email] = account_id
    
    return account_id
```

### 4. Cache Performance Benefits

**Typical API Call Reduction:**
- **Without Caching**: 1000 assets × 4 API calls = 4000 requests
- **With Caching**: Schema discovery (5-10 calls) + Asset processing (1000 calls) = ~1010 requests
- **Performance Improvement**: ~75% reduction in API calls

### 5. Cache Invalidation

**Manual Cache Clearing:**
```bash
python src/main.py --bulk --clear-cache --execute
```

**Code Reference:** [`AssetManager.clear_caches()`](src/asset_manager.py#L712-L716)

```python
def clear_caches(self):
    """Clear all caches."""
    self.logger.info("Clearing all caches")
    self.user_client.clear_cache()
    self.assets_client.clear_cache()
```

## Validation and Error Handling

The system implements comprehensive validation at multiple levels:

### 1. Schema Validation

**Code Reference:** [`JiraAssetsClient.create_attribute_update()`](src/jira_assets_client.py#L563-L601)

```python
def create_attribute_update(self, attribute_name: str, value: Any, object_type_id: int) -> Dict[str, Any]:
    """Create an attribute update structure."""
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
    return {
        "objectTypeAttributeId": target_attribute['id'],
        "objectAttributeValues": [{"value": str(value)}]
    }
```

### 2. Data Validation During Processing

**Code Reference:** [`AssetManager.process_asset()`](src/asset_manager.py#L186-L305)

```python
# Extract and validate user email
user_email = self.extract_user_email(asset_data)
if not user_email:
    result['skipped'] = True
    result['skip_reason'] = f"No '{self.user_email_attribute}' attribute found"
    return result

# Validate user account exists
try:
    account_id = self.lookup_user_account_id(user_email)
except (UserNotFoundError, MultipleUsersFoundError) as e:
    result['skipped'] = True
    result['skip_reason'] = f"User lookup failed: {str(e)}"
    return result

# Validate accountId is active
if not self.validate_account_id(account_id):
    result['skipped'] = True
    result['skip_reason'] = f"AccountId {account_id} is invalid or inactive"
    return result

# Check if update is needed
if current_assignee == account_id:
    result['skipped'] = True
    result['skip_reason'] = f"Assignee already set to {account_id}"
    return result
```

### 3. Error Recovery Strategies

**Rate Limiting Handling:**
**Code Reference:** [`JiraAssetsClient._handle_response()`](src/jira_assets_client.py#L155-L211)

```python
# Check for rate limiting
if response.status_code == 429:
    retry_after = response.headers.get('Retry-After', '60')
    self.logger.warning(f"Rate limit exceeded. Retry after {retry_after} seconds")
    raise JiraAssetsAPIError(f"Rate limit exceeded. Retry after {retry_after} seconds")
```

**Authentication Error Handling:**
```python
# Check for authentication issues
if response.status_code == 401:
    error_msg = f"Authentication failed [{context}]: Check API credentials"
    self.logger.error(error_msg)
    raise JiraAssetsAPIError(error_msg)
```

### 4. Result Tracking and Reporting

**Code Reference:** [`AssetManager.get_processing_summary()`](src/asset_manager.py#L658-L710)

```python
def get_processing_summary(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate a summary of processing results."""
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
    
    return {
        'total_processed': total,
        'successful': successful,
        'updated': updated,
        'skipped': skipped,
        'errors': errors,
        'success_rate': (successful / total * 100) if total > 0 else 0,
        'skip_reasons': skip_reasons,
        'error_types': error_types
    }
```

## API Endpoints and Rate Limiting

### Primary API Endpoints Used

| Operation | Endpoint | Auth Required | Purpose |
|-----------|----------|---------------|---------|
| Schema Discovery | `/objectschema/list` | OAuth | Get all schemas |
| Object Types | `/objectschema/{id}/objecttypes` | OAuth | Get object types |
| Attributes | `/objecttype/{id}/attributes` | OAuth | Get field definitions |
| Asset Retrieval | `/object/{key}` | Basic/OAuth | Get single asset |
| Bulk Query | `/object/aql` | Basic/OAuth | AQL-based asset search |
| Asset Update | `/object/{id}` | Basic/OAuth | Update asset attributes |
| User Search | `/rest/api/3/user/search` | Basic/OAuth | Find users by email |

### Rate Limiting Strategy

**Code Reference:** [`JiraAssetsClient._rate_limit()`](src/jira_assets_client.py#L143-L153)

```python
def _rate_limit(self):
    """Implement rate limiting between requests."""
    current_time = time.time()
    time_since_last_request = current_time - self.last_request_time
    
    if time_since_last_request < self.min_request_interval:
        sleep_time = self.min_request_interval - time_since_last_request
        self.logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
        time.sleep(sleep_time)
    
    self.last_request_time = time.time()
```

**Configuration:**
```bash
MAX_REQUESTS_PER_MINUTE=300  # Default rate limit
```

**Automatic Rate Limit Handling:**
- Monitors `X-RateLimit-*` headers
- Respects `Retry-After` header on 429 responses
- Implements exponential backoff for repeated rate limit errors

## Code Examples

### Example 1: Complete Schema Discovery Workflow

```python
from src.jira_assets_client import JiraAssetsClient
from src.asset_manager import AssetManager

# Initialize clients (OAuth required for schema access)
assets_client = JiraAssetsClient()
asset_manager = AssetManager()

# Step 1: Discover all schemas
schemas = assets_client.get_object_schemas()
print(f"Found {len(schemas)} schemas:")
for schema in schemas:
    print(f"  - {schema['name']} (ID: {schema['id']})")

# Step 2: Get specific schema
hardware_schema = asset_manager.get_hardware_schema()
schema_id = hardware_schema['id']

# Step 3: Discover object types
object_types = assets_client.get_object_types(schema_id)
print(f"Object types in Hardware schema:")
for obj_type in object_types:
    print(f"  - {obj_type['name']} (ID: {obj_type['id']})")

# Step 4: Get Laptops object type
laptops_object_type = asset_manager.get_laptops_object_type()
object_type_id = laptops_object_type['id']

# Step 5: Discover attributes
attributes = assets_client.get_object_attributes(object_type_id)
print(f"Attributes in Laptops object type:")
for attr in attributes:
    print(f"  - {attr['name']} ({attr['type']['name']})")
```

### Example 2: AQL Query Examples

```python
# Basic object type filtering
aql_query = 'objectType = "Laptops"'

# Filter by attribute existence
aql_query = 'objectType = "Laptops" AND "User Email" IS NOT EMPTY'

# Complex filtering with multiple conditions
aql_query = '''
objectType = "Laptops" AND 
"User Email" IS NOT EMPTY AND 
"Assignee" IS EMPTY AND
"Asset Status" != "Retired"
'''

# Date-based filtering
aql_query = '''
objectType = "Laptops" AND 
"Retirement Date" IS NOT EMPTY AND
"Asset Status" != "Retired"
'''

# Execute AQL query with pagination
result = assets_client.find_objects_by_aql(
    aql_query, 
    start=0, 
    limit=100,
    include_attributes=True
)

objects = result.get('values', [])
total_count = result.get('total', 0)
print(f"Found {len(objects)} objects (Total: {total_count})")
```

### Example 3: Bulk Processing with Progress Tracking

```python
from tqdm import tqdm
from datetime import datetime

def process_all_laptops(dry_run=True):
    """Process all laptop assets with progress tracking."""
    asset_manager = AssetManager()
    
    # Step 1: Get all laptop assets
    print("🔍 Discovering all laptop assets...")
    all_objects = asset_manager.get_hardware_laptops_objects()
    print(f"Found {len(all_objects)} total laptop assets")
    
    # Step 2: Filter assets needing processing
    print("🔧 Filtering assets for processing...")
    objects_to_process = asset_manager.filter_objects_for_processing(all_objects)
    print(f"Found {len(objects_to_process)} assets needing updates")
    
    if not objects_to_process:
        print("✅ No assets need processing")
        return
    
    # Step 3: Process with progress tracking
    results = []
    progress_bar = tqdm(
        total=len(objects_to_process),
        desc="Processing assets",
        unit="assets"
    )
    
    successful = 0
    skipped = 0
    errors = 0
    
    for asset_obj in objects_to_process:
        object_key = asset_obj.get('objectKey', 'unknown')
        
        try:
            result = asset_manager.process_asset(object_key, dry_run=dry_run)
            results.append(result)
            
            if result.get('success'):
                successful += 1
            if result.get('skipped'):
                skipped += 1
                
        except Exception as e:
            errors += 1
            error_result = {
                'object_key': object_key,
                'success': False,
                'error': str(e),
                'dry_run': dry_run,
                'timestamp': datetime.now().isoformat()
            }
            results.append(error_result)
        
        # Update progress bar
        status = f"Processing (✓{successful} ⚠{skipped} ✗{errors})"
        progress_bar.set_description(status)
        progress_bar.update(1)
    
    progress_bar.close()
    
    # Step 4: Save results and generate summary
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"bulk_processing_results_{timestamp}.json"
    
    with open(f"backups/{filename}", 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"📊 Processing Summary:")
    print(f"  Total: {len(results)}")
    print(f"  Successful: {successful}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors: {errors}")
    print(f"  Results saved to: backups/{filename}")

# Run the bulk processing
process_all_laptops(dry_run=True)
```

## Performance Considerations

### 1. API Call Optimization

**Without Schema Caching:**
- 1000 assets × (1 schema + 1 object type + 1 attributes + 1 asset fetch) = 4000 API calls
- Processing time: ~13 minutes at 300 requests/minute

**With Schema Caching:**
- Initial: 1 schema + 1 object type + 1 attributes = 3 API calls
- Per asset: 1 asset fetch = 1000 API calls
- Total: 1003 API calls (~75% reduction)
- Processing time: ~3.5 minutes

### 2. Batch Size Configuration

```bash
# Small batches for testing
BATCH_SIZE=5

# Default production setting
BATCH_SIZE=10

# Large batches for high-performance environments
BATCH_SIZE=50
```

**Batch Size Impact:**
- **Small batches (5-10)**: More frequent progress updates, slower overall processing
- **Large batches (50-100)**: Fewer progress updates, faster processing, higher memory usage

### 3. Memory Usage Optimization

The system processes assets in streaming fashion to minimize memory usage:

```python
# Instead of loading all assets into memory
all_objects = get_all_assets()  # Memory intensive
for obj in all_objects:
    process(obj)

# Stream processing with pagination
start = 0
limit = 100
while True:
    batch = get_assets_batch(start, limit)  # Memory efficient
    if not batch:
        break
    for obj in batch:
        process(obj)
    start += limit
```

### 4. Network Optimization

- **Connection pooling**: Reuses HTTP connections
- **Compression**: Automatic gzip compression support
- **Timeout handling**: Configurable request timeouts
- **Retry logic**: Exponential backoff for network errors

## Troubleshooting

### Common Issues and Solutions

#### 1. Schema Access Denied

**Error:**
```
ERROR: Permission denied: Check Assets API scopes and permissions
```

**Cause:** Using Basic Auth for bulk operations that require schema access.

**Solution:**
1. Switch to OAuth 2.0 authentication:
   ```bash
   AUTH_METHOD=oauth
   OAUTH_CLIENT_ID=your-client-id
   OAUTH_CLIENT_SECRET=your-client-secret
   ```

2. Ensure OAuth app has required scopes:
   ```bash
   OAUTH_SCOPES=read:jira-user read:cmdb-object:jira read:cmdb-schema:jira write:cmdb-object:jira
   ```

3. Run OAuth setup:
   ```bash
   python src/main.py --oauth-setup
   ```

#### 2. Schema Not Found

**Error:**
```
ERROR: Schema 'Hardware' not found
```

**Cause:** Configured schema name doesn't match actual schema in Assets.

**Solution:**
1. List all available schemas:
   ```python
   schemas = assets_client.get_object_schemas()
   for schema in schemas:
       print(f"Schema: {schema['name']}")
   ```

2. Update configuration with correct name:
   ```bash
   HARDWARE_SCHEMA_NAME=IT Hardware  # Use exact name
   ```

#### 3. Rate Limiting Issues

**Error:**
```
ERROR: Rate limit exceeded. Retry after 60 seconds
```

**Solution:**
1. Reduce request rate:
   ```bash
   MAX_REQUESTS_PER_MINUTE=200  # Reduce from 300
   ```

2. Use smaller batch sizes:
   ```bash
   BATCH_SIZE=5  # Reduce from 10
   ```

3. Enable verbose logging to monitor rate limiting:
   ```bash
   python src/main.py --bulk --verbose
   ```

#### 4. Attribute Not Found

**Error:**
```
ERROR: Attribute 'User Email' not found in object type 123
```

**Solution:**
1. List all available attributes:
   ```python
   attributes = assets_client.get_object_attributes(object_type_id)
   for attr in attributes:
       print(f"Attribute: {attr['name']}")
   ```

2. Update configuration with correct attribute name:
   ```bash
   USER_EMAIL_ATTRIBUTE=Email Address  # Use exact name
   ```

#### 5. OAuth Token Issues

**Error:**
```
ERROR: OAuth token expired and refresh failed
```

**Solution:**
1. Delete existing token file:
   ```bash
   rm ~/.jira_assets_oauth_token.json
   ```

2. Re-run OAuth setup:
   ```bash
   python src/main.py --oauth-setup
   ```

### Debug Mode

Enable verbose logging to see detailed API interactions:

```bash
python src/main.py --test-asset HW-459 --verbose
```

**Debug Output Includes:**
- All API requests and responses
- Cache hit/miss statistics
- Rate limiting delays
- Authentication token refresh
- Processing step details

### Performance Monitoring

Monitor processing performance with built-in statistics:

```python
# Cache statistics
cache_stats = asset_manager.get_cache_stats()
print(f"Cache Statistics: {cache_stats}")

# Processing summary
summary = asset_manager.get_processing_summary(results)
print(f"Success Rate: {summary['success_rate']:.1f}%")
print(f"Skip Reasons: {summary['skip_reasons']}")
```

---

## Related Documentation

- [README.md](README.md) - General usage and setup instructions
- [WARP.md](WARP.md) - Development and architecture guide
- [`src/jira_assets_client.py`](src/jira_assets_client.py) - Assets API client implementation
- [`src/asset_manager.py`](src/asset_manager.py) - High-level asset processing logic
- [`src/main.py`](src/main.py) - CLI interface and bulk processing orchestration

---

**Last Updated:** 2025-08-21  
**Version:** 1.0.0
