"""Two-stage tool sampling for curriculum learning.

Stage 1: Random tool exposure with difficulty tiers (simple/medium/hard)
         for breadth exploration and moderate-depth task trajectories.
Stage 2: Skill-guided deep exploration using SKILL.md workflow documents
         for high-quality professional task trajectories.
"""

import logging
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple

from ..utils.config import ToolCurriculumConfig, StageConfig, DifficultyTierConfig, AffinityRuleConfig
from .coverage import CoverageTracker

logger = logging.getLogger(__name__)


@dataclass
class SamplingResult:
    """Result of a sampling operation.

    Contains all information needed to execute an episode.
    Note: is_retrieval_mode is always None at sampling time. The actual task type
    (mutation vs retrieval) is determined automatically after trajectory collection
    based on the filesystem diff.
    """

    stage: str  # Stage name (e.g., "stage1_random_tool")
    tier: Optional[str]  # Difficulty tier (e.g., "simple") or None for stage2
    exposed_tools: List[Dict[str, Any]]  # Tools exposed to the agent
    anchors: List[str]  # Anchor tool names (must be called)
    target_n: int  # Target successful tool calls
    min_distinct_tools: int  # Minimum distinct tools to use
    is_retrieval_mode: Optional[
        bool
    ]  # Deprecated: always None, determined after collection
    base_tools_used: List[str]  # Base tools in exposed set
    anchor_tools_used: List[str]  # Anchor tools in exposed set
    sampling_weights: Dict[str, float]  # Coverage-based weights used
    skill_selections: Optional[List[Any]] = None  # Selected skills for stage2
    skill_fallback: bool = False  # True when stage2 degraded to stage1 hard tier

    @property
    def phase(self) -> str:
        """Backward-compatible phase string for metadata."""
        return f"{self.stage}_{self.tier}" if self.tier else self.stage

    def to_metadata(self) -> Dict[str, Any]:
        """Convert to metadata dict for storage."""
        metadata = {
            "phase": self.phase,
            "stage": self.stage,
            "tier": self.tier,
            "anchors": self.anchors,
            "target_n": self.target_n,
            "min_distinct_tools": self.min_distinct_tools,
            "base_tools_used": self.base_tools_used,
            "anchor_tools_used": self.anchor_tools_used,
            "num_exposed_tools": len(self.exposed_tools),
        }
        if self.skill_selections:
            metadata["skill_ids"] = [s.skill_id for s in self.skill_selections]
            metadata["skill_descriptions"] = [s.description for s in self.skill_selections]
        if self.skill_fallback:
            metadata["skill_fallback"] = True
        return metadata


