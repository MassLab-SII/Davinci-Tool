"""Prompt management for MCP-Trajs2Data.

The runtime prompt system is one shared executable-world prompt set under this
package. Files are split by pipeline function, not by world/domain.
"""

from .loader import PromptLoader
from . import trajectory_fallback

__all__ = ["PromptLoader", "trajectory_fallback"]
