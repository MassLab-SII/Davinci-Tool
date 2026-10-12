"""
Postgres State Manager for mcp-gen
===================================

Manages PostgreSQL state for local mode problem generation and execution.
Creates temporary databases for each iteration with cleanup.
"""

import os
import subprocess
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path

from ..base import BaseStateManager

logger = logging.getLogger(__name__)


class PostgresStateManager(BaseStateManager):
    """
    Manages PostgreSQL database state for problem generation in local mode.
    
    Creates temporary databases for each problem iteration with proper cleanup.
    Assumes local PostgreSQL is running and configured via environment variables.
    """

    def __init__(
        self,
        host: str = None,
        port: int = None,
        database: str = None,
        username: str = None,
        password: str = None,
    ):
        """Initialize PostgreSQL state manager.
        
        Args:
            host: Database host (default from POSTGRES_HOST env or localhost)
            port: Database port (default from POSTGRES_PORT env or 5433)
            database: Main database name (default from POSTGRES_DATABASE env or postgres)
            username: Database username (default from POSTGRES_USERNAME env or postgres)
            password: Database password (default from POSTGRES_PASSWORD env)
        """
        super().__init__(service_name="postgres")
        
        # Load config from environment or use defaults
        self.host = host or os.getenv("POSTGRES_HOST", "localhost")
        self.port = port or int(os.getenv("POSTGRES_PORT", "5433"))
        self.database = database or os.getenv("POSTGRES_DATABASE", "postgres")
        self.username = username or os.getenv("POSTGRES_USERNAME", "postgres")
        self.password = password or os.getenv("POSTGRES_PASSWORD", "password")
        
        # Track current task database
        self.current_database: Optional[str] = None
        self.created_databases: List[str] = []
        
        # Connection status
        self._initialized = False
        
        logger.info(f"Initialized PostgresStateManager: {self.username}@{self.host}:{self.port}")

    def initialize(self, **kwargs) -> bool:
        """Initialize postgres connection and verify access.
        
        Returns:
            True if initialization successful
        """
        try:
            import psycopg2
            
            # Test connection
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.username,
                password=self.password,
                database=self.database
            )
            conn.close()
            
            self._initialized = True
            logger.info(f"✓ PostgreSQL connection verified: {self.host}:{self.port}")
            return True
            
        except ImportError:
            logger.error("psycopg2 not installed. Run: pip install psycopg2-binary")
            return False
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            return False

    def setup_environment(self, problem_context: Dict[str, Any]) -> Dict[str, Any]:
        """Create temporary database for this problem.
        
        Args:
            problem_context: Context about the problem being generated
                - iteration: Current iteration number
                - mcp_server: MCP server name  
                - category: Optional problem category
                
        Returns:
            Dictionary with environment configuration
        """
        try:
            import psycopg2
            from psycopg2 import sql
            
            # Generate unique database name
            iteration = problem_context.get("iteration", 0)
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            db_name = f"mcpgen_{iteration:06d}_{timestamp}"
            
            # Create database
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.username,
                password=self.password,
                database="postgres"
            )
            conn.autocommit = True
            
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name))
                )
            conn.close()
            
            self.current_database = db_name
            self.created_databases.append(db_name)
            
            # Track for cleanup
            self.track_resource(
                resource_type="database",
                identifier=db_name,
                metadata={"iteration": iteration}
            )
            
            logger.info(f"✓ Created temporary database: {db_name}")
            
            # Build DATABASE_URL
            database_url = f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{db_name}"
            os.environ["DATABASE_URL"] = database_url
            os.environ["DATABASE_URI"] = database_url
            logger.info(f"✓ Set DATABASE_URL: {database_url}")
            
            return {
                "database": db_name,
                "database_url": database_url,
                "host": self.host,
                "port": self.port,
                "username": self.username,
                "password": self.password
            }
            
        except Exception as e:
            logger.error(f"Failed to setup postgres environment: {e}")
            return {}

    def get_server_config(self) -> Dict[str, Any]:
        """Get postgres MCP server configuration.
        
        Returns:
            Dictionary with server-specific configuration
        """
        db = self.current_database or self.database
        database_url = f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{db}"
        
        return {
            "database": db,
            "database_url": database_url,
            "host": self.host,
            "port": self.port
        }

    def cleanup(self, keep_on_failure: bool = False) -> bool:
        """Clean up postgres resources.
        
        Args:
            keep_on_failure: If True, preserve database for debugging
        
        Returns:
            True if cleanup successful
        """
        try:
            cleanup_success = True
            
            if not keep_on_failure and self.current_database:
                if not self._drop_database(self.current_database):
                    cleanup_success = False
                else:
                    self.created_databases = [
                        db for db in self.created_databases 
                        if db != self.current_database
                    ]
            elif keep_on_failure:
                logger.info(f"Preserving database for debugging: {self.current_database}")
            
            # Clean up all tracked resources
            if not self._cleanup_tracked_resources():
                cleanup_success = False
            
            self.current_database = None
            return cleanup_success
            
        except Exception as e:
            logger.error(f"Postgres cleanup failed: {e}")
            return False

    def _cleanup_single_resource(self, resource: Dict[str, Any]) -> bool:
        """Clean up a single tracked resource.
        
        Args:
            resource: Resource dictionary with type, id, and metadata
            
        Returns:
            True if cleanup successful
        """
        if resource["type"] == "database":
            return self._drop_database(resource["id"])
        return True

    def _drop_database(self, db_name: str) -> bool:
        """Drop a database.
        
        Args:
            db_name: Database name to drop
            
        Returns:
            True if successful
        """
        try:
            import psycopg2
            from psycopg2 import sql
            
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.username,
                password=self.password,
                database="postgres"
            )
            conn.autocommit = True
            
            with conn.cursor() as cur:
                # Terminate connections to the database
                cur.execute(
                    sql.SQL("""
                        SELECT pg_terminate_backend(pid)
                        FROM pg_stat_activity
                        WHERE datname = %s AND pid <> pg_backend_pid()
                    """),
                    (db_name,)
                )
                
                # Drop database
                cur.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(
                        sql.Identifier(db_name)
                    )
                )
            conn.close()
            
            logger.info(f"✓ Dropped database: {db_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to drop database {db_name}: {e}")
            return False

    def run_verification_script(
        self,
        script_content: str,
        work_dir: Path,
        python_executable: str = "python3",
        timeout: int = 60
    ) -> tuple[bool, str]:
        """Run verification script with database access.
        
        Args:
            script_content: Python script content
            work_dir: Working directory for script
            python_executable: Python interpreter path
            timeout: Execution timeout in seconds
            
        Returns:
            Tuple of (success, output/error message)
        """
        try:
            # Write verification script
            verify_path = work_dir / "verify.py"
            verify_path.write_text(script_content)
            verify_path.chmod(0o755)
            
            # Set up environment with database connection
            env = os.environ.copy()
            if self.current_database:
                env["POSTGRES_HOST"] = self.host
                env["POSTGRES_PORT"] = str(self.port)
                env["POSTGRES_DATABASE"] = self.current_database
                env["POSTGRES_USERNAME"] = self.username
                env["POSTGRES_PASSWORD"] = self.password
                env["DATABASE_URL"] = f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.current_database}"
            
            # Run verification script
            result = subprocess.run(
                [python_executable, str(verify_path), str(work_dir)],
                cwd=str(work_dir),
                env=env,
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
