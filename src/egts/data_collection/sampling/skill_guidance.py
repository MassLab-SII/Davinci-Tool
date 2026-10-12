"""Skill guidance injector for detecting off-track exploration and nudging the
model back toward the expected skill workflow.

Works alongside SkillCompletionDetector (which decides *when* a skill is done)
and ExplorationStateRecorder (which prevents *tool-level* repetition). This
module adds *workflow-level* drift detection with progressive intervention:

  - 2 consecutive off-track steps → mild nudge
  - 4 consecutive off-track steps → moderate reminder (remaining steps)
  - 6 consecutive off-track steps → force re-inject full SKILL.md
  - 8+ steps → stop intervening, let max_steps_per_skill handle it

A step is "off-track" when the tool used is NOT in the set of expected
step tools extracted from the SKILL.md workflow.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class SkillGuidanceInjector:
    """Per-skill guidance injector that detects drift and provides nudges.

    An instance is created for each skill in the sequential exposure pipeline.
    Call ``record_step(tool_name)`` after every successful tool execution, then
    call ``get_guidance()`` to receive an optional user-message string to inject.
    """

    def __init__(
        self,
        skill_id: str,
        step_tools: List[str],
        skill_content: str,
        mild_threshold: int = 2,
        medium_threshold: int = 4,
        force_threshold: int = 6,
        stop_threshold: int = 8,
    ):
        """Initialize guidance injector for a single skill.

        Args:
            skill_id: Current skill identifier.
            step_tools: Ordered list of tools expected per workflow step
                        (from ``SkillCompletionDetector.extract_step_tools``).
            skill_content: Raw SKILL.md content for force re-injection.
            mild_threshold: Off-track steps before mild nudge.
            medium_threshold: Off-track steps before moderate reminder.
            force_threshold: Off-track steps before full SKILL.md re-injection.
            stop_threshold: Off-track steps at which intervention stops.
        """
        self.skill_id = skill_id
        self.step_tools = step_tools
        self.skill_content = skill_content
        self.mild_threshold = mild_threshold
        self.medium_threshold = medium_threshold
        self.force_threshold = force_threshold
        self.stop_threshold = stop_threshold

        # Runtime state
        self.off_track_count: int = 0
        self.total_steps: int = 0
        self.expected_tools_set: Set[str] = set(step_tools) if step_tools else set()
        self.used_expected_tools: Set[str] = set()

        # Track recent tools for repetition-aware diagnostics
        self.recent_tools: List[str] = []

        # Track which intervention levels have been applied (avoid re-injecting
        # the same level over and over; only inject when crossing a threshold)
        self._last_injected_level: int = -1

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_step(self, tool_name: str) -> None:
        """Record a step's tool usage and update off-track counter.

        Args:
            tool_name: Name of the tool just executed.
        """
        self.total_steps += 1
        self.recent_tools.append(tool_name)
        if len(self.recent_tools) > 5:
            self.recent_tools = self.recent_tools[-5:]

        if not self.expected_tools_set:
            # No step tools to compare against — can't detect drift
            self.off_track_count = 0
            return

        if tool_name in self.expected_tools_set:
            self.used_expected_tools.add(tool_name)
            if self.off_track_count > 0:
                logger.debug(
                    "Skill %s: back on track after %d off-track steps (tool=%s)",
                    self.skill_id,
                    self.off_track_count,
                    tool_name,
                )
            self.off_track_count = 0
            self._last_injected_level = -1
        else:
            self.off_track_count += 1
            logger.debug(
                "Skill %s: off-track step %d (tool=%s not in expected set)",
                self.skill_id,
                self.off_track_count,
                tool_name,
            )

    def get_guidance(self) -> Optional[str]:
        """Get a guidance message for the current off-track state.

        Returns:
            A user-message string ready for injection, or None if no
            intervention is needed yet.
        """
        if self.off_track_count < self.mild_threshold:
            return None
        if self.off_track_count >= self.stop_threshold:
            # Stop intervening — max_steps_per_skill will force-complete
            return None

        # Determine which level this off_track_count falls into
        level = self._current_level()
        if level <= self._last_injected_level:
            # Already injected at or above this level — don't repeat
            return None

        self._last_injected_level = level

        if level == 3:
            return self._build_force_reinject()
        elif level == 2:
            return self._build_medium_nudge()
        else:
            return self._build_mild_nudge()

    def reset(self) -> None:
        """Reset all runtime state for a new skill."""
        self.off_track_count = 0
        self.total_steps = 0
        self.used_expected_tools.clear()
        self.recent_tools.clear()
        self._last_injected_level = -1

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _current_level(self) -> int:
        """Map off_track_count to intervention level (1=mild, 2=medium, 3=force)."""
        if self.off_track_count >= self.force_threshold:
            return 3
        elif self.off_track_count >= self.medium_threshold:
            return 2
        else:
            return 1

    def _remaining_expected_tools(self) -> List[str]:
        """Return expected step tools that haven't been used yet."""
        return [t for t in self.step_tools if t not in self.used_expected_tools]

    def _build_mild_nudge(self) -> str:
        from prompts.skill_guided import SKILL_GUIDANCE_MILD_TEMPLATE

        remaining = self._remaining_expected_tools()
        remaining_str = ", ".join(remaining) if remaining else "any remaining steps"
        return SKILL_GUIDANCE_MILD_TEMPLATE.format(
            skill_id=self.skill_id,
            remaining_tools=remaining_str,
        )

    def _build_medium_nudge(self) -> str:
        from prompts.skill_guided import SKILL_GUIDANCE_MEDIUM_TEMPLATE

        remaining = self._remaining_expected_tools()
        remaining_str = ", ".join(remaining) if remaining else "all expected steps covered"
        return SKILL_GUIDANCE_MEDIUM_TEMPLATE.format(
            skill_id=self.skill_id,
            off_track_count=self.off_track_count,
            remaining_tools=remaining_str,
        )

    def _build_force_reinject(self) -> str:
        from prompts.skill_guided import SKILL_GUIDANCE_FORCE_TEMPLATE

        completed = [t for t in self.step_tools if t in self.used_expected_tools]
        remaining = self._remaining_expected_tools()

        completed_str = ", ".join(completed) if completed else "none"
        remaining_str = ", ".join(remaining) if remaining else "all expected steps covered"

        return SKILL_GUIDANCE_FORCE_TEMPLATE.format(
            skill_id=self.skill_id,
            off_track_count=self.off_track_count,
            completed_tools=completed_str,
            remaining_tools=remaining_str,
            skill_content=self.skill_content,
        )


