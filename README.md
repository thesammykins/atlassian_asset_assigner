# 🎯 Jira Assets Manager

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub stars](https://img.shields.io/github/stars/thesammykins/atlassian_asset_assigner.svg)](https://github.com/thesammykins/atlassian_asset_assigner/stargazers)

A comprehensive Python tool for automating the management of Jira Assets by extracting user email attributes and updating assignee fields with corresponding Jira accountIds.

## ✅ Current Status

**✨ Fully functional and production-ready!**
- ✅ **Single asset processing** - Test and update individual assets
- ✅ **Bulk asset processing** - Process multiple assets with progress tracking
- ✅ **Email extraction** - Extract user emails from configurable asset attributes
- ✅ **User lookup** - Map emails to Jira user accountIds with caching
- ✅ **Asset updates** - Update assignee fields in Jira Assets
- ✅ **Dry run mode** - Preview changes before applying them
- ✅ **OAuth 2.0 support** - Full OAuth authentication for enhanced permissions
- ✅ **Rate limiting** - Respects API limits with intelligent throttling
- ✅ **Progress tracking** - Real-time progress bars and detailed reporting
- ✅ **Error handling** - Robust error handling with retry logic

## Overview

This tool solves the common problem of having user email addresses in Jira Assets objects but needing to populate assignee fields with Jira accountIds. It:

1. **Fetches assets** from specified Jira Assets schemas and object types
2. **Extracts user email addresses** from configurable attribute fields
3. **Looks up Jira users** by email to get their accountIds
4. **Updates assignee fields** with the correct accountIds
5. **Provides detailed reporting** and progress tracking

## Features

- ✅ **Secure Configuration Management** - Uses environment variables for credentials
- ✅ **Rate Limiting** - Respects Jira API rate limits to avoid throttling
- ✅ **Comprehensive Logging** - Detailed logs with configurable levels
- ✅ **Caching** - Reduces API calls by caching user lookups and schema data
- ✅ **Dry Run Mode** - Preview changes before applying them
- ✅ **Progress Tracking** - Visual progress bars for bulk operations
- ✅ **Error Handling** - Robust error handling with detailed error reporting
- ✅ **Backup & Recovery** - Creates backups before making changes
- ✅ **Filtering** - Only processes assets that need updates

## Installation

### Prerequisites

- Python 3.13+ (tested with 3.13.2)
- Valid Jira Cloud instance with Assets enabled
- API token for Jira authentication

### Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/thesammykins/atlassian_asset_assigner.git
   cd atlassian_asset_assigner
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your actual values (see Configuration section)
   ```

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and configure the following variables:

```bash
# Jira Instance Configuration
JIRA_DOMAIN=your-domain.atlassian.net
JIRA_USER_EMAIL=your.email@company.com

# API Token - Generate from: https://id.atlassian.com/manage-profile/security/api-tokens
JIRA_API_TOKEN=your_api_token_here

# Jira Assets Configuration
ASSETS_WORKSPACE_ID=your_workspace_id

# Schema and Object Schema Configuration
HARDWARE_SCHEMA_NAME=Hardware
LAPTOPS_OBJECT_SCHEMA_NAME=Laptops

# Asset Attributes
USER_EMAIL_ATTRIBUTE=User Email
ASSIGNEE_ATTRIBUTE=Assignee

# API Rate Limiting (requests per minute)
MAX_REQUESTS_PER_MINUTE=300
BATCH_SIZE=10

# Logging Configuration
LOG_LEVEL=INFO
LOG_TO_FILE=true
```

### Getting Your API Token (Basic Authentication)

1. Go to [https://id.atlassian.com/manage-profile/security/api-tokens](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click "Create API token"
3. Give it a descriptive label like "Jira Assets Manager"
4. Copy the generated token and add it to your `.env` file

### Setting Up OAuth 2.0 (For Advanced Permissions)

**⚠️ OAuth 2.0 is required for bulk operations** that need schema access (`read:cmdb-schema:jira` scope).

#### Step 1: Create an Atlassian OAuth App

1. Go to [https://developer.atlassian.com/console/myapps/](https://developer.atlassian.com/console/myapps/)
2. Click "Create" → "OAuth 2.0 integration"
3. Fill in the app details:
   - **App name**: `Jira Assets Manager`
   - **Description**: `Automate Jira Assets user email to assignee mapping`
4. Click "Create"

#### Step 2: Configure OAuth App

1. In your new app, click "Permissions"
2. Add the following scopes:
   - `read:jira-user` - Read user information
   - `read:cmdb-object:jira` - Read Assets objects
   - `read:cmdb-schema:jira` - Read Assets schemas (required for bulk operations)
   - `write:cmdb-object:jira` - Update Assets objects

3. Click "Settings" and configure:
   - **Callback URL**: `http://localhost:8080/callback`
   - **Additional settings** as needed

4. Save your **Client ID** and **Client Secret**

#### Step 3: Update Configuration

1. Set `AUTH_METHOD=oauth` in your `.env` file
2. Add your OAuth credentials:
   ```bash
   AUTH_METHOD=oauth
   OAUTH_CLIENT_ID=your-client-id-here
   OAUTH_CLIENT_SECRET=your-client-secret-here
   OAUTH_REDIRECT_URI=http://localhost:8080/callback
   OAUTH_SCOPES=read:jira-user read:cmdb-object:jira read:cmdb-schema:jira write:cmdb-object:jira
   ```

#### Step 4: First-Time Authorization

When you run the tool with OAuth for the first time:

1. A browser window will open automatically
2. Log in to your Atlassian account
3. Grant permissions to the app
4. You'll be redirected to a local callback page with a success message
5. Both access and refresh tokens will be saved securely to `~/.jira_assets_oauth_token.json`

**First-time setup:**
```bash
# Set up OAuth authentication (one-time setup)
python src/main.py --oauth-setup
```

**Or trigger OAuth setup during normal usage:**
```bash
# This will trigger the OAuth flow if no valid token exists
python src/main.py --bulk --dry-run
```

#### Token Management & Persistence

The OAuth implementation includes robust token management:

- **Automatic Token Storage**: Access and refresh tokens are securely stored locally
- **Token Validation**: Tokens are validated before each API call
- **Automatic Refresh**: Expired access tokens are automatically refreshed using the refresh token
- **Secure Storage**: Tokens are stored with `600` permissions (owner read/write only)
- **Error Recovery**: If refresh fails, you'll be prompted to re-authorize

**Token File Location**: `~/.jira_assets_oauth_token.json`

**What to Expect:**
- **First Run**: Browser opens for authorization, tokens saved
- **Subsequent Runs**: Tokens loaded automatically, no browser required
- **After Token Expiry**: Automatic refresh (no user interaction needed)
- **After Refresh Token Expiry**: New authorization required (≈90 days)

#### OAuth vs API Token Comparison

| Feature | API Token | OAuth 2.0 |
|---------|-----------|------------|
| Single asset operations | ✅ | ✅ |
| User lookups | ✅ | ✅ |
| Asset updates | ✅ | ✅ |
| **Bulk operations** | ❌ | ✅ |
| **Schema access** | ❌ | ✅ |
| Setup complexity | Simple | Moderate |
| Token management | Manual | Automatic |

### Finding Your Assets Workspace ID

The workspace ID can be found by accessing:
```
https://your-domain.atlassian.net/rest/servicedeskapi/assets/workspace
```

This will return a JSON response with your workspace ID.

## Usage

### Command Line Interface

The tool provides several command-line options:

```bash
python src/main.py --help
```

### Basic Usage Examples

#### Test on a Specific Asset (Dry Run)
```bash
python src/main.py --test-asset HW-459
```

#### Test and Execute Update on Specific Asset
```bash
python src/main.py --test-asset HW-459 --execute
```

#### Preview Bulk Operation (Dry Run)
```bash
python src/main.py --bulk --dry-run
```

#### Execute Bulk Operation
```bash
python src/main.py --bulk --execute
```

#### Bulk Operation with Custom Batch Size
```bash
python src/main.py --bulk --batch-size 5 --execute
```

#### Verbose Logging
```bash
python src/main.py --test-asset HW-459 --verbose
```

#### Clear Caches Before Processing
```bash
python src/main.py --bulk --clear-cache --execute
```

### Command Line Options

| Option | Description |
|--------|-------------|
| `--test-asset KEY` | Test processing on a specific asset (e.g., HW-459) |
| `--bulk` | Process all assets in Hardware/Laptops schema |
| `--oauth-setup` | Set up OAuth 2.0 authentication (required for bulk operations) |
| `--dry-run` | Preview changes without applying them (default) |
| `--execute` | Actually apply changes (overrides --dry-run) |
| `--batch-size N` | Batch size for bulk operations (default: 10) |
| `--verbose, -v` | Enable verbose logging |
| `--quiet, -q` | Suppress non-error output |
| `--clear-cache` | Clear all caches before processing |

## How It Works

### Single Asset Processing

1. **Fetch Asset**: Retrieves the asset details using the Assets API
2. **Extract Email**: Looks for the "User Email" attribute value
3. **Lookup User**: Searches Jira for a user with that email address
4. **Validate Account**: Ensures the accountId is valid and active
5. **Check Current State**: Verifies if update is needed
6. **Update Assignee**: Sets the assignee field to the accountId (if not dry run)
7. **Verify Update**: Confirms the update was applied correctly

### Bulk Processing

1. **Fetch All Assets**: Retrieves all objects from the specified schema/object type
2. **Filter Assets**: Only processes assets with email but no assignee
3. **Process in Batches**: Handles assets in configurable batch sizes
4. **Progress Tracking**: Shows real-time progress with statistics
5. **Result Logging**: Saves detailed results to JSON files
6. **Summary Report**: Displays comprehensive statistics

### Error Handling

The tool includes comprehensive error handling for:

- **Network Issues**: Retries with exponential backoff
- **Rate Limiting**: Automatically respects API rate limits
- **Authentication Errors**: Clear error messages for credential issues
- **Permission Errors**: Identifies missing scopes or permissions
- **Data Validation**: Validates emails, accountIds, and asset data
- **API Errors**: Handles various Jira API error responses

## Output and Logging

### Console Output

The tool provides colored console output with:
- 🟢 **Success messages** in green
- 🟡 **Warnings** in yellow  
- 🔴 **Errors** in red
- 🔵 **Information** in blue

### Log Files

When `LOG_TO_FILE=true`, logs are written to:
- `logs/jira_assets_manager.log` - Main application logs
- Console output for real-time feedback

### Result Files

Bulk operations create backup files in the `backups/` directory:
- `bulk_processing_results_YYYYMMDD_HHMMSS.json` - Detailed results
- Contains processing status for each asset
- Includes error messages and skip reasons

### Sample Output

```
╔══════════════════════════════════════════════════════════════╗
║                    Jira Assets Manager                      ║  
║              User Email → Assignee Automation               ║
╚══════════════════════════════════════════════════════════════╝

SUCCESS: Environment configuration validated
INFO: DRY RUN mode - no changes will be applied

INFO: Testing asset: HW-459 (dry_run=True)

============================================================
Asset: HW-459
============================================================
User Email:          john.doe@company.com
Current Assignee:    None
Account ID:          712020:abc123-def456-789abc-123def456789
New Assignee:        712020:abc123-def456-789abc-123def456789

INFO: Status: Processed (dry run)

INFO: Test completed successfully (dry run)
```

## Directory Structure

```
jira_assets_manager/
├── src/
│   ├── __init__.py           # Package initialization
│   ├── main.py               # Main CLI application
│   ├── config.py             # Configuration management
│   ├── asset_manager.py      # High-level asset management
│   ├── jira_assets_client.py # Jira Assets API client
│   └── jira_user_client.py   # Jira User API client
├── tests/                    # Test files (future)
├── logs/                     # Application logs
├── backups/                  # Result and backup files
├── docs/                     # Documentation
├── requirements.txt          # Python dependencies
├── .env.example             # Environment template
├── .env                     # Your configuration (not in git)
├── .gitignore              # Git ignore rules
└── README.md               # This file
```

## API Endpoints Used

### Jira User API
- `GET /rest/api/3/user/search` - Search users by email
- `GET /rest/api/3/user` - Validate user accounts

### Jira Assets API
- `GET /rest/servicedeskapi/assets/workspace` - Get workspace info
- `GET /gateway/api/jsm/assets/workspace/{workspaceId}/v1/objectschema` - Get schemas
- `GET /gateway/api/jsm/assets/workspace/{workspaceId}/v1/objectschema/{id}/objecttypes` - Get object types
- `GET /gateway/api/jsm/assets/workspace/{workspaceId}/v1/objecttype/{id}/attributes` - Get attributes
- `GET /gateway/api/jsm/assets/workspace/{workspaceId}/v1/object/{key}` - Get asset by key
- `POST /gateway/api/jsm/assets/workspace/{workspaceId}/v1/object/aql` - Search assets with AQL
- `PUT /gateway/api/jsm/assets/workspace/{workspaceId}/v1/object/{id}` - Update asset

## Rate Limiting

The tool respects Jira's API rate limits:
- **Default**: 300 requests per minute
- **Automatic spacing** between requests
- **Rate limit headers** are monitored and respected
- **Exponential backoff** on rate limit errors

## Troubleshooting

### Common Issues

**1. Authentication Failed**
```
ERROR: Authentication failed: Check API credentials
```
**Solution**: Verify your `JIRA_USER_EMAIL` and `JIRA_API_TOKEN` in `.env`

**2. Permission Denied**
```  
ERROR: Permission denied: Check Assets API scopes and permissions
```
**Solution**: Ensure your API token has the necessary permissions for Assets

**3. Schema Not Found**
```
ERROR: Schema 'Hardware' not found
```
**Solution**: Check the `HARDWARE_SCHEMA_NAME` in your `.env` file

**4. Asset Not Found**
```
ERROR: Asset HW-459 not found
```
**Solution**: Verify the asset key exists and you have access to it

**5. User Not Found**
```
WARNING: No user found with email: user@example.com
```
**Solution**: This is expected for emails that don't correspond to Jira users

### Debug Mode

Enable verbose logging for detailed debugging:
```bash
python src/main.py --test-asset HW-459 --verbose
```

This will show:
- All API requests and responses  
- Caching operations
- Rate limiting delays
- Detailed processing steps

### Configuration Validation

The tool validates your configuration on startup and will show specific error messages for missing or incorrect values.

## Contributing

We welcome contributions to improve the Jira Assets Manager! Here's how you can help:

### Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/atlassian_asset_assigner.git
   cd atlassian_asset_assigner
   ```
3. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

### Making Changes

1. **Set up the development environment** (see Installation section)
2. **Make your changes** following the existing code style
3. **Test your changes** thoroughly:
   - Test with single asset processing
   - Test with bulk operations (if applicable)
   - Ensure OAuth and API token authentication both work
4. **Add tests** if you're adding new functionality
5. **Update documentation** if needed

### Submitting Changes

1. **Commit your changes** with clear, descriptive messages:
   ```bash
   git commit -m "Add feature: description of what you added"
   ```
2. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```
3. **Create a Pull Request** on GitHub with:
   - Clear description of changes
   - Screenshots/logs if applicable
   - Reference to any related issues

### Code Guidelines

- Follow Python PEP 8 style guidelines
- Use type hints where appropriate
- Add docstrings for new functions/classes
- Keep functions focused and single-purpose
- Handle errors gracefully with informative messages

### Reporting Issues

If you find a bug or have a feature request:

1. **Check existing issues** first to avoid duplicates
2. **Create a new issue** with:
   - Clear, descriptive title
   - Steps to reproduce (for bugs)
   - Expected vs actual behavior
   - Your environment details (Python version, OS, etc.)
   - Relevant log excerpts (without sensitive data)

## Security

🔐 **Security is paramount when working with API credentials:**

- **Never commit** your `.env` file or any files containing real credentials
- **Use environment variables** for all sensitive configuration
- **Regularly rotate** your API tokens and OAuth credentials
- **Review permissions** granted to API tokens - use minimal required scopes
- **Use OAuth 2.0** for production environments when possible
- **Store tokens securely** - the tool uses `600` file permissions for token storage
- **Monitor API usage** to detect any unusual activity

### Reporting Security Issues

If you discover a security vulnerability, please:

1. **Do not** create a public issue
2. **Contact the maintainers** directly via GitHub's private vulnerability reporting
3. **Include details** about the vulnerability and potential impact
4. **Allow time** for the issue to be addressed before public disclosure

## License

**MIT License**

Copyright (c) 2025 Jira Assets Manager Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

### Third-Party Libraries

This project uses several third-party libraries. See `requirements.txt` for the complete list. All dependencies are used under their respective licenses.

### Disclaimer

**Important:** This tool interacts with your Jira instance and can modify data. Always:
- Test in a non-production environment first
- Use dry-run mode to preview changes
- Ensure you have proper backups
- Review your organization's policies before use
- Understand the API permissions you're granting

## Support

For issues and questions:

1. Check the troubleshooting section above
2. Review the log files for detailed error information
3. Verify your configuration matches the examples
4. Test with a single asset before bulk operations

## Changelog

### v1.0.0 (Initial Release)
- ✅ Core functionality for asset processing
- ✅ Comprehensive CLI interface
- ✅ Rate limiting and caching
- ✅ Dry run capabilities
- ✅ Progress tracking and logging
- ✅ Error handling and recovery
- ✅ Configuration management