class StageAwareSampler:
    """Two-stage tool sampler with coverage optimization.

    Stage 1 (random tool exposure): Unified sampling with difficulty tiers
        - simple: base tools only (1-3 tools)
        - medium: base + anchor tools (3-6 tools)
        - hard: all tools (5-15 tools)
    Stage 2 (skill-guided): Professional workflow exploration via SKILL.md
    """

    def __init__(
        self,
        config: ToolCurriculumConfig,
        all_tools: List[Dict[str, Any]],
        coverage_tracker: Optional[CoverageTracker] = None,
        project_root: Optional[Path] = None,
        domain: Optional[str] = None,
        read_only_tools: Optional[List[str]] = None,
    ):
        """Initialize sampler.

        Args:
            config: Tool curriculum configuration
            all_tools: All available tools from MCP server
            coverage_tracker: Optional coverage tracker for balanced sampling
            project_root: Optional project root for skill-guided exploration
            domain: Optional domain name for resolving {domain} in skills_dir
            read_only_tools: Explicit read-only tool names (from ToolMetadataResolver)
        """
        self.config = config
        self.all_tools = all_tools
        self.coverage = coverage_tracker
        self.explicit_read_only_tools = set(read_only_tools or [])

        # Build tool name -> tool dict mapping
        self._tool_map: Dict[str, Dict[str, Any]] = {}
        self._tool_alias_map: Dict[str, str] = {}
        for tool in all_tools:
            name = tool.get("name") or tool.get("function", {}).get("name", "")
            if name:
                self._tool_map[name] = tool
                for alias in self._tool_aliases(name):
                    self._tool_alias_map.setdefault(alias, name)

        # Identify base tools and anchor tools
        self.base_tool_names = self._resolve_configured_tool_names(config.base_tools)

        # Anchor tools: use curated list if provided, else auto-detect (all non-base tools)
        if config.anchor_tools:
            self.anchor_tool_names = self._resolve_configured_tool_names(config.anchor_tools)
            logger.info(f"Using curated anchor tools: {sorted(self.anchor_tool_names)}")
        else:
            self.anchor_tool_names = set(self._tool_map.keys()) - self.base_tool_names

        # Identify read-only tools for retrieval mode
        self.read_only_tools = self._identify_read_only_tools()

        # Register tools with coverage tracker
        if self.coverage:
            self.coverage.register_tools(list(self._tool_map.keys()))

        # Initialize skill sampler if enabled
        self.skill_sampler = None
        if config.skill_guided.enabled and project_root:
            from .skill_sampler import SkillSampler

            try:
                self.skill_sampler = SkillSampler(
                    config.skill_guided,
                    project_root,
                    all_tools,
                    domain=domain,
                    coverage_tracker=coverage_tracker,
                )
                logger.info("SkillSampler initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize SkillSampler: {e}")

        logger.info(
            f"StageAwareSampler initialized: "
            f"{len(self.base_tool_names)} base tools, "
            f"{len(self.anchor_tool_names)} anchor tools, "
            f"{len(self.read_only_tools)} read-only tools"
        )

    @staticmethod
    def _tool_aliases(name: str) -> Set[str]:
        """Return matching aliases for namespaced MCP tool names."""
        aliases = {name}
        for delimiter in ("__", ".", "/", ":"):
            if delimiter in name:
                aliases.add(name.rsplit(delimiter, 1)[-1])
        return aliases

    def _resolve_configured_tool_names(self, configured_names: Optional[List[str]]) -> Set[str]:
        resolved = set()
        for configured in configured_names or []:
            live_name = self._tool_alias_map.get(configured)
            if live_name:
                resolved.add(live_name)
        return resolved

    @staticmethod
    def _safe_randint(lower: int, upper: int) -> int:
        """Sample an int while tolerating undersized candidate pools."""
        if upper <= 0:
            return 0
        lower = max(1, min(lower, upper))
        return random.randint(lower, upper)

    def _identify_read_only_tools(self) -> Set[str]:
        """Identify tools that don't modify state.

        Prefer explicit config-driven metadata when available and only fall back
        to name-based heuristics for previously unknown tools.
        """
        if self.explicit_read_only_tools:
            return self.explicit_read_only_tools & set(self._tool_map.keys())

        read_only_keywords = {
            "list", "read", "get", "search", "find",
            "show", "display", "info", "stat", "tree", "allowed",
        }
        write_keywords = {
            "write", "edit", "create", "mkdir", "move", "delete",
            "remove", "rename", "copy", "append", "modify", "update", "set",
        }

        read_only = set()
        for name in self._tool_map.keys():
            name_lower = name.lower()
            has_write = any(kw in name_lower for kw in write_keywords)
            has_read = any(kw in name_lower for kw in read_only_keywords)
            if has_read and not has_write:
                read_only.add(name)

        return read_only

    def sample(
        self,
        force_stage: Optional[str] = None,
        env_category: Optional[str] = None,
        current_iteration: Optional[int] = None,
        total_iterations: Optional[int] = None,
    ) -> SamplingResult:
        """Sample tools for the next episode.

        Args:
            force_stage: Optional stage name to force selection
            env_category: Optional environment category for skill filtering
            current_iteration: Zero-based or one-based collection progress marker.
            total_iterations: Total planned episodes for progressive scheduling.

        Returns:
            SamplingResult with stage, tier, tools, anchors, target_n, etc.
        """
        forced_tier = None
        if force_stage:
            stage = self.config.get_stage_by_name(force_stage)
            if not stage:
                logger.warning(
                    f"Forced stage {force_stage} not found, selecting automatically"
                )
                stage, forced_tier = self._select_stage_for_progress(
                    current_iteration, total_iterations
                )
        elif getattr(self.config, "selection_strategy", "progressive") == "progressive":
            stage, forced_tier = self._select_stage_for_progress(
                current_iteration, total_iterations
            )
        else:
            stage = self._select_stage()

        if stage.is_stage1():
            return self._sample_stage1(stage, forced_tier=forced_tier)
        else:
            return self._sample_stage2(stage, env_category)

    def _select_stage_for_progress(
        self,
        current_iteration: Optional[int],
        total_iterations: Optional[int],
    ) -> Tuple[StageConfig, Optional[DifficultyTierConfig]]:
        """Select a monotonically progressive exposure segment.

        Segments are weighted by tier.weight (stage-1) or stage.weight (stage-2).
        Progress walks segments proportionally to their configured weights,
        respecting the user's intent for how much of the total budget each
        difficulty tier should receive.
        """
        segments: List[Tuple[StageConfig, Optional[DifficultyTierConfig], float]] = []
        for stage in self.config.get_enabled_stages():
            if stage.is_stage1():
                for tier in stage.difficulty_tiers or []:
                    segments.append((stage, tier, tier.weight))
            else:
                segments.append((stage, None, stage.weight))

        if not segments:
            return self._select_stage(), None

        total_weight = sum(s[2] for s in segments)

        if not total_iterations or total_iterations <= 1:
            # Single iteration: weighted random across all segments
            r = random.uniform(0, total_weight)
            cumulative = 0.0
            for stage, tier, w in segments:
                cumulative += w
                if r <= cumulative:
                    return stage, tier
            return segments[-1][0], segments[-1][1]

        current = max(0, int(current_iteration or 0))
        progress = min(max(current / max(1, int(total_iterations)), 0.0), 0.999999)

        # Walk segments proportional to their weight
        cumulative = 0.0
        for stage, tier, w in segments:
            cumulative += w / total_weight
            if progress < cumulative:
                logger.info(
                    "Progressive exposure segment: %s%s (iteration=%s/%s, weight=%.2f)",
                    stage.name,
                    f":{tier.tier}" if tier else "",
                    current_iteration,
                    total_iterations,
                    w,
                )
                return stage, tier

        return segments[-1][0], segments[-1][1]

    def _select_stage(self) -> StageConfig:
        """Select a stage based on configured weights."""
        enabled_stages = self.config.get_enabled_stages()

        if not enabled_stages:
            # Fallback: create a default stage1 with hard tier
            return StageConfig(
                name="stage1_random_tool",
                weight=1.0,
                difficulty_tiers=[
                    DifficultyTierConfig(
                        tier="hard",
                        tool_count_min=3,
                        tool_count_max=10,
                        target_n_min=1,
                        target_n_max=5,
                        min_distinct_tools=1,
                        tool_pool="all",
                    )
                ],
            )

        # Weighted random selection
        total_weight = sum(s.weight for s in enabled_stages)
        r = random.uniform(0, total_weight)

        cumulative = 0
        for stage in enabled_stages:
            cumulative += stage.weight
            if r <= cumulative:
                return stage

        return enabled_stages[-1]

    def _select_tier(self, tiers: List[DifficultyTierConfig]) -> DifficultyTierConfig:
        """Select a difficulty tier based on configured weights."""
        total_weight = sum(t.weight for t in tiers)
        r = random.uniform(0, total_weight)

        cumulative = 0
        for tier in tiers:
            cumulative += tier.weight
            if r <= cumulative:
                return tier

        return tiers[-1]

    def _get_tools_by_names(self, names: List[str]) -> List[Dict[str, Any]]:
        """Get tool dicts by names."""
        return [self._tool_map[n] for n in names if n in self._tool_map]

    def _sample_stage1(
        self,
        stage: StageConfig,
        forced_tier: Optional[DifficultyTierConfig] = None,
    ) -> SamplingResult:
        """Sample for Stage 1 (random tool exposure with difficulty tiers).

        Unified method that replaces the old _sample_phase0/1/2/3 methods.
        Difficulty is controlled by the selected tier's tool_pool, tool_count,
        and target_n parameters.
        """
        tier = forced_tier or self._select_tier(stage.difficulty_tiers)

        # Determine candidates and sample based on tool_pool
        if tier.tool_pool == "base_only":
            candidates = list(self.base_tool_names)
            if not candidates:
                candidates = list(self._tool_map.keys())

            weights = {}
            if self.coverage:
                weights = self.coverage.get_coverage_weights(candidates)

            num_tools = self._safe_randint(
                tier.tool_count_min, min(tier.tool_count_max, len(candidates))
            )
            selected = self._weighted_sample(candidates, num_tools, weights)
            anchors = []

        elif tier.tool_pool == "base_plus_anchor":
            base_candidates = list(self.base_tool_names)
            anchor_candidates = list(self.anchor_tool_names)

            if not anchor_candidates:
                # Fallback to base_only if no anchors available
                logger.warning("No anchor tools available, falling back to base_only")
                candidates = base_candidates or list(self._tool_map.keys())
                weights = {}
                if self.coverage:
                    weights = self.coverage.get_coverage_weights(candidates)
                num_tools = self._safe_randint(
                    tier.tool_count_min, min(tier.tool_count_max, len(candidates))
                )
                selected = self._weighted_sample(candidates, num_tools, weights)
                anchors = []
            else:
                # Sample base tools
                base_weights = {}
                if self.coverage:
                    base_weights = self.coverage.get_coverage_weights(base_candidates)
                if not base_candidates:
                    logger.warning(
                        "No base tools available for base_plus_anchor tier; sampling anchors only"
                    )
                num_base = self._safe_randint(
                    tier.tool_count_min, min(tier.tool_count_max, len(base_candidates))
                )
                base_selected = self._weighted_sample(
                    base_candidates, num_base, base_weights
                )

                # Sample anchor tools
                anchor_weights = {}
                if self.coverage:
                    anchor_weights = self.coverage.get_coverage_weights(anchor_candidates)
                num_anchors = max(1, min(len(anchor_candidates), tier.anchor_count))
                anchors = self._weighted_sample(
                    anchor_candidates, num_anchors, anchor_weights
                )

                # Apply affinity rules if multiple anchors
                if tier.anchor_count >= 2:
                    anchors = self._apply_affinity_rules(anchors, anchor_candidates)

                selected = list(set(base_selected + anchors))
                weights = {**base_weights, **anchor_weights}

        else:  # "all"
            candidates = list(self._tool_map.keys())
            weights = {}
            if self.coverage:
                weights = self.coverage.get_coverage_weights(candidates)

            num_tools = self._safe_randint(
                tier.tool_count_min, min(tier.tool_count_max, len(candidates))
            )
            selected = self._weighted_sample(candidates, num_tools, weights)
            anchors = []

        self._ensure_prerequisite_tools(selected)

        # Sample target_n
        target_n = random.randint(tier.target_n_min, tier.target_n_max)

        # Classify selected tools
        base_used = [t for t in selected if t in self.base_tool_names]
        anchor_used = [t for t in selected if t in self.anchor_tool_names]

        return SamplingResult(
            stage=stage.name,
            tier=tier.tier,
            exposed_tools=self._get_tools_by_names(selected),
            anchors=anchors if tier.anchor_count > 0 else [],
            target_n=target_n,
            min_distinct_tools=tier.min_distinct_tools,
            is_retrieval_mode=None,
            base_tools_used=base_used,
            anchor_tools_used=anchor_used,
            sampling_weights=weights if tier.tool_pool != "base_only" else (weights if self.coverage else {}),
        )

    def _ensure_prerequisite_tools(self, selected: List[str]) -> None:
        """Expose lightweight prerequisite tools for precondition-heavy tool families."""
        selected_set = set(selected)

        def add_if_live(tool_name: str) -> None:
            if tool_name in self._tool_map and tool_name not in selected_set:
                selected.append(tool_name)
                selected_set.add(tool_name)

        if "list_allowed_directories" in self.base_tool_names:
            add_if_live("list_allowed_directories")

        filesystem_tools = [name for name in selected if name.startswith("filesystem-")]
        if filesystem_tools:
            add_if_live("filesystem-list_allowed_directories")
            add_if_live("filesystem-list_directory")

        browser_tools = [
            name
            for name in selected
            if name.startswith("playwright_with_chunk-browser_")
        ]
        if browser_tools:
            add_if_live("playwright_with_chunk-browser_navigate")
            add_if_live("playwright_with_chunk-browser_snapshot")

    def _sample_stage2(
        self, stage: StageConfig, env_category: Optional[str] = None
    ) -> SamplingResult:
        """Sample for Stage 2 (skill-guided deep exploration).

        Samples N skills from skill_tools.json, computes the union of their
        required tools, and determines target_n from skill ranges.
        """
        if not self.skill_sampler:
            logger.warning(
                "SKILL FALLBACK: SkillSampler not initialized — stage2 "
                "degrading to stage1 hard tier. Skill-guided exploration "
                "is NOT active. Check skill_guided config (enabled, "
                "skills_dir, skills_json) and ensure skill data files exist."
            )
            fallback_stage = StageConfig(
                name="stage1_random_tool",
                weight=1.0,
                difficulty_tiers=[
                    DifficultyTierConfig(
                        tier="hard",
                        tool_count_min=3,
                        tool_count_max=10,
                        target_n_min=3,
                        target_n_max=10,
                        min_distinct_tools=1,
                        tool_pool="all",
                    )
                ],
            )
            result = self._sample_stage1(fallback_stage)
            result.skill_fallback = True
            result.stage = "stage2_skill_guided"  # Preserve original intent in metadata
            return result

        # Sample N skills
        n_skills = random.randint(
            self.config.skill_guided.skills_min,
            self.config.skill_guided.skills_max,
        )
        skill_selections = self.skill_sampler.sample_skills(n_skills, env_category)

        # Compute exposed tools and target_n
        exposed_tools = self.skill_sampler.compute_exposed_tools(skill_selections)
        target_n = self.skill_sampler.compute_target_n(skill_selections)

        # Enforce stage n_min as a floor (skill-computed target_n must meet
        # the minimum bar).  Do NOT clamp to stage.n_max — the per-skill
        # tool_calls_range already defines a reasonable upper bound, and
        # multi-skill episodes naturally need a higher budget to satisfy
        # per-skill checkpoints.  Clamping down starves the agent of tool-
        # call budget and causes spurious incompletions.
        if stage.n_min is not None:
            target_n = max(stage.n_min, target_n)

        # Identify base vs anchor tools in exposed set
        exposed_names = [
            t.get("name") or t.get("function", {}).get("name", "")
            for t in exposed_tools
        ]
        required_checkpoint_tools = self._checkpoint_anchor_tools(skill_selections)
        anchors = [
            tool_name
            for tool_name in required_checkpoint_tools
            if tool_name in self._tool_map
        ]
        self._ensure_prerequisite_tools(exposed_names)
        if len(exposed_names) > len(exposed_tools):
            exposed_tools = self._get_tools_by_names(exposed_names)
        for anchor in anchors:
            if anchor not in exposed_names:
                exposed_names.append(anchor)
                exposed_tools.extend(self._get_tools_by_names([anchor]))
        base_used = [t for t in exposed_names if t in self.base_tool_names]
        anchor_used = [t for t in exposed_names if t in self.anchor_tool_names]

        logger.info(
            f"Skill-guided sampling: {n_skills} skills, "
            f"{len(exposed_tools)} tools, target_n={target_n}"
        )

        return SamplingResult(
            stage=stage.name,
            tier=None,
            exposed_tools=exposed_tools,
            anchors=anchors,
            target_n=target_n,
            min_distinct_tools=stage.min_distinct_tools,
            is_retrieval_mode=None,
            base_tools_used=base_used,
            anchor_tools_used=anchor_used,
            sampling_weights={},
            skill_selections=skill_selections,
        )

    def _checkpoint_anchor_tools(self, skill_selections: List[Any]) -> List[str]:
        """Resolve required checkpoint tools from sampled skills as soft anchors."""
        anchors: List[str] = []
        seen: Set[str] = set()
        for skill in skill_selections or []:
            for checkpoint in getattr(skill, "required_checkpoints", []) or []:
                tool_name = str(checkpoint.get("tool") or "").strip()
                if not tool_name or tool_name in seen:
                    continue
                live_name = self._tool_alias_map.get(tool_name, tool_name)
                if live_name in self._tool_map and live_name not in seen:
                    anchors.append(live_name)
                    seen.add(live_name)
        return anchors

    def _weighted_sample(
        self, candidates: List[str], n: int, weights: Dict[str, float]
    ) -> List[str]:
        """Sample n items from candidates with optional weights."""
        if not candidates:
            return []

        n = min(n, len(candidates))

        if not weights:
            return random.sample(candidates, n)

        # Weighted sampling without replacement
        selected = []
        remaining = list(candidates)

        for _ in range(n):
            if not remaining:
                break

            total_weight = sum(weights.get(c, 1.0) for c in remaining)
            if total_weight <= 0:
                choice = random.choice(remaining)
            else:
                r = random.uniform(0, total_weight)
                cumulative = 0
                choice = remaining[-1]
                for c in remaining:
                    cumulative += weights.get(c, 1.0)
                    if r <= cumulative:
                        choice = c
                        break

            selected.append(choice)
            remaining.remove(choice)

        return selected

    def _apply_affinity_rules(
        self, anchors: List[str], candidates: List[str]
    ) -> List[str]:
        """Apply affinity rules to add companion tools."""
        if not self.config.affinity_rules:
            return anchors

        result = list(anchors)

        for rule in self.config.affinity_rules:
            if rule.primary_tool in result:
                if random.random() < rule.probability:
                    for companion in rule.companion_tools:
                        if companion in candidates and companion not in result:
                            result.append(companion)
                            if not rule.required:
                                break

        return result

    def verify_anchors_called(
        self, sampling_result: SamplingResult, tools_called: List[str]
    ) -> Tuple[bool, List[str]]:
        """Verify that all required anchors were called."""
        if not sampling_result.anchors:
            return True, []

        tools_called_set = set(tools_called)
        missing = [a for a in sampling_result.anchors if a not in tools_called_set]

        return len(missing) == 0, missing

    def get_statistics(self) -> Dict[str, Any]:
        """Get sampler statistics."""
        return {
            "total_tools": len(self._tool_map),
            "base_tools": len(self.base_tool_names),
            "anchor_tools": len(self.anchor_tool_names),
            "read_only_tools": len(self.read_only_tools),
            "enabled_stages": [s.name for s in self.config.get_enabled_stages()],
            "affinity_rules": len(self.config.affinity_rules),
            "coverage_summary": self.coverage.get_summary() if self.coverage else None,
        }


# Backward compatibility alias
PhaseAwareSampler = StageAwareSampler
