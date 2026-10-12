"""Directory backup utilities for filesystem state management."""

import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class DirectoryBackup:
    """Manage directory backups for verification purposes."""
    
    def __init__(self, base_dir: str):
        """Initialize directory backup manager.
        
        Args:
            base_dir: Base directory for storing backups
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
    def create_backup(self, source_dir: str, backup_name: str) -> str:
        """Create a backup of the source directory.
        
        Args:
            source_dir: Directory to backup
            backup_name: Optional custom backup name (default: timestamp)
            
        Returns:
            Path to the backup directory
        """
        source_path = Path(source_dir)
        
        if not source_path.exists():
            logger.error(f"Source directory does not exist: {source_dir}")
        
        backup_path = self.base_dir / backup_name
        
        # Create backup
        logger.info(f"Creating backup: {source_dir} -> {backup_path}")
        
        try:
            shutil.copytree(source_dir, backup_path, dirs_exist_ok=True)
            logger.info(f"✓ Backup created: {backup_path}")
        
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            raise
        
        return str(backup_path)
    
    def remove_backup(self, backup_path: str):
        """Remove a backup directory.
        
        Args:
            backup_path: Path to the backup to remove
        """
        backup = Path(backup_path)
        
        if backup.exists():
            logger.info(f"Removing backup: {backup_path}")
            shutil.rmtree(backup_path)
            logger.info(f"✓ Backup removed: {backup_path}")
        else:
            logger.warning(f"Backup does not exist: {backup_path}")
    
    def cleanup_old_backups(self, keep_recent: int = 10):
        """Clean up old backups, keeping only the most recent ones.
        
        Args:
            keep_recent: Number of recent backups to keep
        """
        backups = sorted(self.base_dir.glob("backup_*"), key=lambda p: p.stat().st_mtime)
        
        if len(backups) > keep_recent:
            to_remove = backups[:-keep_recent]
            logger.info(f"Cleaning up {len(to_remove)} old backups")
            
            for backup in to_remove:
                self.remove_backup(str(backup))
