from typing import Any, Dict, List, Optional
import yaml
import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from data_collection.executable_worlds.env_spec import ExecutableWorldEnvSpec

# Re-export from new config structure
from data_collection.config.core import (
    SingleModelConfig,
    DefaultConfig,
    ModelConfig,
    MaaSConfig,
    StdioMCPServerConfig,
    HttpMCPServerConfig,
    PipelineConfig,
    LoggingConfig,
    DockerConfig,
    LocalConfig,
)
from data_collection.config.tasks.filesystem import FilesystemTaskConfig
from data_collection.config.trajs2data import (
    Trajs2DataFiltersConfig,
    DeduplicationConfig,
    DifficultyTierConfig,
    StageConfig,
    AffinityRuleConfig,
    CoverageConfig,
    SkillGuidedConfig,
    ToolCurriculumConfig,
    RecoverableModeConfig,
    ReplayVerificationConfig,
    SelfQuestioningConfig,
    HindsightConfig,
    DataSynthesisConfig,
    ExperienceManagerConfig,
    EfficiencyMonitorConfig,
    Trajs2DataConfig,
)
from data_collection.config.tasks.factory import (
    register_task_config,
    get_task_config_class,
    build_task_config,
    TASK_CONFIG_REGISTRY,
)

# Alias for backward compatibility if needed, though strictly it's replaced
Trajs2DataFilesystemConfig = FilesystemTaskConfig


class Config(BaseModel):
    """Main configuration object."""

    # Model configuration
    maas: MaaSConfig

    # MCP server configurations
    stdio_mcp_servers: Dict[str, StdioMCPServerConfig] = Field(default_factory=dict)
    http_mcp_servers: Dict[str, HttpMCPServerConfig] = Field(default_factory=dict)

    # Optional executable worlds (Docker/Compose stacks exposing MCP over HTTP)
    executable_world_envs: List[ExecutableWorldEnvSpec] = Field(
        default_factory=list,
        description="External executable worlds managed outside the main MCP server registry",
    )
    # Backward-compatible config alias.
    benchmark_envs: List[ExecutableWorldEnvSpec] = Field(default_factory=list)

    # Execution environment
    execution_mode: str = Field(
        default="local", description="Execution mode: 'local' or 'docker'"
    )
    local: LocalConfig = Field(default_factory=LocalConfig)
    docker: DockerConfig = Field(default_factory=DockerConfig)

    # Pipeline settings
    pipeline: PipelineConfig

    # Trajs2Data core configuration
    trajs2data: Trajs2DataConfig = Field(default_factory=Trajs2DataConfig)

    # Logging
    logging: LoggingConfig

    def get_all_servers(self) -> Dict[str, tuple[str, Any]]:
        """Get all servers with their type.

        Returns:
            Dictionary mapping server name to (type, config) tuple
            where type is 'stdio' or 'http'
        """
        servers = {}

        # Add stdio servers
        for name, config in self.stdio_mcp_servers.items():
            servers[name] = ("stdio", config)

        # Add HTTP servers
        for name, config in self.http_mcp_servers.items():
            servers[name] = ("http", config)

        return servers

    @property
    def is_local_mode(self) -> bool:
        """Check if running in local mode (no Docker)."""
        return self.execution_mode == "local"

    @property
    def is_docker_mode(self) -> bool:
        """Check if running in Docker mode."""
        return self.execution_mode == "docker"

    def get_nl_rewrite_model_config(self) -> SingleModelConfig:
        """Get the NL rewrite model config, falling back to trajectory_collection if not specified."""
        if self.maas.models.nl_rewrite:
            return self.maas.models.nl_rewrite
        # Fallback to trajectory_collection model with lower temperature
        tc = self.maas.models.trajectory_collection
        return SingleModelConfig(
            model=tc.model,
            base_url=tc.base_url,
            api_key=tc.api_key,
            temperature=0.7,  # Default for NL rewriting
            max_tokens=tc.max_tokens,
        )


