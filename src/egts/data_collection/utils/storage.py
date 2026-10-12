"""Data storage module for persisting trajectories."""

import asyncio
import logging
import json
import hashlib
import copy
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ..dedup.semantic_deduplicator import SemanticDeduplicator

logger = logging.getLogger(__name__)


def _atomic_write_json(path: Path, data: Any) -> None:
    """Write JSON atomically: write to temp file then rename to avoid corruption on crash."""
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        tmp_path.rename(path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def _normalize_problem_text(text: str) -> str:
    """Normalize problem text for comparison.

    Strips whitespace, converts to lowercase, and removes common variations.
    """
    if not text:
        return ""
    # Normalize: lowercase, strip, collapse multiple spaces
    normalized = " ".join(text.lower().strip().split())
    return normalized


def _compute_problem_hash(problem_text: str) -> str:
    """Compute hash of normalized problem text."""
    normalized = _normalize_problem_text(problem_text)
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:16]


def _compute_trajectory_hash(trajectory: Dict[str, Any]) -> str:
    """Compute hash of trajectory based on tool call sequence.

    Two trajectories are considered "same" if they have the same
    sequence of (tool_name, success) pairs.
    """
    tool_calls = trajectory.get("tool_calls", [])

    # Build signature from tool call sequence
    signature = []
    for tc in tool_calls:
        if isinstance(tc, dict):
            name = tc.get("tool_name", tc.get("name", "unknown"))
            success = tc.get("success", True)
            # Include key argument patterns (truncated to avoid over-specificity)
            args = tc.get("arguments", {})
            if isinstance(args, dict):
                arg_keys = sorted(args.keys())[:3]  # Top 3 argument keys
            else:
                arg_keys = []
            signature.append(f"{name}:{success}:{','.join(arg_keys)}")

    signature_str = "|".join(signature)
    return hashlib.md5(signature_str.encode("utf-8")).hexdigest()[:16]


