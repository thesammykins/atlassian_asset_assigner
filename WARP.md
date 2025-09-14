# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Quick Start

### Essential Development Setup
```bash
# Setup virtual environment and dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials (see Configuration section below)
```

### Core Commands
```bash
# Test single asset processing (dry run)
python3 src/main.py --test-asset HW-459

# Test and execute on specific asset
python3 src/main.py --test-asset HW-459 --execute

# OAuth setup for bulk operations (one-time)
python3 src/main.py --oauth-setup

# Bulk processing (dry run first, then execute)
python3 src/main.py --bulk --dry-run
python3 src/main.py --bulk --execute

# Quick test script for development
python3 test_single_laptop.py
```

### Development and Testing
```bash
# Clear caches during development
python3 src/main.py --test-asset HW-459 --clear-cache

# Verbose logging for debugging
python3 src/main.py --test-asset HW-459 --verbose

# Process in smaller batches for testing
python3 src/main.py --bulk --batch-size 5 --execute
```

## Authentication Architecture

This application uses **dual authentication modes** based on operation requirements:

### Basic Auth (API Token)
- **Use for**: Single asset operations, development, testing
- **Setup**: Set `AUTH_METHOD=basic` in .env
- **Requirements**: `JIRA_USER_EMAIL` and `JIRA_API_TOKEN`
- **Limitations**: Cannot access schema endpoints required for bulk operations

### OAuth 2.0
- **Use for**: Bulk operations requiring `read:cmdb-schema:jira` scope
- **Setup**: Set `AUTH_METHOD=oauth` and configure OAuth app
- **Token Management**: Automatic refresh, stored in `~/.jira_assets_oauth_token.json`
- **Browser Flow**: Initial authorization opens browser for user consent

**Key Architecture Note**: OAuth uses site-specific routing (`api.atlassian.com/ex/jira/{site_id}`) while basic auth uses direct domain URLs.

## Application Architecture

### Multi-Client Design
The application employs a three-layer client architecture:

1. **AssetManager** (`asset_manager.py`)
   - High-level business logic orchestration
   - Coordinates between user and assets clients
   - Handles attribute extraction and update workflows

2. **JiraAssetsClient** (`jira_assets_client.py`)
   - Assets API interactions (objects, schemas, attributes)
   - AQL query execution and object CRUD operations
   - Schema and object type caching

3. **JiraUserClient** (`jira_user_client.py`)
   - User search and account validation
   - Email-to-accountId resolution with caching
   - User information lookup and verification

4. **OAuthClient** (`oauth_client.py`)
   - OAuth 2.0 flow management and token persistence
   - Automatic token refresh and site ID discovery
   - Browser-based authorization with local callback server

### Configuration Management
- **Config Class** (`config.py`): Centralized environment variable management
- **Validation**: Runtime validation of required variables by auth method
- **Logging**: File and console logging with configurable levels

## Key Workflows

### Single Asset Processing
1. Fetch asset by object key (e.g., HW-459)
2. Extract "User Email" attribute value
3. Lookup Jira user by email → get accountId
4. Validate accountId exists and is active
5. Create attribute update for "Assignee" field
6. Apply update (if not dry-run) and verify

### Bulk Asset Processing
1. **Schema Discovery**: Get Hardware schema → Laptops object type
2. **Asset Query**: Use AQL to fetch all assets with email but no assignee
3. **Batch Processing**: Process in configurable batches (default: 10)
4. **Progress Tracking**: Real-time progress bars with success/skip/error counts
5. **Result Persistence**: JSON backup files in `backups/` directory

### OAuth Authorization Flow
1. **Check Existing Token**: Validate cached token in `~/.jira_assets_oauth_token.json`
2. **Browser Authorization**: Open browser to Atlassian auth page
3. **Local Callback**: HTTP server on localhost:8080 captures auth code
4. **Token Exchange**: Exchange auth code for access + refresh tokens
5. **Site Discovery**: Resolve Atlassian site ID for API routing
6. **Token Storage**: Securely save tokens with 600 file permissions

## Configuration Requirements

### Required Environment Variables

**Basic Auth Mode:**
```bash
JIRA_DOMAIN=your-domain.atlassian.net
JIRA_USER_EMAIL=your.email@company.com
JIRA_API_TOKEN=your_api_token_here
ASSETS_WORKSPACE_ID=your_workspace_id
```