def load_config(config_path: str = "configs/egts/config.yaml") -> Config:
    """Load configuration from YAML file with environment variable substitution.

    Args:
        config_path: Path to the configuration file

    Returns:
        Parsed configuration object
    """
    # Load environment variables from .env file if it exists
    load_dotenv()

    # Read YAML file
    with open(config_path, "r") as f:
        config_dict = yaml.safe_load(f)

    # Substitute environment variables
    config_dict = _substitute_env_vars(config_dict)

    # Normalize MaaS model aliases for synthesis-oriented configs.
    # Accept:
    # - maas.models.judge_model       -> trajectory_collection
    # - maas.models.synthesis_model   -> nl_rewrite
    # This keeps backward compatibility with existing pipeline code.
    if isinstance(config_dict, dict):
        maas_cfg = config_dict.get("maas")
        if isinstance(maas_cfg, dict):
            models_cfg = maas_cfg.get("models")
            if isinstance(models_cfg, dict):
                if (
                    "trajectory_collection" not in models_cfg
                    and "judge_model" in models_cfg
                ):
                    models_cfg["trajectory_collection"] = models_cfg["judge_model"]
                if "nl_rewrite" not in models_cfg and "synthesis_model" in models_cfg:
                    models_cfg["nl_rewrite"] = models_cfg["synthesis_model"]

    # Parse headers from JSON strings in HTTP server configs
    if "http_mcp_servers" in config_dict:
        for server_name, server_config in config_dict["http_mcp_servers"].items():
            if "headers" in server_config and isinstance(server_config["headers"], str):
                import json

                headers_str = server_config["headers"]

                # Handle variable substitution in headers
                headers_str = headers_str.replace('f"', '"').replace("f'", "'")

                try:
                    server_config["headers"] = json.loads(headers_str)
                except json.JSONDecodeError as e:
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.warning(f"Failed to parse headers for {server_name}: {e}")
                    try:
                        server_config["headers"] = eval(headers_str)
                    except Exception:
                        pass

    # Parse executable world envs (if present)
    # Accept either:
    # - executable_world_envs: [ ... ]
    # - benchmark_envs: [ ... ]
    # - executable_worlds: { envs: [ ... ] }
    # - benchmarks: { envs: [ ... ] }
    if isinstance(config_dict, dict):
        if "executable_world_envs" not in config_dict:
            worlds_block = config_dict.get("executable_worlds")
            if isinstance(worlds_block, dict) and "envs" in worlds_block:
                config_dict["executable_world_envs"] = worlds_block.get("envs")

        if "executable_world_envs" not in config_dict and "benchmark_envs" in config_dict:
            config_dict["executable_world_envs"] = config_dict.get("benchmark_envs")

        if "executable_world_envs" not in config_dict:
            benchmarks_block = config_dict.get("benchmarks")
            if isinstance(benchmarks_block, dict) and "envs" in benchmarks_block:
                config_dict["executable_world_envs"] = benchmarks_block.get("envs")

        if "executable_world_envs" in config_dict and isinstance(
            config_dict.get("executable_world_envs"), list
        ):
            # Let Pydantic validate to ExecutableWorldEnvSpec.
            config_dict.setdefault("benchmark_envs", config_dict["executable_world_envs"])
            pass

    # Map legacy configuration to new structure
    if "trajs2data" in config_dict:
        trajs_cfg = config_dict["trajs2data"]
        if "filesystem" in trajs_cfg and "task" not in trajs_cfg:
            fs_cfg = trajs_cfg.pop("filesystem")
            fs_cfg["task_type"] = "filesystem"
            trajs_cfg["task"] = fs_cfg

        # Use factory to build typed task config from raw dict
        if "task" in trajs_cfg and isinstance(trajs_cfg["task"], dict):
            from data_collection.config.tasks.factory import build_task_config
            trajs_cfg["task"] = build_task_config(trajs_cfg["task"])

    config_obj = Config(**config_dict)

    # Auto-register servers declared in config into the server registry
    from data_collection.mcp_servers.server_registry import auto_register_from_config
    auto_register_from_config(config_obj)

    return config_obj


def _substitute_env_vars(config: Any) -> Any:
    """Recursively substitute environment variables in configuration.

    Supports ${VAR_NAME} syntax for environment variable substitution.

    Args:
        config: Configuration dictionary or value

    Returns:
        Configuration with substituted values
    """
    if isinstance(config, dict):
        return {key: _substitute_env_vars(value) for key, value in config.items()}
    elif isinstance(config, list):
        return [_substitute_env_vars(item) for item in config]
    elif isinstance(config, str):
        if config.startswith("${") and config.endswith("}"):
            current = config
            seen = set()
            while current.startswith("${") and current.endswith("}") and current not in seen:
                seen.add(current)
                var_name = current[2:-1]
                resolved = os.getenv(var_name, current)
                if resolved == current:
                    break
                current = resolved
            return current
        return config
    else:
        return config


def get_output_path(config: Config, *parts: str) -> str:
    """Get a path within the output directory.

    Args:
        config: Configuration object
        *parts: Path components to join

    Returns:
        Full path to the output location
    """
    from pathlib import Path

    output_dir = Path(config.pipeline.output_dir)
    return str(output_dir.joinpath(*parts))
