"""
Filesystem State Manager for mcp-gen
====================================

Manages filesystem state for local mode problem generation and execution.
Supports backup/restore for environment isolation, and MCP tool-based initialization.
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

from ..base import BaseStateManager

logger = logging.getLogger(__name__)


class FilesystemStateManager(BaseStateManager):
    """
    Manages filesystem state for problem generation in local mode.
    
    Creates isolated workspaces for each problem iteration with backup/restore
    capability for environment isolation.
    """

    def __init__(self, workspace_root: Optional[Path] = None):
        """Initialize filesystem state manager.
        
        Args:
            workspace_root: Root directory for workspaces (defaults to ./workspaces)
        """
        super().__init__(service_name="filesystem")
        
        # Use provided workspace root or default
        if workspace_root:
            self.workspace_root = Path(workspace_root)
        else:
            self.workspace_root = Path("./workspaces-async")
        
        self.current_workspace: Optional[Path] = None
        self.backup_dir: Optional[Path] = None
        self.backup_enabled = True
        
        logger.info(f"Initialized FilesystemStateManager with root: {self.workspace_root}")

    def initialize(self, **kwargs) -> bool:
        """Initialize the filesystem environment.
        
        Ensures the workspace root exists and is accessible.
        
        Returns:
            True if initialization successful
        """
        try:
            # Ensure workspace root directory exists
            self.workspace_root.mkdir(parents=True, exist_ok=True)
            
            # Verify we can write to the directory
            test_file = self.workspace_root / ".mcp_gen_test"
            test_file.write_text("test")
            test_file.unlink()
            
            logger.info(f"✓ Filesystem environment initialized: {self.workspace_root}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize filesystem environment: {e}")
            return False

    def setup_environment(self, problem_context: Dict[str, Any]) -> Dict[str, Any]:
        """Create isolated workspace for this problem.
        
        Args:
            problem_context: Context about the problem being generated
                - iteration: Current iteration number
                - mcp_server: MCP server name  
                - category: Optional problem category
                
        Returns:
            Dictionary with environment configuration
        """
        try:
            # Create workspace name from iteration
            iteration = problem_context.get("iteration", 0)
            workspace_name = f"problem_{iteration:06d}_filesystem"
            
            self.current_workspace = self.workspace_root / workspace_name
            
            # Remove existing workspace if it exists
            if self.current_workspace.exists():
                shutil.rmtree(self.current_workspace)
            
            # Create fresh workspace
            self.current_workspace.mkdir(parents=True, exist_ok=True)
            
            # Track this workspace for cleanup
            self.track_resource(
                resource_type="directory",
                identifier=str(self.current_workspace),
                metadata={"iteration": iteration}
            )
            
            logger.info(f"✓ Created workspace: {self.current_workspace}")
            
            # Set environment variable for MCP server
            os.environ["FILESYSTEM_TEST_DIR"] = str(self.current_workspace)
            
            return {
                "workspace_path": str(self.current_workspace),
                "test_directory": str(self.current_workspace),
                "root_directory": str(self.current_workspace)
            }
            
        except Exception as e:
            logger.error(f"Failed to setup filesystem environment: {e}")
            return {}

    def create_backup(self) -> bool:
        """Create a backup of the current workspace.
        
        Used before trajectory collection to enable restore on failure.
        
        Returns:
            True if backup successful
        """
        if not self.current_workspace or not self.current_workspace.exists():
            logger.warning("No workspace to backup")
            return False
        
        try:
            # Create backup directory
            self.backup_dir = self.current_workspace.parent / f"{self.current_workspace.name}_backup"
            
            # Remove existing backup if it exists
            if self.backup_dir.exists():
                shutil.rmtree(self.backup_dir)
            
            # Copy workspace to backup
            shutil.copytree(self.current_workspace, self.backup_dir)
            
            logger.info(f"✓ Created backup: {self.backup_dir}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return False

    def restore_from_backup(self) -> bool:
        """Restore workspace from backup.
        
        Used to reset environment after failed trajectory.
        
        Returns:
            True if restore successful
        """
        if not self.backup_dir or not self.backup_dir.exists():
            logger.warning("No backup available for restore")
            return False
        
        try:
            # Remove current workspace
            if self.current_workspace and self.current_workspace.exists():
                shutil.rmtree(self.current_workspace)
            
            # Restore from backup
            shutil.copytree(self.backup_dir, self.current_workspace)
            
            logger.info(f"✓ Restored workspace from backup")
            return True
            
        except Exception as e:
            logger.error(f"Failed to restore from backup: {e}")
            return False

    def cleanup_backup(self) -> bool:
        """Clean up backup directory.
        
        Returns:
            True if cleanup successful
        """
        if self.backup_dir and self.backup_dir.exists():
            try:
                shutil.rmtree(self.backup_dir)
                logger.debug(f"Cleaned up backup: {self.backup_dir}")
                self.backup_dir = None
                return True
            except Exception as e:
                logger.error(f"Failed to cleanup backup: {e}")
                return False
        return True

    def get_server_config(self) -> Dict[str, Any]:
        """Get filesystem MCP server configuration.
        
        Returns:
            Dictionary with server-specific configuration
        """
        workspace = str(self.current_workspace) if self.current_workspace else str(self.workspace_root)
        return {
            "root_directory": workspace,
            "allowed_directories": [workspace]
        }

    def cleanup(self, keep_on_failure: bool = False) -> bool:
        """Clean up filesystem resources.
        
        Args:
            keep_on_failure: If True, preserve workspace for debugging
        
        Returns:
            True if cleanup successful
        """
        try:
            cleanup_success = True
            
            # Clean up backup first
            self.cleanup_backup()
            
            # Clean up current workspace (unless preserving for debugging)
            if not keep_on_failure:
                if self.current_workspace and self.current_workspace.exists():
                    try:
                        shutil.rmtree(self.current_workspace)
                        logger.info(f"✓ Cleaned up workspace: {self.current_workspace}")
                    except Exception as e:
                        logger.error(f"Failed to cleanup workspace: {e}")
                        cleanup_success = False
            else:
                logger.info(f"Preserving workspace for debugging: {self.current_workspace}")
            
            # Clean up all tracked resources
            if not self._cleanup_tracked_resources():
                cleanup_success = False
            
            self.current_workspace = None
            return cleanup_success
            
        except Exception as e:
            logger.error(f"Filesystem cleanup failed: {e}")
            return False

    def _cleanup_single_resource(self, resource: Dict[str, Any]) -> bool:
        """Clean up a single tracked resource.
        
        Args:
            resource: Resource dictionary with type, id, and metadata
            
        Returns:
            True if cleanup successful
        """
        if resource["type"] == "directory":
            dir_path = Path(resource["id"])
            if dir_path.exists():
                try:
                    shutil.rmtree(dir_path)
                    logger.debug(f"Cleaned up directory: {dir_path}")
                    return True
                except Exception as e:
                    logger.error(f"Failed to cleanup directory {dir_path}: {e}")
                    return False
        return True

    def get_workspace_path(self) -> Optional[Path]:
        """Get the current workspace path.
        
        Returns:
            Path to current workspace or None if not set up
        """
        return self.current_workspace

    def run_verification_script(
        self,
        script_content: str,
        python_executable: str = "python3",
        timeout: int = 60
    ) -> tuple[bool, str]:
        """Run verification script in the current workspace.
        
        Args:
            script_content: Python script content
            python_executable: Python interpreter path
            timeout: Execution timeout in seconds
            
        Returns:
            Tuple of (success, output/error message)
        """
        if not self.current_workspace:
            return False, "No workspace available"
        
        try:
            # Write verification script
            verify_path = self.current_workspace / "verify.py"
            verify_path.write_text(script_content)
            verify_path.chmod(0o755)
            
            # Run verification script
            result = subprocess.run(
                [python_executable, str(verify_path), str(self.current_workspace)],
                cwd=str(self.current_workspace),
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                logger.info("✓ Verification script passed")
                return True, result.stdout
            else:
                error_msg = f"Exit code {result.returncode}"
                if result.stdout:
                    error_msg += f"\nStdout: {result.stdout}"
                if result.stderr:
                    error_msg += f"\nStderr: {result.stderr}"
                logger.warning(f"✗ Verification failed: {error_msg}")
                return False, error_msg
                
        except subprocess.TimeoutExpired:
            return False, f"Verification timed out after {timeout}s"
        except Exception as e:
            return False, f"Verification error: {e}"
