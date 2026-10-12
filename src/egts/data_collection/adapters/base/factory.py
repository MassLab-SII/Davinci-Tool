from typing import Any
import logging
from .diff_interpreter import DiffInterpreter

logger = logging.getLogger(__name__)


class DiffInterpreterFactory:
    """Factory for creating diff interpreters.

    Always returns a ``FilesystemDiffInterpreter``, which auto-detects the
    diff type via duck-typing: file-level detail (``created`` / ``deleted`` /
    ``modified`` / ``moved`` lists) for ``FilesystemDiff``, or tool-call
    inference for hash-based diffs like ``_WorldStateDiff``.
    """

    @staticmethod
    def create(task_config) -> DiffInterpreter:
        from data_collection.adapters.filesystem.diff_interpreter import (
            FilesystemDiffInterpreter,
        )
        return FilesystemDiffInterpreter()
