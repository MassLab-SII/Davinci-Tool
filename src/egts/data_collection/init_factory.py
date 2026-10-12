from typing import Any, Optional
from pathlib import Path
import logging
from dataclasses import dataclass
from .state.filesystem_init_generator import (
    FilesystemInitGenerator,
    SizeProfile,
    InitPlan,
)
from .adapters.base.interfaces import EnvInitGenerator

logger = logging.getLogger(__name__)


class FilesystemInitGeneratorAdapter(EnvInitGenerator):
    """Adapter for FilesystemInitGenerator."""

    def __init__(self, seed: Optional[int] = None):
        self.generator = FilesystemInitGenerator(seed=seed)

    def generate_init_plan(self, root: str, size_profile: str) -> InitPlan:
        # Convert string profile to enum
        profile_enum = SizeProfile(size_profile)
        return self.generator.generate_init_plan(root, profile_enum)


class EnvInitGeneratorFactory:
    """Factory for creating environment initialization generators."""

    @staticmethod
    def create(task_config) -> EnvInitGenerator:
        """Create a generator based on task configuration.

        Known task types get their specialized generator. Unknown task types
        fall back to FilesystemInitGeneratorAdapter as a safe default.
        """
        from .config.tasks.filesystem import FilesystemTaskConfig

        if isinstance(task_config, FilesystemTaskConfig):
            return FilesystemInitGeneratorAdapter(seed=task_config.seed_base)

        # For unknown task types, try to use the server adapter's init_generator
        # (which is resolved via server_manager.get_adapters in main.py).
        # Here we provide a safe fallback.
        seed = getattr(task_config, "seed_base", None)
        logger.info(
            f"EnvInitGeneratorFactory: no specialized generator for task_type="
            f"'{getattr(task_config, 'task_type', '?')}', using filesystem fallback"
        )
        return FilesystemInitGeneratorAdapter(seed=seed)