class SkillGuidanceCache:
    """Manages per-skill SkillGuidanceInjector instances across a sequential
    skill exposure episode.

    Usage in the collector::

        # Setup (once per episode)
        guidance_cache = SkillGuidanceCache()
        for sel in skill_selections:
            step_tools = step_tools_cache.get(sel.skill_id, [])
            content = skill_content_cache.get(sel.skill_id, "")
            guidance_cache.register(sel.skill_id, step_tools, content)

        # Per step (after completion check, when skill is NOT completed)
        current_skill_id = skill_selections[current_skill_index].skill_id
        injector = guidance_cache.get(current_skill_id)
        if injector is not None:
            last_tool = _get_last_tool_name(trajectory)
            if last_tool:
                injector.record_step(last_tool)
                guidance_msg = injector.get_guidance()
                if guidance_msg:
                    messages.append({"role": "user", "content": guidance_msg})
    """

    def __init__(self):
        self._injectors: Dict[str, SkillGuidanceInjector] = {}

    def register(
        self, skill_id: str, step_tools: List[str], skill_content: str
    ) -> None:
        """Register a skill for guidance tracking."""
        self._injectors[skill_id] = SkillGuidanceInjector(
            skill_id=skill_id,
            step_tools=step_tools,
            skill_content=skill_content,
        )

    def get(self, skill_id: str) -> Optional[SkillGuidanceInjector]:
        """Get the injector for a skill, or None."""
        return self._injectors.get(skill_id)

    def reset_skill(self, skill_id: str) -> None:
        """Reset guidance state for a specific skill (used on skill transition)."""
        injector = self._injectors.get(skill_id)
        if injector:
            injector.reset()

    def __contains__(self, skill_id: str) -> bool:
        return skill_id in self._injectors

    def __len__(self) -> int:
        return len(self._injectors)
