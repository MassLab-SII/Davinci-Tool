"""Efficiency monitoring for data collection pipeline.

Implements PRD 4.5: "Phase1/2 这类困难阶段，在给定 num_iterations 下的
saved_episodes 不应过低（例如 <10% 需触发策略降难度）"
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class AdjustmentAction(str, Enum):
    """Actions that can be taken to improve efficiency."""

    NONE = "none"
    REDUCE_TARGET_N = "reduce_target_n"
    INCREASE_MAX_FAILURES = "increase_max_failures"
    SWITCH_TO_EASIER_PHASE = "switch_to_easier_phase"


@dataclass
class EfficiencyStats:
    """Efficiency statistics for a monitoring window."""

    attempted: int
    saved: int
    filtered: int
    deduped: int
    success_rate: float
    is_below_threshold: bool
    recommended_action: AdjustmentAction
    current_target_n: int
    adjusted_target_n: Optional[int] = None

    def to_dict(self) -> Dict:
        return {
            "attempted": self.attempted,
            "saved": self.saved,
            "filtered": self.filtered,
            "deduped": self.deduped,
            "success_rate": round(self.success_rate, 3),
            "is_below_threshold": self.is_below_threshold,
            "recommended_action": self.recommended_action.value,
            "current_target_n": self.current_target_n,
            "adjusted_target_n": self.adjusted_target_n,
        }


class EfficiencyMonitor:
    """Monitors data collection efficiency and suggests adjustments.

    PRD 4.5: Tracks attempted, saved, filtered, deduped episodes
    and triggers strategy adjustments when efficiency is low.
    """

    def __init__(
        self,
        min_success_rate: float = 0.1,
        window_size: int = 20,
        auto_adjust: bool = True,
        reduce_target_n: bool = True,
        target_n_reduction_step: int = 1,
        min_target_n: int = 1,
    ):
        """Initialize efficiency monitor.

        Args:
            min_success_rate: Minimum acceptable success rate (0-1)
            window_size: Rolling window size for rate calculation
            auto_adjust: Whether to automatically adjust parameters
            reduce_target_n: Whether reducing target_n is allowed
            target_n_reduction_step: How much to reduce target_n
            min_target_n: Minimum allowed target_n
        """
        self.min_success_rate = min_success_rate
        self.window_size = window_size
        self.auto_adjust = auto_adjust
        self.reduce_target_n = reduce_target_n
        self.target_n_reduction_step = target_n_reduction_step
        self.min_target_n = min_target_n

        # Rolling window of results (True=saved, False=filtered)
        self._results: deque = deque(maxlen=window_size)

        # Counters
        self._total_attempted = 0
        self._total_saved = 0
        self._total_filtered = 0
        self._total_deduped = 0
        self._total_salvaged = 0  # New: Track salvaged episodes

        # Tool & Step Metrics (PRD 4.5)
        self._total_tool_calls = 0
        self._successful_tool_calls = 0
        self._failed_tool_calls = 0
        self._total_steps = 0

        # Recovery Metrics
        self._total_checkpoints = 0
        self._total_rollbacks = 0

        # Token Metrics (PRD: Cost Monitoring)
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_tokens = 0

        # Timing
        self._start_time = 0.0  # Will be set on first use or explicit start

        # Current adjusted target_n (None = no adjustment)
        self._adjusted_target_n: Optional[int] = None

        logger.info(
            f"EfficiencyMonitor initialized: min_rate={min_success_rate:.1%}, "
            f"window={window_size}, auto_adjust={auto_adjust}"
        )

    def record_attempt(
        self,
        saved: bool,
        filtered: bool = False,
        deduped: bool = False,
        salvaged: bool = False,
    ):
        """Record an episode attempt result.

        Args:
            saved: Whether the episode was saved
            filtered: Whether it was filtered (quality/hard filter)
            deduped: Whether it was deduplicated
            salvaged: Whether it was saved via salvage mechanism
        """
        self._total_attempted += 1
        self._results.append(saved)

        if saved:
            self._total_saved += 1
            if salvaged:
                self._total_salvaged += 1
        elif filtered:
            self._total_filtered += 1
        elif deduped:
            self._total_deduped += 1

    def record_tool_stats(self, successful: int, failed: int, total_steps: int):
        """Record tool usage statistics from an episode."""
        self._successful_tool_calls += successful
        self._failed_tool_calls += failed
        self._total_tool_calls += successful + failed
        self._total_steps += total_steps

    def record_recovery_stats(self, checkpoints: int, rollbacks: int):
        """Record recovery statistics from an episode."""
        self._total_checkpoints += checkpoints
        self._total_rollbacks += rollbacks

    def record_token_usage(self, prompt_tokens: int, completion_tokens: int):
        """Record token usage from an episode."""
        self._total_input_tokens += prompt_tokens
        self._total_output_tokens += completion_tokens
        self._total_tokens += prompt_tokens + completion_tokens

    def get_stats(self, current_target_n: int) -> EfficiencyStats:
        """Get current efficiency statistics.

        Args:
            current_target_n: Current target_n setting

        Returns:
            EfficiencyStats with current metrics and recommendations
        """
        window_saved = sum(self._results)
        window_total = len(self._results)

        if window_total == 0:
            success_rate = 1.0  # No data yet, assume good
        else:
            success_rate = window_saved / window_total

        is_below = success_rate < self.min_success_rate

        # Determine recommended action
        action = AdjustmentAction.NONE
        adjusted_n = None

        if is_below and self.auto_adjust:
            if self.reduce_target_n and current_target_n > self.min_target_n:
                action = AdjustmentAction.REDUCE_TARGET_N
                adjusted_n = max(
                    self.min_target_n, current_target_n - self.target_n_reduction_step
                )
                self._adjusted_target_n = adjusted_n

        return EfficiencyStats(
            attempted=self._total_attempted,
            saved=self._total_saved,
            filtered=self._total_filtered,
            deduped=self._total_deduped,
            success_rate=success_rate,
            is_below_threshold=is_below,
            recommended_action=action,
            current_target_n=current_target_n,
            adjusted_target_n=adjusted_n,
        )

    def get_adjusted_target_n(self, original_target_n: int) -> int:
        """Get the adjusted target_n if efficiency is low.

        Args:
            original_target_n: Original target_n from sampling

        Returns:
            Adjusted target_n (may be lower if efficiency is low)
        """
        if self._adjusted_target_n is not None:
            return min(original_target_n, self._adjusted_target_n)
        return original_target_n

    def reset_adjustment(self):
        """Reset the target_n adjustment (e.g., after improvement)."""
        self._adjusted_target_n = None
        logger.info("EfficiencyMonitor: reset target_n adjustment")

    def check_and_reset_on_improvement(self, consecutive_successes: int = 5):
        """Check if we should reset adjustment based on improvement.

        Args:
            consecutive_successes: Number of consecutive saves to reset
        """
        if self._adjusted_target_n is None:
            return

        # Check last N results
        if len(self._results) >= consecutive_successes:
            recent = list(self._results)[-consecutive_successes:]
            if all(recent):
                self.reset_adjustment()
                logger.info(
                    f"EfficiencyMonitor: {consecutive_successes} consecutive successes, resetting adjustment"
                )

    def get_summary(self) -> Dict:
        """Get summary statistics."""
        window_saved = sum(self._results)
        window_total = len(self._results)

        overall_success_rate = self._total_saved / max(1, self._total_attempted)
        window_success_rate = window_saved / max(1, window_total)

        return {
            # Flat structure for main.py compatibility
            "total_attempted": self._total_attempted,
            "total_saved": self._total_saved,
            "total_filtered": self._total_filtered,
            "total_deduped": self._total_deduped,
            "overall_success_rate": overall_success_rate,
            "window_success_rate": window_success_rate,
            "current_adjustment": self._adjusted_target_n,
            # Detailed nested structure
            "episodes": {
                "attempted": self._total_attempted,
                "saved": self._total_saved,
                "salvaged": self._total_salvaged,
                "filtered": self._total_filtered,
                "deduped": self._total_deduped,
                "success_rate": f"{overall_success_rate:.1%}",
            },
            "tools": {
                "total": self._total_tool_calls,
                "successful": self._successful_tool_calls,
                "failed": self._failed_tool_calls,
                "success_rate": f"{self._successful_tool_calls / max(1, self._total_tool_calls):.1%}",
            },
            "recovery": {
                "checkpoints": self._total_checkpoints,
                "rollbacks": self._total_rollbacks,
            },
            "tokens": {
                "total": self._total_tokens,
                "input": self._total_input_tokens,
                "output": self._total_output_tokens,
                "avg_per_episode": int(
                    self._total_tokens / max(1, self._total_attempted)
                ),
                "avg_per_success": int(self._total_tokens / max(1, self._total_saved)),
            },
            "window": {
                "size": self.window_size,
                "success_rate": f"{window_success_rate:.1%}",
                "current_adjustment": self._adjusted_target_n,
            },
        }
