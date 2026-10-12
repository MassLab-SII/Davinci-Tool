"""Backward-compatible alias for experience-library prompts.

Use `prompts.experience` for new code. This module remains only so older imports
from `prompts.skills` do not break immediately.
"""

from prompts.experience import *  # noqa: F401,F403
