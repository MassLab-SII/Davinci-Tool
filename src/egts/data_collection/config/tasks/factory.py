from __future__ import annotations

from typing import Any, Dict, Type

from .base import BaseTaskConfig
from .filesystem import FilesystemTaskConfig
from .playwright import PlaywrightTaskConfig
from .postgres import PostgresTaskConfig


TASK_CONFIG_REGISTRY: Dict[str, Type[BaseTaskConfig]] = {
    "filesystem": FilesystemTaskConfig,
    "playwright": PlaywrightTaskConfig,
    "postgres": PostgresTaskConfig,
}


def register_task_config(task_type: str, config_class: Type[BaseTaskConfig]) -> None:
    """Register a task config class for a task_type."""
    TASK_CONFIG_REGISTRY[str(task_type)] = config_class


def get_task_config_class(task_type: str | None) -> Type[BaseTaskConfig]:
    """Return the registered config class, or BaseTaskConfig for unknown types."""
    if not task_type:
        return FilesystemTaskConfig
    return TASK_CONFIG_REGISTRY.get(str(task_type), BaseTaskConfig)


def build_task_config(task: BaseTaskConfig | Dict[str, Any] | None) -> BaseTaskConfig:
    """Build a typed task config from raw config data.

    Known task types keep their specialized defaults. Unknown task types fall back
    to BaseTaskConfig with `extra=allow`, so new benchmark worlds can be declared
    in config without touching the central task union.
    """
    if task is None:
        return FilesystemTaskConfig()
    if isinstance(task, BaseTaskConfig):
        return task
    if not isinstance(task, dict):
        raise TypeError(f"Unsupported task config payload: {type(task)}")

    task_type = task.get("task_type", "filesystem")
    config_class = get_task_config_class(task_type)
    return config_class(**task)