class Storage:
    """Storage manager for trajectory data with deduplication support."""

    def __init__(
        self,
        output_dir: str,
        exp_name: str = "",
        dedup_enabled: bool = True,
        max_trajectories_per_problem: int = 3,
        semantic_deduplicator: Optional["SemanticDeduplicator"] = None,
    ):
        """Initialize storage manager.

        Args:
            output_dir: Base output directory
            exp_name: Experiment name for organization (empty = use timestamp)
            dedup_enabled: Whether to enable deduplication filtering
            max_trajectories_per_problem: Max different trajectories to keep per problem
            semantic_deduplicator: Optional semantic deduplicator for embedding-based checks
        """
        self.output_dir = Path(output_dir)
        self.exp_name = exp_name
        self.exp_dir = self.output_dir / exp_name

        # Deduplication settings
        self.dedup_enabled = dedup_enabled
        self.max_trajectories_per_problem = max_trajectories_per_problem
        self.semantic_deduplicator = semantic_deduplicator

        self.stats = {
            "exp_name": exp_name,
            "total_generated": 0,
            "total_validated": 0,
            "total_failed": 0,
            # trajs2data mode stats
            "trajs2data_total": 0,
            "trajs2data_valid": 0,
            "trajs2data_raw": 0,
            "trajs2data_filtered": 0,
            "trajs2data_deduplicated": 0,  # Count of deduplicated episodes
            "trajs2data_salvaged": 0,  # Count of salvaged (truncated) episodes
            # Detailed failure tracking
            "total_tool_failures": 0,  # Total tool call failures across all episodes
            "failure_by_tool": {},  # tool_name -> failure_count
            "failure_by_reason": {},  # reason_category -> count
            "failure_events": [],  # Recent failure events (limited)
            # Episode-level stats for averages
            "episode_failure_counts": [],  # Per-episode failure counts (limited)
            # Type breakdown
            "trajs2data_mutation": 0,
            "trajs2data_retrieval": 0,
            "data_source_counts": {},
        }

        # Limit for stored failure events (to avoid memory bloat)
        self._max_failure_events = 100
        self._max_episode_failure_records = 500

        # Thread safety for concurrent operations.
        # NOTE: These are threading.Lock because Storage methods are synchronous.
        # For async callers, the blocking I/O in save_* methods should be offloaded
        # via loop.run_in_executor() to avoid event-loop stalls under concurrency.
        # With num_workers=1, lock contention is not seen in practice.
        self._stats_lock = threading.Lock()

        # Deduplication index: problem_hash -> [(trajectory_hash, path), ...]
        self._problem_index: Dict[str, List[Tuple[str, Path]]] = {}
        self._dedup_lock = threading.Lock()

        # Load existing index from disk if available
        if self.dedup_enabled:
            self._load_dedup_index()

        # Resume statistics from previous runs (if any), with filesystem scan fallback.
        self._load_existing_statistics()

        logger.info(
            f"Storage initialized: {self.exp_dir} (dedup={'enabled' if dedup_enabled else 'disabled'})"
        )

    def _load_dedup_index(self):
        """Load deduplication index from existing data on disk."""
        count = 0
        if not self.exp_dir.exists():
            return

        for server_dir in self.exp_dir.iterdir():
            if not server_dir.is_dir():
                continue

            trajs2data_dir = server_dir / "trajs2data"
            if not trajs2data_dir.exists():
                continue

            for entry_dir in trajs2data_dir.iterdir():
                if not entry_dir.is_dir():
                    continue

                problem_path = entry_dir / "problem.json"
                trajectory_path = entry_dir / "trajectory.json"

                if not problem_path.exists() or not trajectory_path.exists():
                    continue

                try:
                    with open(problem_path, "r", encoding="utf-8") as f:
                        problem_data = json.load(f)
                    with open(trajectory_path, "r", encoding="utf-8") as f:
                        trajectory_data = json.load(f)

                    problem_text = problem_data.get("problem", "")
                    problem_hash = _compute_problem_hash(problem_text)
                    traj_hash = _compute_trajectory_hash(trajectory_data)

                    if problem_hash not in self._problem_index:
                        self._problem_index[problem_hash] = []

                    self._problem_index[problem_hash].append((traj_hash, entry_dir))
                    count += 1

                except Exception as e:
                    logger.warning(f"Failed to index {entry_dir}: {e}")

        if count > 0:
            logger.info(
                f"Loaded dedup index: {count} entries, {len(self._problem_index)} unique problems"
            )

    def _load_existing_statistics(self):
        """Load/repair statistics from previous runs for resume scenarios."""
        stats_path = self.exp_dir / "statistics.json"
        loaded_stats: Dict[str, Any] = {}

        if stats_path.exists():
            try:
                with open(stats_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict):
                    loaded_stats = raw
            except Exception as e:
                logger.warning(f"Failed to load existing statistics from {stats_path}: {e}")

        # Start from loaded file values when available.
        for key in self.stats.keys():
            if key in loaded_stats:
                self.stats[key] = loaded_stats[key]

        # Reconcile with on-disk episode directories to avoid stat reset on resume.
        scanned = self._scan_existing_episode_stats()
        numeric_keys = [
            "trajs2data_total",
            "trajs2data_valid",
            "trajs2data_raw",
            "trajs2data_filtered",
            "trajs2data_mutation",
            "trajs2data_retrieval",
            "trajs2data_salvaged",
        ]
        for key in numeric_keys:
            current = int(self.stats.get(key, 0) or 0)
            self.stats[key] = max(current, scanned.get(key, 0))
        if scanned.get("data_source_counts"):
            merged_sources = dict(scanned.get("data_source_counts") or {})
            for source, count in dict(self.stats.get("data_source_counts", {}) or {}).items():
                merged_sources[source] = max(int(count or 0), int(merged_sources.get(source, 0) or 0))
            self.stats["data_source_counts"] = merged_sources

        # Keep dedup count from previous persisted stats (cannot be recovered from disk).
        deduped = int(self.stats.get("trajs2data_deduplicated", 0) or 0)
        min_total = (
            int(self.stats.get("trajs2data_valid", 0) or 0)
            + int(self.stats.get("trajs2data_raw", 0) or 0)
            + int(self.stats.get("trajs2data_filtered", 0) or 0)
            + deduped
        )
        self.stats["trajs2data_total"] = max(
            int(self.stats.get("trajs2data_total", 0) or 0), min_total
        )

    def _scan_existing_episode_stats(self) -> Dict[str, int]:
        """Scan output folders to reconstruct key trajs2data counters."""
        counts = {
            "trajs2data_total": 0,
            "trajs2data_valid": 0,
            "trajs2data_raw": 0,
            "trajs2data_filtered": 0,
            "trajs2data_mutation": 0,
            "trajs2data_retrieval": 0,
            "trajs2data_salvaged": 0,
            "data_source_counts": {},
        }

        if not self.exp_dir.exists():
            return counts

        scan_roots = [self.exp_dir] + [
            child for child in self.exp_dir.iterdir() if child.is_dir()
        ]

        for server_dir in scan_roots:

            valid_dir = server_dir / "trajs2data"
            if valid_dir.exists():
                for entry in valid_dir.iterdir():
                    if not entry.is_dir():
                        continue
                    metadata_path = entry / "metadata.json"
                    if not metadata_path.exists():
                        continue
                    counts["trajs2data_valid"] += 1
                    counts["trajs2data_total"] += 1
                    try:
                        with open(metadata_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                        self._accumulate_source_count(
                            counts["data_source_counts"], meta
                        )
                        task_type = str(meta.get("task_type", meta.get("type", ""))).lower()
                        if task_type == "retrieval":
                            counts["trajs2data_retrieval"] += 1
                        elif task_type == "mutation":
                            counts["trajs2data_mutation"] += 1
                        if bool(meta.get("salvaged", False)):
                            counts["trajs2data_salvaged"] += 1
                    except Exception:
                        continue

            raw_dir = server_dir / "trajs2data_raw"
            if raw_dir.exists():
                for entry in raw_dir.iterdir():
                    if not entry.is_dir():
                        continue
                    metadata_path = entry / "metadata.json"
                    if not metadata_path.exists():
                        continue
                    counts["trajs2data_raw"] += 1
                    counts["trajs2data_total"] += 1
                    try:
                        with open(metadata_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                        self._accumulate_source_count(
                            counts["data_source_counts"], meta
                        )
                        task_type = str(meta.get("task_type", meta.get("type", ""))).lower()
                        if task_type == "retrieval":
                            counts["trajs2data_retrieval"] += 1
                        elif task_type == "mutation":
                            counts["trajs2data_mutation"] += 1
                        if bool(meta.get("salvaged", False)):
                            counts["trajs2data_salvaged"] += 1
                    except Exception:
                        continue

            filtered_dir = server_dir / "trajs2data_filtered"
            if filtered_dir.exists():
                for entry in filtered_dir.iterdir():
                    if not entry.is_dir():
                        continue
                    info_path = entry / "filter_info.json"
                    if not info_path.exists():
                        continue
                    counts["trajs2data_filtered"] += 1
                    counts["trajs2data_total"] += 1
                    try:
                        with open(info_path, "r", encoding="utf-8") as f:
                            info = json.load(f)
                        self._accumulate_source_count(
                            counts["data_source_counts"], info
                        )
                    except Exception:
                        continue

        return counts

    @staticmethod
    def _source_name_from_metadata(metadata: Optional[Dict[str, Any]]) -> Optional[str]:
        if not isinstance(metadata, dict):
            return None
        data_source = metadata.get("data_source")
        if isinstance(data_source, dict):
            for key in ("name", "namespace", "output_namespace", "selected_env"):
                value = data_source.get(key)
                if value:
                    return str(value)
        for key in ("data_source_name", "source_namespace", "source_env"):
            value = metadata.get(key)
            if value:
                return str(value)
        world_context = metadata.get("world_context")
        if isinstance(world_context, dict):
            configured = world_context.get("configured")
            if isinstance(configured, dict):
                value = configured.get("selected_env")
                if value:
                    return str(value)
        return None

    @classmethod
    def _accumulate_source_count(
        cls, counts: Dict[str, int], metadata: Optional[Dict[str, Any]]
    ) -> None:
        source_name = cls._source_name_from_metadata(metadata) or "unknown"
        counts[source_name] = int(counts.get(source_name, 0) or 0) + 1

    def _record_data_source(self, metadata: Optional[Dict[str, Any]]) -> None:
        source_name = self._source_name_from_metadata(metadata)
        if not source_name:
            return
        source_counts = self.stats.setdefault("data_source_counts", {})
        source_counts[source_name] = int(source_counts.get(source_name, 0) or 0) + 1

    def _check_dedup(
        self,
        problem_text: str,
        trajectory: Dict[str, Any],
        sample_path: Optional[Path] = None,
    ) -> Tuple[bool, str]:
        """Check if this problem/trajectory combination should be deduplicated.

        Args:
            problem_text: The synthesized problem text
            trajectory: The trajectory data
            sample_path: Path where sample will be saved (optional)

        Returns:
            (should_save, reason): Whether to save and the reason if rejected
        """
        if not self.dedup_enabled:
            return True, ""

        # 1. Semantic Deduplication (Priority if enabled)
        if self.semantic_deduplicator:
            decision = self.semantic_deduplicator.should_keep(
                problem_text=problem_text,
                trajectory=trajectory,
                sample_path=sample_path,
            )
            if not decision.should_keep:
                return False, decision.reason
            # Note: should_keep automatically registers the entry if kept
            return True, ""

        # 2. Basic Hash-based Deduplication (Fallback)
        problem_hash = _compute_problem_hash(problem_text)
        traj_hash = _compute_trajectory_hash(trajectory)

        with self._dedup_lock:
            if problem_hash not in self._problem_index:
                # New problem, always save
                return True, ""

            existing_trajs = self._problem_index[problem_hash]

            # Check if this exact trajectory already exists
            for existing_traj_hash, existing_path in existing_trajs:
                if existing_traj_hash == traj_hash:
                    return (
                        False,
                        f"Duplicate trajectory for problem '{problem_text[:50]}...'",
                    )

            # Check if we've reached the limit for this problem
            if len(existing_trajs) >= self.max_trajectories_per_problem:
                return (
                    False,
                    f"Already have {self.max_trajectories_per_problem} different trajectories for problem '{problem_text[:50]}...'",
                )

            # Different trajectory for existing problem, allow it
            return True, ""

    def get_max_existing_iteration(
        self, mcp_server_name: str = "filesystem", output_namespace: str | None = None
    ) -> int:
        """Scan output directory to find the maximum existing iteration number.

        Checks the flattened experiment root plus the mcp_server_name and
        output_namespace directories to correctly resume after namespace-aware
        saves.

        Args:
            mcp_server_name: MCP server name to check
            output_namespace: Optional output namespace override

        Returns:
            Max iteration number found, or -1 if no data exists
        """
        candidates = ["", mcp_server_name]
        if output_namespace:
            candidates.append(output_namespace)
        candidates = list(dict.fromkeys(candidates))

        max_iter = -1

        scan_rules = {
            "trajs2data": "metadata.json",
            "trajs2data_raw": "metadata.json",
            "trajs2data_filtered": "filter_info.json",
        }

        for ns in candidates:
            base_dir = self.exp_dir if ns == "" else self.exp_dir / ns
            for sub, marker_file in scan_rules.items():
                target_dir = base_dir / sub
                if not target_dir.exists():
                    continue

                for entry in target_dir.iterdir():
                    if not entry.is_dir():
                        continue

                    if not (entry / marker_file).exists():
                        continue

                    name = entry.name
                    if "_" in name:
                        try:
                            num_part = name.split("_")[-1]
                            val = int(num_part)
                            if val > max_iter:
                                max_iter = val
                        except ValueError:
                            continue

        return max_iter

    def _register_saved_entry(
        self, problem_text: str, trajectory: Dict[str, Any], saved_path: Path
    ):
        """Register a saved entry in the deduplication index."""
        problem_hash = _compute_problem_hash(problem_text)
        traj_hash = _compute_trajectory_hash(trajectory)

        with self._dedup_lock:
            if problem_hash not in self._problem_index:
                self._problem_index[problem_hash] = []

            self._problem_index[problem_hash].append((traj_hash, saved_path))

    def save_trajectory(
        self,
        trajectory: Dict[str, Any],
        verifier_script: str,
        mcp_server_name: str,
        is_valid: bool,
        iteration: int,
        problem_data: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """Save a trajectory to disk.

        Args:
            trajectory: Trajectory data
            verifier_script: Verification script content
            mcp_server_name: Name of the MCP server
            is_valid: Whether the trajectory passed validation
            iteration: Iteration number
            problem_data: Optional problem data including Dockerfile

        Returns:
            Path to saved trajectory directory
        """
        # Update statistics (thread-safe)
        with self._stats_lock:
            self.stats["total_generated"] += 1
            if is_valid:
                self.stats["total_validated"] += 1
            else:
                self.stats["total_failed"] += 1

        unique_id = f"problem_{iteration:06d}"

        status = "valid" if is_valid else "failed"
        trajectory_dir = self.exp_dir / mcp_server_name / status / unique_id
        trajectory_dir.mkdir(parents=True, exist_ok=True)

        # Save trajectory
        trajectory_path = trajectory_dir / "trajectory.json"
        with open(trajectory_path, "w") as f:
            json.dump(trajectory, f, indent=2)

        # Save verification script
        verifier_path = trajectory_dir / "verify.py"
        with open(verifier_path, "w") as f:
            f.write(verifier_script)

        timestamp = datetime.now().isoformat()

        # Save Dockerfile if provided
        if problem_data and problem_data.get("dockerfile"):
            dockerfile_path = trajectory_dir / "Dockerfile"
            with open(dockerfile_path, "w") as f:
                f.write(problem_data["dockerfile"])

        # Save problem.json if provided
        if problem_data:
            problem_path = trajectory_dir / "problem.json"
            with open(problem_path, "w") as f:
                json.dump(problem_data, f, indent=2)

        # Save metadata with enhanced information
        metadata = {
            "exp_name": self.exp_name,
            "mcp_server": mcp_server_name,
            "is_valid": is_valid,
            "timestamp": timestamp,
            "iteration": iteration,
            "problem": trajectory["problem"]["problem"],
            "tools_used": trajectory["tools_used"],
            "num_turns": trajectory["num_turns"],
            "execution_time": trajectory.get("execution_time"),
            "model_name": trajectory.get("model_name"),
            "success": trajectory.get("success", True),
            "error": trajectory.get("error"),
        }

        metadata_path = trajectory_dir / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(
            f"Saved {'valid' if is_valid else 'failed'} trajectory to {trajectory_dir}"
        )

        return trajectory_dir

    def save_statistics(self):
        """Save collection statistics to disk (thread-safe)."""
        stats_path = self.exp_dir / "statistics.json"
        stats_path.parent.mkdir(parents=True, exist_ok=True)

        # Lock critical section: getting stats AND writing to file
        with self._stats_lock:
            # Use get_statistics logic (inline here to stay inside lock)
            stats_copy = self.stats.copy()

            # Re-calculate computed fields inside lock
            stats_copy["success_rate"] = (
                stats_copy["total_validated"] / stats_copy["total_generated"]
                if stats_copy["total_generated"] > 0
                else 0.0
            )

            trajs2data_attempted = stats_copy["trajs2data_total"] - stats_copy.get(
                "trajs2data_deduplicated", 0
            )
            trajs2data_saved = stats_copy.get("trajs2data_valid", 0) + stats_copy.get(
                "trajs2data_raw", 0
            )
            stats_copy["trajs2data_saved"] = trajs2data_saved
            stats_copy["trajs2data_success_rate"] = (
                trajs2data_saved / trajs2data_attempted
                if trajs2data_attempted > 0
                else 0.0
            )
            stats_copy["trajs2data_valid_success_rate"] = (
                stats_copy["trajs2data_valid"] / trajs2data_attempted
                if trajs2data_attempted > 0
                else 0.0
            )
            stats_copy["trajs2data_raw_success_rate"] = (
                stats_copy.get("trajs2data_raw", 0) / trajs2data_attempted
                if trajs2data_attempted > 0
                else 0.0
            )

            # Deduplication index access needs its own lock, but we are inside stats_lock.
            # Ideally avoid nested locks if possible to prevent deadlocks.
            # But here _dedup_lock is subordinate.
            with self._dedup_lock:
                stats_copy["unique_problems"] = len(self._problem_index)

            # ... (rest of computation)
            episode_failure_counts = stats_copy.get("episode_failure_counts", [])
            if episode_failure_counts:
                stats_copy["avg_failures_per_episode"] = sum(
                    episode_failure_counts
                ) / len(episode_failure_counts)
            else:
                stats_copy["avg_failures_per_episode"] = 0.0

            salvaged = stats_copy.get("trajs2data_salvaged", 0)
            filtered = stats_copy.get("trajs2data_filtered", 0)
            if (salvaged + filtered) > 0:
                stats_copy["salvage_rate"] = salvaged / (salvaged + filtered)
            else:
                stats_copy["salvage_rate"] = 0.0

            # Add timestamp
            stats_with_time = {
                **stats_copy,
                "last_updated": datetime.now().isoformat(),
            }

            # Write to file while holding the lock to prevent interleaving
            try:
                with open(stats_path, "w", encoding="utf-8") as f:
                    json.dump(stats_with_time, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.error(f"Failed to save statistics: {e}")

        # Log compact summary (outside lock is fine)
        logger.debug(
            f"Statistics saved: valid={stats_with_time.get('trajs2data_valid', 0)}, "
            f"raw={stats_with_time.get('trajs2data_raw', 0)}, "
            f"filtered={stats_with_time.get('trajs2data_filtered', 0)}, "
            f"salvaged={stats_with_time.get('trajs2data_salvaged', 0)}"
        )

    def get_statistics(self) -> Dict[str, Any]:
        """Get current statistics.

        Returns:
            Statistics dictionary
        """
        with self._stats_lock:
            stats_copy = self.stats.copy()

        # Calculate success rates
        stats_copy["success_rate"] = (
            stats_copy["total_validated"] / stats_copy["total_generated"]
            if stats_copy["total_generated"] > 0
            else 0.0
        )

        # trajs2data save rate (excluding deduplicated). In collection-only mode
        # raw episodes are successful outputs; synthesized valid episodes are
        # counted separately for synthesis-in-collection runs.
        trajs2data_attempted = stats_copy["trajs2data_total"] - stats_copy.get(
            "trajs2data_deduplicated", 0
        )
        trajs2data_saved = stats_copy.get("trajs2data_valid", 0) + stats_copy.get(
            "trajs2data_raw", 0
        )
        stats_copy["trajs2data_saved"] = trajs2data_saved
        stats_copy["trajs2data_success_rate"] = (
            trajs2data_saved / trajs2data_attempted
            if trajs2data_attempted > 0
            else 0.0
        )
        stats_copy["trajs2data_valid_success_rate"] = (
            stats_copy["trajs2data_valid"] / trajs2data_attempted
            if trajs2data_attempted > 0
            else 0.0
        )
        stats_copy["trajs2data_raw_success_rate"] = (
            stats_copy.get("trajs2data_raw", 0) / trajs2data_attempted
            if trajs2data_attempted > 0
            else 0.0
        )

        # Unique problems count
        with self._dedup_lock:
            stats_copy["unique_problems"] = len(self._problem_index)

        # Compute average failures per episode
        episode_failure_counts = stats_copy.get("episode_failure_counts", [])
        if episode_failure_counts:
            stats_copy["avg_failures_per_episode"] = sum(episode_failure_counts) / len(
                episode_failure_counts
            )
        else:
            stats_copy["avg_failures_per_episode"] = 0.0

        # Compute salvage rate (salvaged / (filtered + salvaged))
        salvaged = stats_copy.get("trajs2data_salvaged", 0)
        filtered = stats_copy.get("trajs2data_filtered", 0)
        if (salvaged + filtered) > 0:
            stats_copy["salvage_rate"] = salvaged / (salvaged + filtered)
        else:
            stats_copy["salvage_rate"] = 0.0

        return stats_copy

    def record_tool_failure(
        self,
        tool_name: str,
        reason: str = "unknown",
        episode_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        """Record a tool call failure for statistics.

        Args:
            tool_name: Name of the tool that failed
            reason: Failure reason category (e.g., "invalid_args", "execution_error", "timeout")
            episode_id: Optional episode identifier
            error_message: Optional detailed error message
        """
        with self._stats_lock:
            self.stats["total_tool_failures"] += 1

            # Track by tool
            if tool_name not in self.stats["failure_by_tool"]:
                self.stats["failure_by_tool"][tool_name] = 0
            self.stats["failure_by_tool"][tool_name] += 1

            # Track by reason
            if reason not in self.stats["failure_by_reason"]:
                self.stats["failure_by_reason"][reason] = 0
            self.stats["failure_by_reason"][reason] += 1

            # Store recent failure events (capped)
            if len(self.stats["failure_events"]) < self._max_failure_events:
                self.stats["failure_events"].append(
                    {
                        "tool": tool_name,
                        "reason": reason,
                        "episode": episode_id,
                        "message": (error_message or "")[
                            :200
                        ],  # Truncate long messages
                        "timestamp": datetime.now().isoformat(),
                    }
                )

    def record_episode_failures(
        self, num_failures: int, episode_id: Optional[str] = None
    ):
        """Record the number of failures for an episode (for avg calculation).

        Args:
            num_failures: Number of tool failures in this episode
            episode_id: Optional episode identifier
        """
        with self._stats_lock:
            if (
                len(self.stats["episode_failure_counts"])
                < self._max_episode_failure_records
            ):
                self.stats["episode_failure_counts"].append(num_failures)

    def record_salvaged_episode(
        self, original_target_n: int, actual_steps: int, reason: str = "max_failures"
    ):
        """Record that an episode was salvaged (truncated but saved).

        Args:
            original_target_n: The original target number of tool calls
            actual_steps: The actual number of successful steps saved
            reason: Why the episode was truncated (e.g., "max_failures", "timeout")
        """
        with self._stats_lock:
            self.stats["trajs2data_salvaged"] += 1

    def get_failure_report(self) -> Dict[str, Any]:
        """Get detailed failure report.

        Returns:
            Failure statistics and recent events
        """
        with self._stats_lock:
            return {
                "total_tool_failures": self.stats["total_tool_failures"],
                "failure_by_tool": dict(self.stats["failure_by_tool"]),
                "failure_by_reason": dict(self.stats["failure_by_reason"]),
                "recent_failures": list(self.stats["failure_events"][-20:]),  # Last 20
                "avg_failures_per_episode": (
                    sum(self.stats["episode_failure_counts"])
                    / len(self.stats["episode_failure_counts"])
                    if self.stats["episode_failure_counts"]
                    else 0.0
                ),
            }

    def get_quality_report(self) -> Dict[str, Any]:
        """Generate a comprehensive quality report for the dataset.

        Returns:
            Quality metrics including efficiency, coverage, and diversity
        """
        stats = self.get_statistics()
        failure_report = self.get_failure_report()

        # Compute efficiency metrics
        total = stats.get("trajs2data_total", 0)
        valid = stats.get("trajs2data_valid", 0)
        filtered = stats.get("trajs2data_filtered", 0)
        deduped = stats.get("trajs2data_deduplicated", 0)
        salvaged = stats.get("trajs2data_salvaged", 0)

        return {
            "summary": {
                "total_episodes_attempted": total,
                "valid_saved": valid,
                "filtered_out": filtered,
                "deduplicated": deduped,
                "salvaged": salvaged,
                "yield_rate": valid / total if total > 0 else 0.0,
                "salvage_rate": salvaged / (filtered + salvaged)
                if (filtered + salvaged) > 0
                else 0.0,
            },
            "type_distribution": {
                "mutation": stats.get("trajs2data_mutation", 0),
                "retrieval": stats.get("trajs2data_retrieval", 0),
            },
            "diversity": {
                "unique_problems": stats.get("unique_problems", 0),
                "avg_trajectories_per_problem": (
                    valid / stats.get("unique_problems", 1)
                    if stats.get("unique_problems", 0) > 0
                    else 0.0
                ),
            },
            "failure_analysis": {
                "total_tool_failures": failure_report["total_tool_failures"],
                "avg_failures_per_episode": failure_report["avg_failures_per_episode"],
                "top_failing_tools": sorted(
                    failure_report["failure_by_tool"].items(),
                    key=lambda x: x[1],
                    reverse=True,
                )[:10],
                "failure_reasons": failure_report["failure_by_reason"],
            },
            "generated_at": datetime.now().isoformat(),
        }

    def get_dedup_stats(self) -> Dict[str, Any]:
        """Get detailed deduplication statistics.

        Returns:
            Deduplication metrics including count per problem, rejection reasons, etc.
        """
        with self._stats_lock:
            total = self.stats.get("trajs2data_total", 0)
            deduped = self.stats.get("trajs2data_deduplicated", 0)

        with self._dedup_lock:
            unique_problems = len(self._problem_index)

            # Calculate trajectories per problem distribution
            trajs_per_problem = []
            for problem_hash, traj_list in self._problem_index.items():
                trajs_per_problem.append(len(traj_list))

            avg_trajs = (
                sum(trajs_per_problem) / len(trajs_per_problem)
                if trajs_per_problem
                else 0
            )
            max_trajs = max(trajs_per_problem) if trajs_per_problem else 0
            min_trajs = min(trajs_per_problem) if trajs_per_problem else 0

            # Count problems at capacity (max_trajectories_per_problem)
            at_capacity = sum(
                1
                for count in trajs_per_problem
                if count >= self.max_trajectories_per_problem
            )

        return {
            "enabled": self.dedup_enabled,
            "max_trajectories_per_problem": self.max_trajectories_per_problem,
            "total_episodes": total,
            "deduplicated_count": deduped,
            "dedup_rate": deduped / total if total > 0 else 0.0,
            "unique_problems": unique_problems,
            "trajectories_per_problem": {
                "avg": round(avg_trajs, 2),
                "min": min_trajs,
                "max": max_trajs,
            },
            "problems_at_capacity": at_capacity,
            "capacity_rate": at_capacity / unique_problems
            if unique_problems > 0
            else 0.0,
        }

    def save_quality_report(self):
        """Save quality report to disk."""
        report = self.get_quality_report()
        report_path = self.exp_dir / "quality_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"Quality report saved to {report_path}")
        return report

    def _resolve_output_namespace(
        self,
        default_server_name: str,
        metadata_extra: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Resolve artifact namespace, preferring explicit storage overrides."""
        if metadata_extra and "artifact_namespace" in metadata_extra:
            return str(metadata_extra.get("artifact_namespace") or "")
        if metadata_extra and metadata_extra.get("output_namespace"):
            return str(metadata_extra["output_namespace"])
        return default_server_name

    def _allocate_episode_dir(
        self,
        base_dir: Path,
        prefix: str,
        iteration: int,
    ) -> Tuple[Path, int]:
        """Create a new episode directory without overwriting existing data."""
        candidate_iteration = iteration
        while True:
            episode_dir = base_dir / f"{prefix}_{candidate_iteration:06d}"
            try:
                episode_dir.mkdir(parents=True, exist_ok=False)
                if candidate_iteration != iteration:
                    logger.warning(
                        "Episode id %s_%06d already existed; saved as %s_%06d instead",
                        prefix,
                        iteration,
                        prefix,
                        candidate_iteration,
                    )
                return episode_dir, candidate_iteration
            except FileExistsError:
                candidate_iteration += 1

    def save_trajs2data_trajectory(
        self,
        trajectory: Dict[str, Any],
        problem_data: Dict[str, Any],
        mcp_server_name: str,
        iteration: int,
        metadata_extra: Optional[Dict[str, Any]] = None,
        final_assistant_answer: Optional[str] = None,
    ) -> Optional[Path]:
        """Save a trajs2data trajectory (without verifier script).

        This method is for the Traj→Problem pipeline where trajectories
        are the training signal, not verification scripts.

        Supports dual-mode:
        - Mutation (task_type="mutation"): Standard trajectory with filesystem changes
        - Retrieval (task_type="retrieval"): Q&A trajectory with reference_answer

        Includes deduplication:
        - Same problem + same trajectory: rejected
        - Same problem + different trajectory: allowed up to MAX_TRAJECTORIES_PER_PROBLEM

        Args:
            trajectory: Trajectory data (from StrictTrajectory.to_dict())
            problem_data: Problem data including synthesized problem.json
            mcp_server_name: Name of the MCP server
            iteration: Iteration number
            metadata_extra: Additional metadata fields (seed, n_tools, type, phase, anchors, etc.)
            final_assistant_answer: For retrieval mode, the final assistant answer to append

        Returns:
            Path to saved trajectory directory, or None if deduplicated
        """
        problem_text = problem_data.get("problem", "")
        task_type = problem_data.get(
            "task_type",
            metadata_extra.get("type", "mutation") if metadata_extra else "mutation",
        )

        output_namespace = self._resolve_output_namespace(
            mcp_server_name, metadata_extra
        )

        # Check deduplication
        # Pass trajectory_dir as tentative path (though it might not be created yet if rejected)
        tentative_path = (
            self.exp_dir
            / output_namespace
            / "trajs2data"
            / f"trajs2data_{iteration:06d}"
        )
        should_save, dedup_reason = self._check_dedup(
            problem_text, trajectory, tentative_path
        )

        if not should_save:
            # Update statistics for deduplicated entry
            with self._stats_lock:
                self.stats["trajs2data_total"] += 1
                self.stats["trajs2data_deduplicated"] += 1

            logger.info(f"Deduplicated iteration {iteration}: {dedup_reason}")
            return None

        # Update statistics (thread-safe)
        with self._stats_lock:
            self.stats["trajs2data_total"] += 1
            self.stats["trajs2data_valid"] += 1

            # Track by type
            if task_type == "retrieval":
                self.stats.setdefault("trajs2data_retrieval", 0)
                self.stats["trajs2data_retrieval"] += 1
            else:
                self.stats.setdefault("trajs2data_mutation", 0)
                self.stats["trajs2data_mutation"] += 1

        unique_id = f"trajs2data_{iteration:06d}"
        trajectory_dir = self.exp_dir / output_namespace / "trajs2data" / unique_id
        trajectory_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().isoformat()

        # For retrieval mode, append final assistant answer to trajectory messages
        trajectory_to_save = trajectory.copy()
        if final_assistant_answer and task_type == "retrieval":
            messages = trajectory_to_save.get("messages", [])
            # Append final assistant answer (not counted in num_steps)
            messages.append(
                {
                    "role": "assistant",
                    "content": final_assistant_answer,
                    "_is_final_answer": True,  # Mark as final answer, not a tool step
                }
            )
            trajectory_to_save["messages"] = messages
            trajectory_to_save["has_final_answer"] = True

        # Save trajectory.json
        trajectory_path = trajectory_dir / "trajectory.json"

        # Sanitize paths in trajectory before saving (prevent overfitting)
        # Use problem_data["filesystem_root"] if available, otherwise try to guess
        root_path = problem_data.get("filesystem_root")
        if root_path:
            # Create sanitized copy for saving
            trajectory_to_save_final = self._sanitize_trajectory_paths(
                trajectory_to_save, root_path, replacement="/workspace"
            )
        else:
            trajectory_to_save_final = trajectory_to_save

        with open(trajectory_path, "w", encoding="utf-8") as f:
            json.dump(trajectory_to_save_final, f, indent=2, ensure_ascii=False)

        # Save original trajectory if available (Pre-Hindsight)
        if "original_trajectory" in trajectory_to_save:
            original_path = trajectory_dir / "trajectory_original.json"
            # Extract and remove from main object to avoid duplication if it's there
            original_data = trajectory_to_save.pop("original_trajectory")
            # If it's a StrictTrajectory object, convert to dict
            if hasattr(original_data, "to_dict"):
                original_data = original_data.to_dict()

            with open(original_path, "w", encoding="utf-8") as f:
                json.dump(original_data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved original trajectory to {original_path}")

        # Save problem.json
        problem_path = trajectory_dir / "problem.json"
        with open(problem_path, "w", encoding="utf-8") as f:
            json.dump(problem_data, f, indent=2, ensure_ascii=False)

        # Determine task type for metadata
        task_type = problem_data.get("task_type", "mutation")

        # Build metadata with dual-mode support
        metadata = {
            "exp_name": self.exp_name,
            "mcp_server": mcp_server_name,
            "pipeline_mode": "trajs2data",
            "task_type": task_type,  # "mutation" or "retrieval"
            "timestamp": timestamp,
            "iteration": iteration,
            "problem": problem_data.get("problem", ""),
            "tools_used": trajectory.get("tools_used", []),
            "num_steps": trajectory.get("num_steps", 0),
            "num_successful_tool_calls": trajectory.get("num_successful_tool_calls", 0),
            "target_n": trajectory.get("target_n", 0),
            "status": trajectory.get("status", "success"),
            "execution_time": trajectory.get("execution_time"),
            "model_name": trajectory.get("model_name"),
            "difficulty_bucket": problem_data.get("difficulty_bucket"),
        }

        # Add type-specific metadata
        if task_type == "retrieval":
            metadata["retrieval_spec"] = problem_data.get("retrieval_spec", {})
            metadata["reference_answer_length"] = len(
                problem_data.get("reference_answer", "")
            )
            metadata["answer_truncated"] = problem_data.get("answer_truncated", False)
            metadata["has_final_answer"] = bool(final_assistant_answer)
        else:
            metadata["intent_spec"] = problem_data.get("intent_spec", {})

        # Add extra metadata fields (phase, anchors, base_tools, coverage, etc.)
        if metadata_extra:
            metadata.update(metadata_extra)
        with self._stats_lock:
            self._record_data_source(metadata)

        # Save metadata.json
        metadata_path = trajectory_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        # Register in deduplication index
        self._register_saved_entry(problem_text, trajectory, trajectory_dir)

        # No verify.py in trajs2data mode - trajectory is the ground truth
        logger.info(f"Saved trajs2data trajectory ({task_type}) to {trajectory_dir}")
        self.save_statistics()
        return trajectory_dir

    def save_trajs2data_raw_episode(
        self,
        trajectory: Dict[str, Any],
        raw_context: Dict[str, Any],
        mcp_server_name: str,
        iteration: int,
        metadata_extra: Optional[Dict[str, Any]] = None,
    ) -> Path:
        """Save a raw trajs2data episode without synthesized problem.

        This is used when collection focuses on trajectory acquisition and defers
        expensive LLM synthesis/rewriting to the offline data_synthesis pipeline.
        """
        output_namespace = self._resolve_output_namespace(
            mcp_server_name, metadata_extra
        )

        with self._stats_lock:
            self.stats["trajs2data_total"] += 1
            self.stats["trajs2data_raw"] += 1

        base_dir = self.exp_dir / output_namespace / "trajs2data_raw"
        episode_dir, saved_iteration = self._allocate_episode_dir(
            base_dir, "trajs2data", iteration
        )

        timestamp = datetime.now().isoformat()

        # Sanitize host-specific absolute paths to reduce overfitting/leakage.
        root_path = raw_context.get("filesystem_root") if isinstance(raw_context, dict) else None
        trajectory_to_save = trajectory
        raw_context_to_save = raw_context
        if root_path:
            trajectory_to_save = self._sanitize_trajectory_paths(
                trajectory, root_path, replacement="/workspace"
            )
            raw_context_to_save = self._sanitize_paths_recursive(
                raw_context, root_path, replacement="/workspace"
            )

        # Save raw trajectory
        trajectory_path = episode_dir / "trajectory.json"
        with open(trajectory_path, "w", encoding="utf-8") as f:
            json.dump(trajectory_to_save, f, indent=2, ensure_ascii=False)

        # Save raw synthesis context
        raw_context_path = episode_dir / "raw_context.json"
        with open(raw_context_path, "w", encoding="utf-8") as f:
            json.dump(raw_context_to_save, f, indent=2, ensure_ascii=False)

        metadata = {
            "exp_name": self.exp_name,
            "mcp_server": mcp_server_name,
            "pipeline_mode": "trajs2data_raw",
            "timestamp": timestamp,
            "iteration": saved_iteration,
            "requested_iteration": iteration,
            "num_steps": trajectory_to_save.get("num_steps", 0),
            "num_successful_tool_calls": trajectory_to_save.get(
                "num_successful_tool_calls", 0
            ),
            "target_n": trajectory_to_save.get("target_n", 0),
            "status": trajectory_to_save.get("status", "unknown"),
            "task_type": raw_context_to_save.get("task_type"),
            "task_domain": raw_context_to_save.get("task_domain"),
            "synthesis_deferred": True,
        }
        if metadata_extra:
            metadata.update(metadata_extra)
        with self._stats_lock:
            self._record_data_source(metadata)

        metadata_path = episode_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved raw trajs2data episode to {episode_dir}")
        self.save_statistics()
        return episode_dir

    def save_trajs2data_replay_synthesis_episode(
        self,
        replay_payload: Dict[str, Any],
        mcp_server_name: str,
        iteration: int,
        metadata_extra: Optional[Dict[str, Any]] = None,
        min_quality_tier: str = "acceptable",
    ) -> Path:
        """Save a task-oriented replay synthesis episode.

        All episodes are flattened into a single trajs2data_replay_synthesis/
        directory (no per-domain subdirectories). A real-time registry file is
        maintained alongside, gated by *min_quality_tier*.
        """
        base_dir = self.exp_dir / "trajs2data_replay_synthesis"
        episode_dir, saved_iteration = self._allocate_episode_dir(
            base_dir, "replay", iteration
        )

        problem = replay_payload.get("problem") or {}
        trajectory = replay_payload.get("trajectory") or {}
        replay_context = replay_payload.get("replay_context") or {}
        verification = replay_payload.get("verification") or {}
        review_record = replay_payload.get("review_record")

        _atomic_write_json(episode_dir / "problem.json", problem)
        _atomic_write_json(episode_dir / "trajectory.json", trajectory)
        _atomic_write_json(episode_dir / "replay_context.json", replay_context)
        _atomic_write_json(episode_dir / "verification.json", verification)
        if review_record is not None:
            _atomic_write_json(episode_dir / "synthesized_review_records.json", [review_record])

        metadata = {
            "exp_name": self.exp_name,
            "mcp_server": mcp_server_name,
            "pipeline_mode": "trajs2data_replay_synthesis",
            "timestamp": datetime.now().isoformat(),
            "iteration": saved_iteration,
            "requested_iteration": iteration,
            "accepted": bool(replay_payload.get("accepted", False)),
            "rejected_reason": replay_payload.get("rejected_reason", ""),
            "num_steps": trajectory.get("num_steps", 0),
            "num_successful_tool_calls": trajectory.get("num_successful_tool_calls", 0),
        }
        if metadata_extra:
            metadata.update(metadata_extra)
        _atomic_write_json(episode_dir / "metadata.json", metadata)

        with self._stats_lock:
            self.stats["trajs2data_total"] += 1
            if bool(replay_payload.get("accepted", False)):
                self.stats["trajs2data_valid"] += 1
            else:
                self.stats["trajs2data_filtered"] += 1
            self._record_data_source(metadata)

        # ── Real-time quality-gated registry ──
        self._update_replay_registry(
            episode_dir=episode_dir,
            saved_iteration=saved_iteration,
            replay_payload=replay_payload,
            metadata=metadata,
            min_quality_tier=min_quality_tier,
        )

        logger.info(f"Saved replay synthesis episode to {episode_dir}")
        self.save_statistics()
        return episode_dir

    def _update_replay_registry(
        self,
        episode_dir: Path,
        saved_iteration: int,
        replay_payload: Dict[str, Any],
        metadata: Dict[str, Any],
        min_quality_tier: str = "acceptable",
    ) -> None:
        """Real-time append to replay registry, gated by quality tier.

        Reads the existing registry, appends the new episode if its quality tier
        meets *min_quality_tier*, and atomically writes the updated registry.
        """
        registry_path = self.exp_dir / "trajs2data_replay_synthesis" / "registry.json"

        with self._stats_lock:
            try:
                if registry_path.exists():
                    registry = json.loads(registry_path.read_text("utf-8"))
                else:
                    registry = {
                        "created_at": datetime.now().isoformat(),
                        "min_quality_tier": min_quality_tier,
                        "total_episodes": 0,
                        "registry_entries": [],
                        "quality_distribution": {"high_quality": 0, "acceptable": 0, "reject": 0},
                    }
            except Exception:
                registry = {
                    "created_at": datetime.now().isoformat(),
                    "min_quality_tier": min_quality_tier,
                    "total_episodes": 0,
                    "registry_entries": [],
                    "quality_distribution": {"high_quality": 0, "acceptable": 0, "reject": 0},
                }

            review_record = replay_payload.get("review_record") or {}
            quality_tier = str(review_record.get("quality_tier", "reject"))
            quality_score = float(review_record.get("quality_score", 0.0))
            accepted = bool(replay_payload.get("accepted", False))
            problem = replay_payload.get("problem") or {}
            problem_text = (
                problem.get("problem", "")
                if isinstance(problem, dict)
                else str(problem)
            )

            # Bump counters
            registry["total_episodes"] += 1
            if quality_tier in registry["quality_distribution"]:
                registry["quality_distribution"][quality_tier] += 1

            # Quality gate: only add to registry_entries if tier meets threshold
            tier_rank = {"high_quality": 2, "acceptable": 1, "reject": 0}
            if tier_rank.get(quality_tier, -1) >= tier_rank.get(min_quality_tier, 1):
                entry = {
                    "episode_dir": str(episode_dir.name),
                    "saved_iteration": saved_iteration,
                    "quality_tier": quality_tier,
                    "quality_score": quality_score,
                    "accepted": accepted,
                    "task_type": metadata.get("task_type", ""),
                    "mcp_server": metadata.get("mcp_server", ""),
                    "num_steps": metadata.get("num_steps", 0),
                    "timestamp": datetime.now().isoformat(),
                    "problem": problem_text[:200],  # truncated for index
                }
                registry["registry_entries"].append(entry)

                # ── Real-time aggregated training data (JSONL) ──
                if review_record:
                    jsonl_path = self.exp_dir / "trajs2data_replay_synthesis" / "replay_data.jsonl"
                    try:
                        line = json.dumps(review_record, ensure_ascii=False)
                        with open(jsonl_path, "a", encoding="utf-8") as fh:
                            fh.write(line + "\n")
                    except Exception:
                        logger.exception("Failed to append review record to %s", jsonl_path)

            registry["updated_at"] = datetime.now().isoformat()
            _atomic_write_json(registry_path, registry)

    def _sanitize_paths_recursive(
        self, data: Any, root_path: str, replacement: str = "/workspace"
    ) -> Any:
        """Recursively replace absolute root paths in arbitrary nested structures."""
        root_path = str(root_path).rstrip("/")
        obj = copy.deepcopy(data)

        def _replace(v: Any) -> Any:
            if isinstance(v, str):
                return v.replace(root_path, replacement)
            if isinstance(v, dict):
                return {k: _replace(val) for k, val in v.items()}
            if isinstance(v, list):
                return [_replace(i) for i in v]
            return v

        return _replace(obj)

    def _sanitize_trajectory_paths(
        self,
        trajectory: Dict[str, Any],
        root_path: str,
        replacement: str = "/workspace",
    ) -> Dict[str, Any]:
        """Sanitize absolute paths in trajectory arguments.

        Replaces the host root path with a generic placeholder to prevent overfitting.
        Applies to:
        - Tool call arguments (path, paths, etc.)
        - Tool results (content)

        Args:
            trajectory: Trajectory dictionary
            root_path: The absolute root path to replace (e.g., /path/to/workspace/...)
            replacement: The replacement string (e.g., /workspace)

        Returns:
            Sanitized trajectory copy
        """
        import copy

        sanitized = copy.deepcopy(trajectory)
        root_path = str(root_path).rstrip("/")

        def _recursive_replace(obj: Any) -> Any:
            if isinstance(obj, str):
                return obj.replace(root_path, replacement)
            if isinstance(obj, dict):
                return {k: _recursive_replace(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_recursive_replace(i) for i in obj]
            return obj

        # Sanitize tool calls
        for tc in sanitized.get("tool_calls", []):
            if "arguments" in tc:
                tc["arguments"] = _recursive_replace(tc["arguments"])
            if "result" in tc:
                tc["result"] = _recursive_replace(tc["result"])

        # Sanitize messages
        for msg in sanitized.get("messages", []):
            if "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    if "function" in tc and "arguments" in tc["function"]:
                        # Arguments in messages are strings of JSON
                        try:
                            args_str = tc["function"]["arguments"]
                            if root_path in args_str:
                                tc["function"]["arguments"] = args_str.replace(
                                    root_path, replacement
                                )
                        except Exception:
                            pass
            if "content" in msg and isinstance(msg["content"], str):
                msg["content"] = msg["content"].replace(root_path, replacement)

        return sanitized

    def save_trajs2data_filtered(
        self,
        trajectory: Dict[str, Any],
        mcp_server_name: str,
        iteration: int,
        filter_reason: str,
        attempt: Optional[int] = None,
        filter_stage: Optional[str] = None,
        metadata_extra: Optional[Dict[str, Any]] = None,
    ) -> Optional[Path]:
        """Record a filtered trajectory (for debugging).

        Args:
            trajectory: Trajectory data
            mcp_server_name: Name of the MCP server
            iteration: Iteration number
            filter_reason: Why the trajectory was filtered
            attempt: Optional attempt number (1-based). If provided, each failed
                attempt gets its own directory.
            filter_stage: Optional stage tag (e.g., hard_filter, soft_filter).

        Returns:
            Path if saved, None if skipped
        """
        with self._stats_lock:
            self.stats["trajs2data_total"] += 1
            self.stats["trajs2data_filtered"] += 1

        # Optionally save filtered trajectories for analysis
        # Set to False to skip saving filtered trajectories
        save_filtered = True

        if not save_filtered:
            logger.debug(f"Filtered trajectory {iteration}: {filter_reason}")
            return None

        output_namespace = self._resolve_output_namespace(
            mcp_server_name,
            metadata_extra or ({"output_namespace": trajectory.get("output_namespace")} if isinstance(trajectory, dict) else None),
        )

        if attempt is not None:
            unique_id = f"filtered_{iteration:06d}_attempt_{int(attempt):02d}"
        else:
            unique_id = f"filtered_{iteration:06d}"

        base_dir = self.exp_dir / output_namespace / "trajs2data_filtered"
        filtered_dir = base_dir / unique_id
        if filtered_dir.exists():
            suffix = 2
            while True:
                candidate = base_dir / f"{unique_id}_v{suffix}"
                if not candidate.exists():
                    filtered_dir = candidate
                    break
                suffix += 1
        filtered_dir.mkdir(parents=True, exist_ok=True)

        # Save trajectory for debugging
        trajectory_path = filtered_dir / "trajectory.json"
        with open(trajectory_path, "w", encoding="utf-8") as f:
            json.dump(trajectory, f, indent=2, ensure_ascii=False)

        # Save filter info
        filter_info = {
            "iteration": iteration,
            "attempt": attempt,
            "filter_stage": filter_stage or "",
            "filter_reason": filter_reason,
            "timestamp": datetime.now().isoformat(),
            "status": trajectory.get("status", "unknown"),
            "abort_reason": trajectory.get("abort_reason"),
            "num_steps": trajectory.get("num_steps", 0),
        }
        if metadata_extra:
            filter_info.update(metadata_extra)
        with self._stats_lock:
            self._record_data_source(filter_info)

        filter_path = filtered_dir / "filter_info.json"
        with open(filter_path, "w", encoding="utf-8") as f:
            json.dump(filter_info, f, indent=2, ensure_ascii=False)

        logger.info(f"Saved filtered trajectory to {filtered_dir}: {filter_reason}")
        self.save_statistics()
        return filtered_dir
