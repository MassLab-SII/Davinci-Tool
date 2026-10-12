"""Coverage guarantee scheduler for tool curriculum learning.

Implements hard constraints to ensure all tools get coverage regardless of model preferences:
- Deadline enforcement: Force anchor补齐 when approaching deadline
- Underused boosting: Increase sampling weight for low-coverage tools
- Anti-repeat hint: Generate prompts encouraging novel tool usage
"""

import logging
import random
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set, Tuple
from datetime import datetime

from ..utils.config import ToolCurriculumConfig
from .coverage import CoverageTracker
from .sampler import StageAwareSampler, SamplingResult

logger = logging.getLogger(__name__)


@dataclass
class CoverageDeadlineStatus:
    """Status of coverage deadline enforcement."""

    deadline_episode: int  # Episode number when deadline applies
    target_coverage_ratio: float  # Target coverage ratio (e.g., 0.8)
    current_episode: int  # Current episode number
    current_coverage_ratio: float  # Current coverage ratio
    uncovered_tools: List[str]  # Tools that haven't reached min_success
    undercovered_tools: List[str]  # Tools below average coverage
    is_behind_schedule: bool  # Whether we're behind the deadline
    episodes_remaining: int  # Episodes left until deadline
    tools_needed_per_episode: float  # Avg new tools needed per remaining episode

    def to_dict(self) -> Dict[str, Any]:
        return {
            "deadline_episode": self.deadline_episode,
            "target_coverage_ratio": self.target_coverage_ratio,
            "current_episode": self.current_episode,
            "current_coverage_ratio": self.current_coverage_ratio,
            "uncovered_tools_count": len(self.uncovered_tools),
            "undercovered_tools_count": len(self.undercovered_tools),
            "is_behind_schedule": self.is_behind_schedule,
            "episodes_remaining": self.episodes_remaining,
            "tools_needed_per_episode": self.tools_needed_per_episode,
        }


@dataclass
class CoverageBoost:
    """Boosted sampling weights for underused tools."""

    original_weights: Dict[str, float]
    boosted_weights: Dict[str, float]
    boost_factor_applied: float
    tools_boosted: List[str]


