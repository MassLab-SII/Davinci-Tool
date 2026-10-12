from typing import Any, List, Optional
import logging
from .adapters.base.factory import DiffInterpreterFactory
from .adapters.base.diff_interpreter import IntentSpec, TaskCategory
from .utils.config import SelfQuestioningConfig

logger = logging.getLogger(__name__)


def _inject_legacy_compatibility(spec: IntentSpec) -> IntentSpec:
    """Inject legacy attributes into IntentSpec for backward compatibility.

    The new IntentSpec stores domain-specific changes in the 'changes' dict,
    while the old code expects flattened attributes on the object itself.
    """
    changes = spec.changes or {}

    # Inject attributes expected by old code
    # We map counts directly. Note that directories vs files distinction
    # might be lost if not present in changes dict, defaulting to 0.
    if not hasattr(spec, "files_created"):
        setattr(spec, "files_created", changes.get("created_count", 0))
    if not hasattr(spec, "files_deleted"):
        setattr(spec, "files_deleted", changes.get("deleted_count", 0))
    if not hasattr(spec, "files_modified"):
        setattr(spec, "files_modified", changes.get("modified_count", 0))
    if not hasattr(spec, "files_moved"):
        setattr(spec, "files_moved", changes.get("moved_count", 0))

    if not hasattr(spec, "directories_created"):
        setattr(spec, "directories_created", changes.get("directories_created", 0))
    if not hasattr(spec, "directories_deleted"):
        setattr(spec, "directories_deleted", changes.get("directories_deleted", 0))

    if not hasattr(spec, "affected_directories"):
        setattr(spec, "affected_directories", changes.get("affected_directories", []))
    if not hasattr(spec, "file_types_involved"):
        setattr(spec, "file_types_involved", changes.get("file_types_involved", set()))
    if not hasattr(spec, "naming_patterns"):
        setattr(spec, "naming_patterns", changes.get("naming_patterns", []))

    return spec


def build_intent_spec(
    diff: Any, tool_calls: List[Any], root_path: str, task_config: Optional[Any] = None
) -> IntentSpec:
    """Build intent specification using the appropriate interpreter.

    Args:
        diff: The difference object
        tool_calls: List of tool calls
        root_path: Root context path
        task_config: Task configuration object (required for correct interpreter)

    Returns:
        IntentSpec
    """
    spec = None
    if task_config:
        try:
            interpreter = DiffInterpreterFactory.create(task_config)
            spec = interpreter.interpret(diff, tool_calls, root_path)
        except Exception as e:
            logger.warning(
                f"Failed to use interpreter factory: {e}, falling back to legacy"
            )

    if spec is None:
        # Fallback to legacy filesystem logic if no config provided
        # This maintains backward compatibility during migration
        from .adapters.filesystem.diff_interpreter import FilesystemDiffInterpreter

        spec = FilesystemDiffInterpreter().interpret(diff, tool_calls, root_path)

    return _inject_legacy_compatibility(spec)
