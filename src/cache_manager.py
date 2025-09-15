"""
Asset Creation Cache Manager

Provides caching functionality for frequently accessed data during asset creation
to improve performance and reduce API calls. Data is cached for 24 hours.
"""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .config import config


class CacheManager:
    """Manages file-based caching for asset creation data."""
    
    def __init__(self, cache_dir: str = None):
        """
        Initialize the cache manager.
        
        Args:
            cache_dir: Directory to store cache files (default: ./cache)
        """
        self.cache_dir = Path(cache_dir or 'cache')
        self.cache_dir.mkdir(exist_ok=True)
        
        # Cache expires after 24 hours (86400 seconds)
        self.cache_ttl = 24 * 60 * 60
        
        self.logger = logging.getLogger('jira_assets_manager.cache_manager')
        
    def _get_cache_file_path(self, cache_key: str) -> Path:
        """Get the file path for a cache key."""
        # Include workspace ID in filename to avoid conflicts between different workspaces
        workspace_id = config.assets_workspace_id[:8] if config.assets_workspace_id else "default"
        filename = f"{cache_key}_{workspace_id}.json"
        return self.cache_dir / filename
    
    def _is_cache_valid(self, cache_file: Path) -> bool:
        """Check if cache file exists and is within TTL."""
        if not cache_file.exists():
            return False
            
        # Check file modification time
        file_mtime = cache_file.stat().st_mtime
        current_time = time.time()
        
        age = current_time - file_mtime
        is_valid = age < self.cache_ttl
        
        if is_valid:
            hours_old = age / 3600
            self.logger.debug(f"Cache file {cache_file.name} is {hours_old:.1f} hours old (valid)")
        else:
            hours_old = age / 3600
            self.logger.debug(f"Cache file {cache_file.name} is {hours_old:.1f} hours old (expired)")
            
        return is_valid
    
    def get_cached_data(self, cache_key: str) -> Optional[Any]:
        """
        Retrieve cached data if it exists and is valid.
        
        Args:
            cache_key: Unique key for the cached data
            
        Returns:
            Cached data if valid, None otherwise
        """
        cache_file = self._get_cache_file_path(cache_key)
        
        if not self._is_cache_valid(cache_file):
            return None
            
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                
            # Validate cache structure
            if not isinstance(cache_data, dict) or 'data' not in cache_data:
                self.logger.warning(f"Invalid cache structure in {cache_file.name}")
                return None
                
            cached_at = cache_data.get('cached_at')
            data = cache_data.get('data')
            
            self.logger.info(f"Using cached {cache_key} (cached at {cached_at})")
            return data
            
        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(f"Failed to read cache file {cache_file.name}: {e}")
            # Remove corrupted cache file
            try:
                cache_file.unlink()
            except OSError:
                pass
            return None
    
    def cache_data(self, cache_key: str, data: Any) -> bool:
        """
        Store data in cache with current timestamp.
        
        Args:
            cache_key: Unique key for the cached data
            data: Data to cache (must be JSON serializable)
            
        Returns:
            True if successfully cached, False otherwise
        """
        cache_file = self._get_cache_file_path(cache_key)
        
        cache_data = {
            'cached_at': datetime.now(timezone.utc).isoformat(),
            'ttl_seconds': self.cache_ttl,
            'data': data
        }
        
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
                
            self.logger.info(f"Cached {cache_key} data to {cache_file.name}")
            return True
            
        except (json.JSONEncodeError, IOError) as e:
            self.logger.error(f"Failed to write cache file {cache_file.name}: {e}")
            return False
    
    def invalidate_cache(self, cache_key: str = None) -> int:
        """
        Remove cached data.
        
        Args:
            cache_key: Specific cache key to invalidate, or None to clear all cache
            
        Returns:
            Number of cache files removed
        """
        removed_count = 0
        
        if cache_key:
            # Remove specific cache file
            cache_file = self._get_cache_file_path(cache_key)
            if cache_file.exists():
                try:
                    cache_file.unlink()
                    removed_count = 1
                    self.logger.info(f"Invalidated cache for {cache_key}")
                except OSError as e:
                    self.logger.error(f"Failed to remove cache file {cache_file.name}: {e}")
        else:
            # Remove all cache files
            try:
                for cache_file in self.cache_dir.glob("*.json"):
                    cache_file.unlink()
                    removed_count += 1
                    
                self.logger.info(f"Cleared all cache files ({removed_count} files)")
                
            except OSError as e:
                self.logger.error(f"Failed to clear cache directory: {e}")
        
        return removed_count
    
    def get_cache_info(self) -> Dict[str, Any]:
        """
        Get information about current cache state.
        
        Returns:
            Dictionary with cache statistics and file info
        """
        cache_files = list(self.cache_dir.glob("*.json"))
        
        info = {
            'cache_directory': str(self.cache_dir.absolute()),
            'cache_ttl_hours': self.cache_ttl / 3600,
            'total_cache_files': len(cache_files),
            'valid_cache_files': 0,
            'expired_cache_files': 0,
            'cache_files': []
        }
        
        for cache_file in cache_files:
            is_valid = self._is_cache_valid(cache_file)
            file_mtime = cache_file.stat().st_mtime
            age_hours = (time.time() - file_mtime) / 3600
            
            file_info = {
                'name': cache_file.name,
                'age_hours': round(age_hours, 1),
                'is_valid': is_valid,
                'size_bytes': cache_file.stat().st_size
            }
            
            info['cache_files'].append(file_info)
            
            if is_valid:
                info['valid_cache_files'] += 1
            else:
                info['expired_cache_files'] += 1
        
        return info
    
    def cleanup_expired_cache(self) -> int:
        """
        Remove expired cache files.
        
        Returns:
            Number of expired files removed
        """
        removed_count = 0
        
        try:
            for cache_file in self.cache_dir.glob("*.json"):
                if not self._is_cache_valid(cache_file):
                    cache_file.unlink()
                    removed_count += 1
                    self.logger.debug(f"Removed expired cache file: {cache_file.name}")
                    
            if removed_count > 0:
                self.logger.info(f"Cleaned up {removed_count} expired cache files")
                
        except OSError as e:
            self.logger.error(f"Failed to cleanup expired cache: {e}")
        
        return removed_count


# Global cache manager instance
cache_manager = CacheManager()