**OAuth Mode (additional):**
```bash
AUTH_METHOD=oauth
OAUTH_CLIENT_ID=your-client-id
OAUTH_CLIENT_SECRET=your-client-secret
OAUTH_REDIRECT_URI=http://localhost:8080/callback
OAUTH_SCOPES=read:jira-user read:cmdb-object:jira read:cmdb-schema:jira write:cmdb-object:jira
```

**Optional Configuration:**
```bash
# Asset schema configuration
HARDWARE_SCHEMA_NAME=Hardware
LAPTOPS_OBJECT_SCHEMA_NAME=Laptops
USER_EMAIL_ATTRIBUTE=User Email
ASSIGNEE_ATTRIBUTE=Assignee

# API behavior
MAX_REQUESTS_PER_MINUTE=300
BATCH_SIZE=10
LOG_LEVEL=INFO
LOG_TO_FILE=true
```

### Critical Setup Steps
1. **Workspace ID Discovery**: Get from `https://your-domain.atlassian.net/rest/servicedeskapi/assets/workspace`
2. **OAuth App Creation**: Create at developer.atlassian.com with required scopes
3. **API Token**: Generate at id.atlassian.com/manage-profile/security/api-tokens

## Domain Knowledge: Jira Assets

### Schema Hierarchy
```
Workspace → Schema → Object Type → Object (Asset)
                              ↓
                         Attributes
```

### Key Concepts
- **AQL (Asset Query Language)**: SQL-like query language for asset search
- **Attribute Types**: Reference (user), Text, Number, Date, etc.
- **Object Keys**: Human-readable identifiers (e.g., HW-459)
- **Account IDs**: Atlassian's internal user identifiers (starts with numbers like 712020:...)

### API Endpoint Patterns
- **Direct Domain** (Basic Auth): `https://domain.atlassian.net/rest/api/3/...`
- **Site-Specific** (OAuth): `https://api.atlassian.com/ex/jira/{site_id}/rest/api/3/...`
- **Assets Gateway**: `/gateway/api/jsm/assets/workspace/{workspaceId}/v1/...`

## Error Handling Patterns

### Specific Exception Types
- `AssetNotFoundError`: Invalid object key or insufficient permissions
- `UserNotFoundError`: Email doesn't match any Jira user
- `SchemaNotFoundError`: Schema name mismatch in configuration
- `TokenError`: OAuth token expired or invalid
- `JiraAssetsAPIError`: General API failures (rate limits, permissions)

### Common Resolution Patterns
- **Rate Limiting**: Automatic exponential backoff with `Retry-After` header respect
- **Token Refresh**: Automatic OAuth token refresh on 401 responses
- **Cache Management**: Clear caches when schema/object type structures change

## Development Guidelines

### Rate Limiting Considerations
- Default: 300 requests/minute with automatic spacing
- Bulk operations respect rate limits across all API clients
- Cache aggressively to minimize API calls (schema, object types, users)

### Testing Approach
- Use `--dry-run` extensively to preview changes
- Test with single assets before bulk operations
- `test_single_laptop.py` provides integration testing template
- OAuth requires real browser interaction (no headless testing)

### Cache Invalidation
- Schema/object type changes require `--clear-cache`
- User cache persists across sessions for performance
- Manual cache clearing available via CLI flag

### Logging Strategy
- Structured logging with context (operation, asset key, etc.)
- Debug level shows all API requests/responses
- File logging creates persistent audit trail
- Color-coded console output for operational visibility

## Troubleshooting

### Authentication Issues
- **Basic Auth 403**: Check API token permissions for Assets
- **OAuth Site Discovery**: Verify domain matches exactly in accessible resources
- **Token Refresh Failures**: Delete `~/.jira_assets_oauth_token.json` and re-authorize

### Schema/Object Type Errors
- Verify schema names match exactly (case-sensitive)
- Check Assets permissions in Jira Service Management
- Use OAuth for bulk operations requiring schema access

### Rate Limiting
- Monitor `X-RateLimit-*` headers in debug logs
- Reduce `BATCH_SIZE` for high-volume operations
- Consider `MAX_REQUESTS_PER_MINUTE` reduction for large datasets

### Development Environment
- Ensure Python 3.13+ (project requirement)
- All dependencies in `requirements.txt` are required
- Virtual environment strongly recommended for isolation