class CoverageScheduler:
    """Scheduler that enforces coverage guarantees across episodes.

    Works alongside StageAwareSampler to ensure:
    1. All tools reach minimum coverage by deadline
    2. Low-coverage tools get prioritized in anchor selection
    3. Anti-repeat hints discourage model from over-using favorite tools
    """

    def __init__(
        self,
        config: ToolCurriculumConfig,
        coverage_tracker: CoverageTracker,
        total_episodes: int,
        coverage_deadline_ratio: float = 0.8,
        coverage_deadline_episode_ratio: float = 0.8,
        boost_underused_factor: float = 3.0,
        max_repeat_action_count: int = 2,
    ):
        """Initialize coverage scheduler.

        Args:
            config: Tool curriculum configuration
            coverage_tracker: Coverage tracker instance
            total_episodes: Total planned episodes for this run
            coverage_deadline_ratio: Target coverage ratio (0.8 = 80% of tools covered)
            coverage_deadline_episode_ratio: Deadline as ratio of total episodes (0.8 = at 80%)
            boost_underused_factor: How much to boost underused tools (3.0 = 3x weight)
            max_repeat_action_count: Max times to allow same action in hints (2 = warn after 2)
        """
        self.config = config
        self.coverage = coverage_tracker
        self.total_episodes = total_episodes
        self.coverage_deadline_ratio = coverage_deadline_ratio
        self.coverage_deadline_episode = int(
            total_episodes * coverage_deadline_episode_ratio
        )
        self.boost_factor = boost_underused_factor
        self.max_repeat_count = max_repeat_action_count

        # Track current episode
        self._current_episode = 0

        # Track recent tool usage for anti-repeat hints
        self._recent_tool_usage: Dict[str, int] = {}  # tool -> usage count in window
        self._usage_window_size = 10  # Track last N episodes
        self._usage_history: List[Set[str]] = []

        # Force-anchor queue for deadline enforcement
        self._forced_anchor_queue: List[str] = []

        logger.info(
            f"CoverageScheduler initialized: deadline={self.coverage_deadline_episode}/"
            f"{total_episodes} episodes, target={coverage_deadline_ratio:.0%} coverage, "
            f"boost_factor={boost_factor}"
        )

    def advance_episode(self, tools_used: List[str]):
        """Advance to next episode and update tracking.

        Args:
            tools_used: Tools successfully used in the just-completed episode
        """
        self._current_episode += 1

        # Update usage history
        self._usage_history.append(set(tools_used))
        if len(self._usage_history) > self._usage_window_size:
            self._usage_history.pop(0)

        # Recompute recent usage counts
        self._recent_tool_usage = {}
        for episode_tools in self._usage_history:
            for tool in episode_tools:
                self._recent_tool_usage[tool] = self._recent_tool_usage.get(tool, 0) + 1

    def get_deadline_status(self) -> CoverageDeadlineStatus:
        """Get current coverage deadline status.

        Returns:
            CoverageDeadlineStatus with current progress
        """
        summary = self.coverage.get_summary()
        report = self.coverage.get_detailed_report()

        current_coverage = summary.get("coverage_rate", 0.0)
        total_tools = summary.get("total_tools", 0)
        uncovered = report.get("uncovered", [])

        episodes_remaining = max(
            0, self.coverage_deadline_episode - self._current_episode
        )

        # How many tools need to reach coverage before deadline?
        tools_needed = int(total_tools * self.coverage_deadline_ratio) - (
            total_tools - len(uncovered)
        )
        tools_needed_per_episode = tools_needed / max(1, episodes_remaining)

        # Are we behind schedule?
        expected_coverage_by_now = (
            self._current_episode / max(1, self.coverage_deadline_episode)
        ) * self.coverage_deadline_ratio
        is_behind = current_coverage < expected_coverage_by_now

        # Identify undercovered tools (below median)
        coverage_counts = [
            self.coverage.get_success_count(t) for t in self.coverage._coverage.keys()
        ]
        median_count = (
            sorted(coverage_counts)[len(coverage_counts) // 2] if coverage_counts else 0
        )
        undercovered = [
            name
            for name in self.coverage._coverage.keys()
            if self.coverage.get_success_count(name) < median_count
        ]

        return CoverageDeadlineStatus(
            deadline_episode=self.coverage_deadline_episode,
            target_coverage_ratio=self.coverage_deadline_ratio,
            current_episode=self._current_episode,
            current_coverage_ratio=current_coverage,
            uncovered_tools=uncovered,
            undercovered_tools=undercovered,
            is_behind_schedule=is_behind,
            episodes_remaining=episodes_remaining,
            tools_needed_per_episode=tools_needed_per_episode,
        )

    def get_forced_anchors(self, max_anchors: int = 1) -> List[str]:
        """Get tools that must be used as anchors to meet deadline.

        When behind schedule, this returns uncovered tools that should
        be forced as anchors in upcoming episodes.

        Args:
            max_anchors: Maximum anchors to force

        Returns:
            List of tool names to force as anchors
        """
        status = self.get_deadline_status()

        if not status.is_behind_schedule:
            return []

        # Prioritize completely uncovered tools
        candidates = status.uncovered_tools.copy()

        if not candidates:
            # Fall back to undercovered
            candidates = status.undercovered_tools.copy()

        # Shuffle and take max_anchors
        random.shuffle(candidates)
        forced = candidates[:max_anchors]

        if forced:
            logger.info(f"Forcing anchors for coverage: {forced}")

        return forced

    def get_boosted_weights(
        self, tool_names: List[str], original_weights: Optional[Dict[str, float]] = None
    ) -> CoverageBoost:
        """Get boosted sampling weights for underused tools.

        Args:
            tool_names: Tools to compute weights for
            original_weights: Optional existing weights to boost

        Returns:
            CoverageBoost with boosted weights
        """
        # Get coverage-based weights (already inverted: low coverage = high weight)
        if original_weights:
            base_weights = original_weights.copy()
        else:
            base_weights = self.coverage.get_coverage_weights(tool_names, invert=True)

        # Identify tools that need extra boost
        tools_to_boost = []
        min_success = self.config.coverage.min_success_per_tool

        for name in tool_names:
            count = self.coverage.get_success_count(name)
            if count < min_success:
                tools_to_boost.append(name)

        # Apply boost factor to underused tools
        boosted_weights = base_weights.copy()
        for name in tools_to_boost:
            boosted_weights[name] = base_weights.get(name, 1.0) * self.boost_factor

        # Normalize weights
        total = sum(boosted_weights.values())
        if total > 0:
            boosted_weights = {k: v / total for k, v in boosted_weights.items()}

        return CoverageBoost(
            original_weights=base_weights,
            boosted_weights=boosted_weights,
            boost_factor_applied=self.boost_factor,
            tools_boosted=tools_to_boost,
        )

    def generate_anti_repeat_hint(self, available_tools: List[str]) -> Optional[str]:
        """Generate an anti-repeat hint to encourage novel tool usage.

        Inspired by AgentEvolver's StateRecorder approach.

        Args:
            available_tools: Tools available in current episode

        Returns:
            Hint text to inject into prompt, or None if not needed
        """
        if not self._recent_tool_usage:
            return None

        # Find over-used tools
        overused = []
        underused = []

        for tool in available_tools:
            count = self._recent_tool_usage.get(tool, 0)

            if count >= self.max_repeat_count:
                overused.append(tool)
            elif count == 0:
                underused.append(tool)

        if not overused and not underused:
            return None

        # Build hint
        hint_parts = []

        if underused:
            sample_underused = random.sample(underused, min(3, len(underused)))
            hint_parts.append(
                f"Consider using tools you haven't tried recently: {', '.join(sample_underused)}."
            )

        if overused:
            hint_parts.append(
                f"You've used {', '.join(overused[:2])} frequently. "
                f"Try different tools for variety."
            )

        hint_parts.append("Avoid repeating the same low-value actions more than twice.")

        return " ".join(hint_parts)

    def adjust_sampling(
        self, sampler: StageAwareSampler, base_result: SamplingResult
    ) -> SamplingResult:
        """Adjust a sampling result based on coverage schedule.

        This is called after the base sampler produces a result,
        and may modify it to enforce coverage guarantees.

        Args:
            sampler: The base sampler
            base_result: Initial sampling result

        Returns:
            Adjusted SamplingResult (may have forced anchors)
        """
        status = self.get_deadline_status()

        # If not behind schedule, return as-is
        if not status.is_behind_schedule:
            return base_result

        # Get forced anchors
        forced = self.get_forced_anchors(max_anchors=1)

        if not forced:
            return base_result

        # Check if forced anchor is already in result
        existing_anchors = set(base_result.anchors)
        new_anchors = [a for a in forced if a not in existing_anchors]

        if not new_anchors:
            return base_result

        # Add forced anchor to result
        new_anchor = new_anchors[0]

        # Ensure tool is in exposed set
        exposed_names = {
            t.get("name") or t.get("function", {}).get("name", "")
            for t in base_result.exposed_tools
        }

        if new_anchor not in exposed_names:
            # Add the tool to exposed set
            if new_anchor in sampler._tool_map:
                base_result.exposed_tools.append(sampler._tool_map[new_anchor])
                base_result.anchor_tools_used.append(new_anchor)

        # Add to anchors list
        base_result.anchors = list(set(base_result.anchors) | {new_anchor})

        logger.info(
            f"Adjusted sampling: forced anchor {new_anchor} for coverage deadline, "
            f"now {len(base_result.anchors)} anchors"
        )

        return base_result

    def get_coverage_report(self) -> Dict[str, Any]:
        """Get comprehensive coverage scheduling report."""
        status = self.get_deadline_status()
        coverage_report = self.coverage.get_detailed_report()

        return {
            "deadline_status": status.to_dict(),
            "coverage_summary": coverage_report["summary"],
            "recent_usage_window": self._usage_window_size,
            "current_episode": self._current_episode,
            "total_episodes": self.total_episodes,
            "top_used_recently": sorted(
                self._recent_tool_usage.items(), key=lambda x: x[1], reverse=True
            )[:10],
            "unused_recently": [
                t
                for t in self.coverage._coverage.keys()
                if t not in self._recent_tool_usage
            ][:10],
        }


def create_anti_repeat_system_prompt_suffix(
    available_tools: List[str], recent_usage: Dict[str, int], max_repeat: int = 2
) -> str:
    """Create a system prompt suffix encouraging novel tool usage.

    This can be appended to the exploration system prompt.

    Args:
        available_tools: List of available tool names
        recent_usage: Dict of tool -> recent usage count
        max_repeat: Threshold for "overused"

    Returns:
        Prompt suffix string
    """
    overused = [t for t in available_tools if recent_usage.get(t, 0) >= max_repeat]
    underused = [t for t in available_tools if recent_usage.get(t, 0) == 0]

    if not overused and not underused:
        return ""

    lines = ["\n\n## Exploration Guidelines"]

    if underused:
        sample = random.sample(underused, min(3, len(underused)))
        lines.append(
            f"- Prioritize exploring these underused tools: {', '.join(sample)}"
        )

    if overused:
        lines.append(f"- Avoid over-relying on: {', '.join(overused[:3])}")

    lines.append("- Do not repeat the same unsuccessful action more than 2 times")
    lines.append("- Prefer novel actions that reveal new information or make progress")

    return "\n".join(lines)
