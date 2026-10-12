"""Coverage tracking for tool curriculum learning.

Tracks how many times each tool has been successfully used in valid samples,
enabling balanced coverage across all available tools.
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class CoverageTracker:
    """Tracks tool usage coverage for curriculum learning.

    Maintains per-tool success counts to enable:
    - Balanced sampling (prioritize low-coverage tools)
    - Coverage metrics reporting
    - Persistent state across runs
    - Argument-level coverage tracking (PRD 3.2 Phase 3)
    """

    def __init__(
        self,
        output_dir: Path,
        track_file: str = "coverage.json",
        min_success_per_tool: int = 10,
    ):
        """Initialize coverage tracker.

        Args:
            output_dir: Directory to store coverage tracking file
            track_file: Filename for coverage data
            min_success_per_tool: Minimum successes for a tool to be "covered"
        """
        self.output_dir = Path(output_dir)
        self.track_file = track_file
        self.min_success_per_tool = min_success_per_tool

        # Tool coverage data
        self._coverage: Dict[str, Dict[str, Any]] = {}

        # Argument-level coverage (PRD 3.2 Phase 3)
        # Maps tool_name -> {arg_signature -> count}
        self._arg_coverage: Dict[str, Dict[str, int]] = {}

        # Tool Co-occurrence Matrix (PRD Phase 3)
        # Maps (tool1, tool2) -> count, where tool1 < tool2 (lexicographically)
        self._tool_co_occurrence: Dict[str, int] = {}

        # Thread safety
        self._lock = threading.Lock()

        # Load existing coverage if available
        self._load()

    @property
    def coverage_path(self) -> Path:
        """Get full path to coverage file."""
        return self.output_dir / self.track_file

    def _load(self):
        """Load existing coverage data from disk."""
        try:
            if self.coverage_path.exists():
                with open(self.coverage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._coverage = data.get("tools", {})
                    self._arg_coverage = data.get("arg_coverage", {})
                    # Load co-occurrence with key reconstruction (JSON keys are strings)
                    self._tool_co_occurrence = data.get("tool_co_occurrence", {})

                    logger.info(
                        f"Loaded coverage data for {len(self._coverage)} tools, "
                        f"{sum(len(v) for v in self._arg_coverage.values())} arg patterns"
                    )
        except Exception as e:
            logger.warning(f"Failed to load coverage data: {e}")
            self._coverage = {}
            self._arg_coverage = {}
            self._tool_co_occurrence = {}

    def save(self):
        """Persist coverage data to disk."""
        with self._lock:
            coverage_snapshot = self._coverage.copy()
            arg_coverage_snapshot = {k: v.copy() for k, v in self._arg_coverage.items()}
            co_occurrence_snapshot = self._tool_co_occurrence.copy()

        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)

            data = {
                "last_updated": datetime.now().isoformat(),
                "min_success_per_tool": self.min_success_per_tool,
                "tools": coverage_snapshot,
                "arg_coverage": arg_coverage_snapshot,
                "tool_co_occurrence": co_occurrence_snapshot,
                "summary": self._compute_summary(coverage_snapshot),
            }

            with open(self.coverage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.debug(f"Saved coverage data to {self.coverage_path}")
        except Exception as e:
            logger.error(f"Failed to save coverage data: {e}")

    def _compute_summary(self, coverage: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Compute coverage summary statistics."""
        if not coverage:
            return {"total_tools": 0, "covered_tools": 0, "coverage_rate": 0.0}

        total = len(coverage)
        covered = sum(
            1
            for t in coverage.values()
            if t.get("success_count", 0) >= self.min_success_per_tool
        )
        observed_successful = sum(
            1 for t in coverage.values() if t.get("success_count", 0) > 0
        )

        return {
            "total_tools": total,
            "covered_tools": covered,
            "observed_successful_tools": observed_successful,
            "coverage_rate": covered / total if total > 0 else 0.0,
            "total_successes": sum(
                t.get("success_count", 0) for t in coverage.values()
            ),
            "min_success_per_tool": self.min_success_per_tool,
        }

    def register_tools(self, tool_names: List[str]):
        """Register tools to track (initializes if not present).

        Args:
            tool_names: List of tool names to track
        """
        with self._lock:
            for name in tool_names:
                if name not in self._coverage:
                    self._coverage[name] = {
                        "success_count": 0,
                        "failure_count": 0,
                        "last_used": None,
                        "episodes": [],  # Recent episode IDs
                    }
            logger.debug(f"Registered {len(tool_names)} tools for coverage tracking")

    def record_success(self, tool_name: str, episode_id: str = ""):
        """Record a successful tool use.

        Args:
            tool_name: Name of the tool that was used successfully
            episode_id: Optional episode identifier
        """
        with self._lock:
            if tool_name not in self._coverage:
                self._coverage[tool_name] = {
                    "success_count": 0,
                    "failure_count": 0,
                    "last_used": None,
                    "episodes": [],
                }

            self._coverage[tool_name]["success_count"] += 1
            self._coverage[tool_name]["last_used"] = datetime.now().isoformat()

            # Track recent episodes (keep last 10)
            if episode_id:
                episodes = self._coverage[tool_name].get("episodes", [])
                episodes.append(episode_id)
                self._coverage[tool_name]["episodes"] = episodes[-10:]

    def record_failure(self, tool_name: str):
        """Record a failed tool use.

        Args:
            tool_name: Name of the tool that failed
        """
        with self._lock:
            if tool_name not in self._coverage:
                self._coverage[tool_name] = {
                    "success_count": 0,
                    "failure_count": 0,
                    "last_used": None,
                    "episodes": [],
                }

            self._coverage[tool_name]["failure_count"] += 1

    def record_episode_tools(
        self, tools_used: List[str], successful_tools: List[str], episode_id: str = ""
    ):
        """Record tool usage for an entire episode.

        Args:
            tools_used: All tools that were attempted
            successful_tools: Tools that succeeded
            episode_id: Episode identifier
        """
        successful_set = set(successful_tools)

        for tool in tools_used:
            if tool in successful_set:
                self.record_success(tool, episode_id)
            else:
                self.record_failure(tool)

        if len(successful_tools) >= 2:
            unique_successful = sorted(list(successful_set))
            with self._lock:
                for i in range(len(unique_successful)):
                    for j in range(i + 1, len(unique_successful)):
                        t1 = unique_successful[i]
                        t2 = unique_successful[j]
                        pair_key = f"{t1},{t2}"
                        self._tool_co_occurrence[pair_key] = (
                            self._tool_co_occurrence.get(pair_key, 0) + 1
                        )

    def get_tool_co_occurrence_count(self, tool1: str, tool2: str) -> int:
        """Get co-occurrence count for a pair of tools.

        Args:
            tool1: First tool name
            tool2: Second tool name

        Returns:
            Number of episodes where both tools were used successfully
        """
        t1, t2 = sorted([tool1, tool2])
        pair_key = f"{t1},{t2}"
        with self._lock:
            return self._tool_co_occurrence.get(pair_key, 0)

    def get_low_co_occurrence_pairs(
        self, tool_names: List[str], max_pairs: int = 10
    ) -> List[Tuple[str, str, int]]:
        """Find tool pairs with low co-occurrence counts (for Frontier Exploration).

        Args:
            tool_names: List of available tools
            max_pairs: Maximum number of pairs to return

        Returns:
            List of (tool1, tool2, count) sorted by count ascending
        """
        pairs = []
        # Check all possible pairs of provided tools
        unique_tools = sorted(list(set(tool_names)))

        with self._lock:
            for i in range(len(unique_tools)):
                for j in range(i + 1, len(unique_tools)):
                    t1 = unique_tools[i]
                    t2 = unique_tools[j]
                    pair_key = f"{t1},{t2}"
                    count = self._tool_co_occurrence.get(pair_key, 0)
                    pairs.append((t1, t2, count))

        # Sort by count ascending (prioritize pairs that rarely occur together)
        pairs.sort(key=lambda x: x[2])
        return pairs[:max_pairs]

    def get_success_count(self, tool_name: str) -> int:
        """Get success count for a tool.

        Args:
            tool_name: Tool to check

        Returns:
            Number of successful uses
        """
        with self._lock:
            return self._coverage.get(tool_name, {}).get("success_count", 0)

    def get_low_coverage_tools(
        self, tool_names: List[str], threshold: Optional[int] = None
    ) -> List[str]:
        """Get tools with coverage below threshold.

        Args:
            tool_names: Tools to consider
            threshold: Coverage threshold (default: min_success_per_tool)

        Returns:
            List of low-coverage tool names, sorted by success count ascending
        """
        if threshold is None:
            threshold = self.min_success_per_tool

        with self._lock:
            low_coverage = []
            for name in tool_names:
                count = self._coverage.get(name, {}).get("success_count", 0)
                if count < threshold:
                    low_coverage.append((name, count))

        # Sort by count ascending (lowest first)
        low_coverage.sort(key=lambda x: x[1])
        return [name for name, _ in low_coverage]

    def get_high_coverage_tools(
        self, tool_names: List[str], top_k: int = 5
    ) -> List[str]:
        """Get tools with highest coverage counts.

        Args:
            tool_names: Tools to consider
            top_k: Number of tools to return

        Returns:
            List of high-coverage tool names, sorted by success count descending
        """
        with self._lock:
            high_coverage = []
            for name in tool_names:
                count = self._coverage.get(name, {}).get("success_count", 0)
                if count > 0:
                    high_coverage.append((name, count))

        # Sort by count descending (highest first)
        high_coverage.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in high_coverage[:top_k]]

    def get_coverage_weights(
        self, tool_names: List[str], invert: bool = True
    ) -> Dict[str, float]:
        """Get sampling weights based on coverage (lower coverage = higher weight).

        Args:
            tool_names: Tools to compute weights for
            invert: If True, low coverage -> high weight

        Returns:
            Dict of tool_name -> weight
        """
        with self._lock:
            counts = {
                name: self._coverage.get(name, {}).get("success_count", 0)
                for name in tool_names
            }

        if not counts:
            return {}

        max_count = max(counts.values()) + 1  # +1 to avoid division by zero

        weights = {}
        for name, count in counts.items():
            if invert:
                # Low count -> high weight
                weights[name] = (max_count - count) / max_count
            else:
                # High count -> high weight
                weights[name] = (count + 1) / max_count

        return weights

    def is_covered(self, tool_name: str) -> bool:
        """Check if a tool has reached minimum coverage.

        Args:
            tool_name: Tool to check

        Returns:
            True if tool has reached min_success_per_tool
        """
        return self.get_success_count(tool_name) >= self.min_success_per_tool

    def get_summary(self) -> Dict[str, Any]:
        """Get coverage summary.

        Returns:
            Summary statistics dict
        """
        with self._lock:
            return self._compute_summary(self._coverage)

    def get_detailed_report(self) -> Dict[str, Any]:
        """Get detailed coverage report.

        Returns:
            Full coverage data with summary
        """
        with self._lock:
            coverage_copy = {k: v.copy() for k, v in self._coverage.items()}
            arg_coverage_copy = {k: v.copy() for k, v in self._arg_coverage.items()}

        return {
            "summary": self._compute_summary(coverage_copy),
            "tools": coverage_copy,
            "arg_coverage": arg_coverage_copy,
            "uncovered": [
                name
                for name, data in coverage_copy.items()
                if data.get("success_count", 0) < self.min_success_per_tool
            ],
            "fully_covered": [
                name
                for name, data in coverage_copy.items()
                if data.get("success_count", 0) >= self.min_success_per_tool
            ],
        }

    # =========================================================================
    # Argument-level Coverage (PRD 3.2 Phase 3)
    # =========================================================================

    def record_success_with_args(
        self, tool_name: str, arguments: Dict[str, Any], episode_id: str = ""
    ):
        """Record successful tool use with argument signature tracking.

        This extends record_success() to also track which argument combinations
        have been used, enabling more fine-grained coverage analysis.

        Args:
            tool_name: Name of the tool that was used successfully
            arguments: The arguments passed to the tool
            episode_id: Optional episode identifier
        """
        # Record basic tool success
        self.record_success(tool_name, episode_id)

        # Record argument signature
        arg_sig = self._compute_arg_signature(arguments)

        with self._lock:
            if tool_name not in self._arg_coverage:
                self._arg_coverage[tool_name] = {}

            self._arg_coverage[tool_name][arg_sig] = (
                self._arg_coverage[tool_name].get(arg_sig, 0) + 1
            )

    def _compute_arg_signature(self, arguments: Dict[str, Any]) -> str:
        """Compute a signature for argument combination.

        The signature captures which keys were provided (not their values),
        to track coverage of different argument patterns.

        Args:
            arguments: The arguments dict

        Returns:
            A string signature like "path,recursive" (sorted keys)
        """
        if not arguments:
            return "_empty_"

        # Sort keys for consistent signature
        keys = sorted(arguments.keys())
        return ",".join(keys)

    def get_arg_patterns(self, tool_name: str) -> Dict[str, int]:
        """Get all observed argument patterns for a tool.

        Args:
            tool_name: Tool to check

        Returns:
            Dict of arg_signature -> count
        """
        with self._lock:
            return self._arg_coverage.get(tool_name, {}).copy()

    def get_uncovered_arg_patterns(
        self,
        tool_name: str,
        known_patterns: Optional[List[str]] = None,
        min_count: int = 1,
    ) -> List[str]:
        """Get argument patterns that haven't been sufficiently covered.

        Args:
            tool_name: Tool to check
            known_patterns: Optional list of expected patterns to check against
            min_count: Minimum uses to consider a pattern "covered"

        Returns:
            List of uncovered argument patterns
        """
        with self._lock:
            observed = self._arg_coverage.get(tool_name, {})

        if known_patterns is None:
            # Return patterns with count below threshold
            return [pattern for pattern, count in observed.items() if count < min_count]
        else:
            # Return patterns from known_patterns that haven't been observed enough
            return [
                pattern
                for pattern in known_patterns
                if observed.get(pattern, 0) < min_count
            ]

    def get_arg_coverage_weights(
        self, tool_name: str, known_patterns: List[str]
    ) -> Dict[str, float]:
        """Get sampling weights for argument patterns (lower coverage = higher weight).

        Args:
            tool_name: Tool to get weights for
            known_patterns: List of known argument patterns

        Returns:
            Dict of pattern -> weight
        """
        with self._lock:
            observed = self._arg_coverage.get(tool_name, {})

        if not known_patterns:
            return {}

        counts = {p: observed.get(p, 0) for p in known_patterns}
        max_count = max(counts.values()) + 1

        return {
            pattern: (max_count - count) / max_count
            for pattern, count in counts.items()
        }

    def get_arg_coverage_summary(self) -> Dict[str, Any]:
        """Get summary of argument-level coverage.

        Returns:
            Summary statistics for arg coverage
        """
        with self._lock:
            total_patterns = sum(
                len(patterns) for patterns in self._arg_coverage.values()
            )
            total_uses = sum(
                sum(counts.values()) for counts in self._arg_coverage.values()
            )
            tools_with_arg_coverage = len(self._arg_coverage)

        return {
            "tools_tracked": tools_with_arg_coverage,
            "total_arg_patterns": total_patterns,
            "total_arg_uses": total_uses,
            "avg_patterns_per_tool": (
                total_patterns / tools_with_arg_coverage
                if tools_with_arg_coverage > 0
                else 0
            ),
        }
