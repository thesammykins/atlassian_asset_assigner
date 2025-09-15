# Asset Creation Caching System

## Overview

The Jira Assets Manager now includes a comprehensive caching system that dramatically improves performance for the asset creation workflow. The caching system targets the three most expensive API operations that occur during every asset creation:

- **Models Loading** (~8-10 seconds) → **Instant** (from cache)
- **Statuses Loading** (~2-3 seconds) → **Instant** (from cache)  
- **Suppliers Loading** (~2-3 seconds) → **Instant** (from cache)

**Total Performance Improvement:** 10-15 seconds reduced to <1 second for subsequent asset creations.

## How It Works

### Cache Storage
- **Location:** `./cache/` directory (auto-created)
- **Format:** JSON files with metadata and timestamp
- **TTL:** 24 hours (configurable)
- **Naming:** `{cache_key}_{workspace_id}.json` (workspace-specific)

### Cached Data
1. **Models List** (`models_list_*.json`)
   - All unique model names from existing laptop assets
   - Extracted from 314+ asset objects via paginated AQL queries
   - Sorted alphabetically for consistent display

2. **Statuses List** (`statuses_list_*.json`)
   - Available status options (Assigned, In Stock, etc.)
   - Extracted from existing assets with status values
   - Used for status selection during asset creation

3. **Suppliers List** (`suppliers_list_*.json`)
   - All supplier objects with names and keys
   - Used for supplier selection and auto-creation
   - Automatically invalidated when new suppliers are created

### Cache Invalidation
- **Automatic:** 24-hour TTL based on file modification time
- **Manual:** `--clear-cache` option forces fresh data loading
- **Smart:** Suppliers cache invalidated automatically when new suppliers are created
- **Cleanup:** `--cache-cleanup` removes expired files

## Usage

### First Asset Creation (Cache Miss)
```bash
python3 src/main.py --new --execute
```
**Result:** Normal API loading times, data cached for future use

### Subsequent Asset Creations (Cache Hit)
```bash
python3 src/main.py --new --execute
```
**Result:** Instant loading from cache, dramatic speed improvement

### Cache Management Commands

#### View Cache Information
```bash
python3 src/main.py --cache-info
```
Shows:
- Cache directory location
- TTL settings (24 hours)
- Number of valid/expired files
- Detailed file information with ages and sizes

#### Clear All Cache (Force Fresh Data)
```bash
python3 src/main.py --new --clear-cache
```
Forces fresh API calls, ignores existing cache

#### Remove Expired Files
```bash
python3 src/main.py --cache-cleanup
```
Removes cache files older than 24 hours

## Cache File Structure

```json
{
  "cached_at": "2025-09-15T00:26:50.115521+00:00",
  "ttl_seconds": 86400,
  "data": [
    "iMac (Retina 5K, 27-inch, 2019)",
    "MacBook Air (13-inch, M3, 2024)",
    "..."
  ]
}
```

## Performance Comparison

### Before Caching
```
INFO: 📦 Loading available models...
[Multiple API calls, pagination, processing 314 objects...]
Time: ~10 seconds

INFO: 📊 Loading available statuses...  
[API calls processing 50 objects...]
Time: ~3 seconds

INFO: 🏢 Loading available suppliers...
[API calls processing suppliers...]
Time: ~2 seconds

Total: ~15 seconds per asset creation
```

### With Caching (Subsequent Runs)
```
INFO: 📦 Loading available models...
Using cached models_list (cached at 2025-09-15T00:26:50.115521+00:00)
Using 25 models from cache
Time: <0.1 seconds

INFO: 📊 Loading available statuses...
Using cached statuses_list (cached at 2025-09-15T00:26:51.466890+00:00) 
Using 8 statuses from cache
Time: <0.1 seconds

Total: <1 second per asset creation (15x improvement!)
```

## Technical Implementation

### CacheManager Class
- **File-based storage** with JSON serialization
- **TTL validation** based on file modification times  
- **Workspace isolation** via filename prefixes
- **Atomic operations** for cache read/write/invalidate
- **Error handling** for corrupted files and permission issues

### Integration Points
- **AssetManager** methods updated with cache-first logic
- **CLI options** for cache management operations
- **Automatic invalidation** when data changes (supplier creation)
- **Logging integration** with detailed cache hit/miss reporting

### Configuration
- **Cache Directory:** `./cache/` (configurable)
- **TTL:** 24 hours (86400 seconds, configurable)
- **File Permissions:** 644 (readable, secure)
- **Workspace Isolation:** Automatic via workspace ID prefix

## Benefits

1. **Massive Performance Improvement**
   - 15x faster asset creation after initial cache population
   - Reduced API load on Jira Assets
   - Better user experience with instant data loading

2. **Intelligent Caching**
   - Only caches stable data that changes infrequently
   - Automatic invalidation when data changes
   - Workspace-specific cache isolation

3. **Robust Management**
   - Multiple CLI options for cache control
   - Detailed cache information and monitoring
   - Automatic cleanup of expired data

4. **Transparent Operation**
   - Falls back gracefully to API calls when cache unavailable
   - Maintains all existing functionality
   - Clear logging of cache hits/misses

## Cache Lifecycle

1. **Initial Load:** API calls made, results cached
2. **Subsequent Loads:** Data served from cache (if valid)
3. **Expiration:** Files older than 24 hours ignored
4. **Invalidation:** Manual clear or automatic (suppliers)
5. **Refresh:** New API calls made, cache updated

This caching system transforms the asset creation experience from slow and API-intensive to fast and responsive, while maintaining data accuracy and providing comprehensive management options.