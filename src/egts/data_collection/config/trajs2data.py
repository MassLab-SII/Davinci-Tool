from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from .tasks.filesystem import FilesystemTaskConfig
from .tasks.base import BaseTaskConfig


class ReplaySynthesisConfig(BaseModel):
    """Task-oriented replay synthesis inside collection."""

    enabled: bool = Field(
        default=False,
        description="Generate task-oriented replay episodes from collected exploration trajectories.",
    )
    max_problem_candidates: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum evidence-grounded problem candidates to consider.",
    )
    max_replay_attempts: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Maximum replay attempts from the same starting state.",
    )
    min_quality_tier: Literal["acceptable", "high_quality"] = Field(
        default="acceptable",
        description="Minimum replay quality tier to keep for training.",
    )
    tool_sequence_selection: Literal["heuristic", "universal"] = Field(
        default="heuristic",
        description="Tool-use subsequence selection strategy: 'heuristic' (keyword-based) or 'universal' (data-flow-based).",
    )
    verify_final_state: bool = Field(
        default=True,
        description="Verify replay final state or retrieval evidence before accepting.",
    )
    save_failed_replays: bool = Field(
        default=True,
        description="Save rejected replay metadata for test-refine analysis.",
    )
    max_selected_tool_calls: int = Field(
        default=12,
        ge=1,
        le=50,
        description="Maximum selected tool calls allowed in one replay sample.",
    )
    harness_mode: Literal["full", "strict", "disabled"] = Field(
        default="disabled",
        description=(
            "How the harness constrains model execution during replay. "
            "'full' (recommended): model re-executes all tools naturally, producing task-oriented "
            "thoughts. Forced-fallback threshold controls when to use skeleton+polish. "
            "'strict': exposes only the expected tool each step (industrial-grade). "
            "'disabled': deterministic replay + rule skeleton + always polish."
        ),
    )
    harness_max_retries_per_step: int = Field(
        default=2,
        ge=1,
        le=5,
        description="Max retries per step when model calls the wrong tool.",
    )
    harness_model: Literal["trajectory_collection", "nl_rewrite"] = Field(
        default="trajectory_collection",
        description="Which model config to use for harness-driven replay thinking.",
    )
    preserve_failure_recovery_chains: bool = Field(
        default=True,
        description="When True, preserves failure->reflection->success chains in tool sequence selection.",
    )
    dependency_relevance_filter: bool = Field(
        default=True,
        description="When True, dependency calls are filtered for relevance to the mutation target.",
    )
    llm_problem_synthesis: bool = Field(
        default=True,
        description="When True, use LLM to generate problems from evidence (primary path).",
    )
    max_dependency_distance: int = Field(
        default=5,
        ge=0,
        le=20,
        description="Maximum step distance for a call to be considered a dependency of a mutation.",
    )
    max_selected_mutations: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of mutation calls to include in the selected tool sequence.",
    )
    polish_enabled: bool = Field(
        default=True,
        description="When True, polish the rule-generated skeleton messages with LLM.",
    )
    polish_model: Literal["nl_rewrite", "judge_model"] = Field(
        default="judge_model",
        description=(
            "Which model config to use for polish. "
            "'judge_model' (default, low temp ~0.1): minimal hallucination, "
            "conservative rewrites — best for production data quality. "
            "'nl_rewrite' (higher temp ~0.7): more creative/diverse phrasing, "
            "but higher risk of fabricating details not in the tool results. "
            "Use 'judge_model' unless you specifically need stylistic diversity "
            "and have quality gates to catch fabrication."
        ),
    )
    enable_quality_judge: bool = Field(
        default=True,
        description="When True, run dual-judge (hard+soft) on replay trajectories for quality scoring.",
    )
    judge_hard_weight: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Weight of hard judge (factual consistency) in quality score.",
    )
    judge_soft_weight: float = Field(
        default=0.20,
        ge=0.0,
        le=1.0,
        description="Weight of soft judge (reasoning quality and coherence) in quality score.",
    )
    judge_dual_bonus: float = Field(
        default=0.10,
        ge=0.0,
        le=1.0,
        description="Bonus added when both hard and soft judges pass.",
    )
    judge_threshold_high: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Minimum quality score for high_quality tier.",
    )
    judge_threshold_acceptable: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Minimum quality score for acceptable tier.",
    )
    min_original_tool_calls: int = Field(
        default=3,
        ge=1,
        le=50,
        description="Minimum original tool calls required to process an episode. Skip episodes with fewer calls.",
    )
    min_selected_tool_calls: int = Field(
        default=2,
        ge=1,
        le=50,
        description="Minimum selected tool calls after tool sequence selection. Skip if selection collapses below this.",
    )
    tool_name_noise_extra: Optional[List[str]] = Field(
        default=None,
        description="Tool name tokens to ADD to the default _TOOL_NAME_NOISE set for this world.",
    )
    tool_name_noise_exclude: Optional[List[str]] = Field(
        default=None,
        description="Tool name tokens to REMOVE from the default _TOOL_NAME_NOISE set for this world.",
    )


class Trajs2DataFiltersConfig(BaseModel):
    """Quality filter configuration for trajs2data."""

    min_steps: int = Field(
        default=2, description="Minimum successful tool calls (soft filter)"
    )
    min_changes: int = Field(
        default=1, description="Minimum filesystem changes (soft filter)"
    )
    max_changes: int = Field(
        default=100, description="Maximum filesystem changes (soft filter)"
    )
    max_failure_rate: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Maximum allowed failed_tool_calls / total_tool_calls ratio (soft filter)",
    )


class DeduplicationConfig(BaseModel):
    """Deduplication configuration for trajs2data."""

    enabled: bool = Field(default=True, description="Enable deduplication filter")
    max_trajectories_per_problem: int = Field(
        default=3, description="Max different trajectories to keep per unique problem"
    )
    use_semantic: bool = Field(
        default=False,
        description="Use embedding-based semantic deduplication (requires API)",
    )
    problem_similarity_threshold: float = Field(
        default=0.90,
        description="Cosine similarity threshold for 'same problem' (semantic mode)",
    )
    trajectory_similarity_threshold: float = Field(
        default=0.85,
        description="Threshold for 'same trajectory' (signature comparison)",
    )
    vector_store_path: Optional[str] = Field(
        default=None,
        description="Path for persistent vector store (ChromaDB). None = in-memory",
    )
    embedding_model: str = Field(
        default="text-embedding-v4",
        description="Model name for embeddings (OpenAI-compatible API)",
    )
    embedding_base_url: Optional[str] = Field(
        default=None,
        description="Base URL for embedding API (if different from default)",
    )
    embedding_api_key: Optional[str] = Field(
        default=None,
        description="API key for embedding API (if different from default)",
    )


class DifficultyTierConfig(BaseModel):
    """A difficulty tier within Stage 1 random tool exposure."""

    tier: str = Field(..., description="Tier name: simple, medium, hard")
    weight: float = Field(default=1.0, description="Sampling weight for this tier")
    tool_count_min: int = Field(default=1, description="Min tools to expose")
    tool_count_max: int = Field(default=5, description="Max tools to expose")
    target_n_min: int = Field(default=1, description="Min target successful tool calls")
    target_n_max: int = Field(default=5, description="Max target successful tool calls")
    min_distinct_tools: int = Field(
        default=1, description="Min distinct tools to use"
    )
    tool_pool: str = Field(
        default="all",
        description="Tool pool: 'base_only', 'base_plus_anchor', 'all'",
    )
    anchor_count: int = Field(
        default=0, description="Number of anchor tools required (0=no constraint)"
    )


class StageConfig(BaseModel):
    """Configuration for a single stage."""

    name: str = Field(..., description="Stage name")
    enabled: bool = Field(default=True, description="Whether this stage is enabled")
    weight: float = Field(
        default=1.0, description="Sampling weight for stage selection"
    )
    description: str = Field(default="", description="Human-readable description")

    # Stage 1 specific: difficulty tiers
    difficulty_tiers: Optional[list[DifficultyTierConfig]] = Field(
        default=None,
        description="Difficulty tiers for Stage 1 (None for Stage 2)",
    )

    # Stage 2 specific: flat n_min/n_max (skill-guided computes tools from skills)
    n_min: Optional[int] = Field(
        default=None, description="Min target_n (Stage 2)"
    )
    n_max: Optional[int] = Field(
        default=None, description="Max target_n (Stage 2)"
    )
    min_distinct_tools: int = Field(
        default=1, description="Min distinct tools"
    )

    def is_stage1(self) -> bool:
        return self.difficulty_tiers is not None

    def is_stage2(self) -> bool:
        return self.difficulty_tiers is None and self.n_min is not None


class AffinityRuleConfig(BaseModel):
    """Configuration for tool affinity/grouping rules."""

    name: str = Field(..., description="Rule name")
    primary_tool: str = Field(..., description="Primary tool that triggers the rule")
    companion_tools: list[str] = Field(
        default_factory=list, description="Tools that should often appear with primary"
    )
    required: bool = Field(
        default=False, description="Whether companions are required (vs. preferred)"
    )
    probability: float = Field(
        default=0.5,
        description="Probability of applying this rule when primary is selected",
    )


class CoverageConfig(BaseModel):
    """Configuration for tool coverage tracking and optimization."""

    min_success_per_tool: int = Field(
        default=10, description="Minimum successful uses per tool for 'covered' status"
    )
    strategy: str = Field(
        default="balanced",
        description="Coverage strategy: 'balanced', 'exhaustive', 'priority_low'",
    )
    track_file: str = Field(
        default="coverage.json",
        description="Filename for coverage tracking (relative to output)",
    )
    rebalance_interval: int = Field(
        default=50, description="Rebalance sampling weights every N episodes"
    )
    coverage_deadline_enabled: bool = Field(
        default=False, description="Enable coverage deadline enforcement"
    )
    coverage_deadline_samples: int = Field(
        default=100, description="Must cover target % of tools by this sample count"
    )
    coverage_deadline_percentage: float = Field(
        default=0.8, description="Required coverage percentage by deadline (0-1)"
    )
    force_uncovered_anchor: bool = Field(
        default=True,
        description="Force uncovered tools as anchors when behind deadline",
    )


class SkillGuidedConfig(BaseModel):
    """Configuration for skill-guided exploration phase."""

    enabled: bool = Field(default=False, description="Enable skill-guided exploration")
    skills_dir: str = Field(
        default="src/egts/skills/filesystem",
        description=(
            "Directory containing skill definitions (relative to project root). "
            "Supports {domain} placeholder for multi-domain worlds, e.g. 'src/egts/skills/mcpmark-{domain}'. "
            "When {domain} is present, the actual domain is resolved at runtime from /admin/reset."
        ),
    )
    skills_json: str = Field(
        default="skill_tools.json",
        description="JSON file defining available skills",
    )
    skills_min: int = Field(
        default=1, ge=1, le=3, description="Min skills per episode"
    )
    skills_max: int = Field(
        default=2, ge=1, le=3, description="Max skills per episode"
    )
    skill_selection_strategy: str = Field(
        default="random",
        description="Strategy: 'random' or 'coverage_weighted'",
    )
    max_steps_per_skill: int = Field(
        default=15,
        ge=5,
        le=30,
        description="Maximum turns per skill before forcing completion",
    )


class ToolCurriculumConfig(BaseModel):
    """Configuration for tool curriculum learning (2-stage architecture)."""

    selection_strategy: Literal["progressive", "weighted_random"] = Field(
        default="progressive",
        description=(
            "How to select exposure stages. 'progressive' advances through "
            "base-oriented, anchor-oriented, frontier, and skill-guided segments "
            "by collection progress; 'weighted_random' preserves legacy behavior."
        ),
    )
    base_tools: list[str] = Field(
        default_factory=lambda: [
            "list_allowed_directories",
            "list_directory",
            "directory_tree",
            "create_directory",
            "write_file",
        ],
        description="Base tools that are truly input-independent",
    )
    anchor_tools: Optional[list[str]] = Field(
        default=None,
        description="Curated anchor tools (None = auto-detect as all non-base tools)",
    )
    stages: list[StageConfig] = Field(
        default_factory=lambda: [
            StageConfig(
                name="stage1_random_tool",
                weight=1.0,
                description="Random tool exposure breadth exploration",
                difficulty_tiers=[
                    DifficultyTierConfig(
                        tier="simple",
                        weight=0.2,
                        tool_count_min=1,
                        tool_count_max=3,
                        target_n_min=1,
                        target_n_max=3,
                        min_distinct_tools=1,
                        tool_pool="base_only",
                        anchor_count=0,
                    ),
                    DifficultyTierConfig(
                        tier="medium",
                        weight=0.5,
                        tool_count_min=3,
                        tool_count_max=6,
                        target_n_min=2,
                        target_n_max=8,
                        min_distinct_tools=2,
                        tool_pool="base_plus_anchor",
                        anchor_count=1,
                    ),
                    DifficultyTierConfig(
                        tier="hard",
                        weight=0.3,
                        tool_count_min=5,
                        tool_count_max=15,
                        target_n_min=3,
                        target_n_max=15,
                        min_distinct_tools=3,
                        tool_pool="all",
                        anchor_count=0,
                    ),
                ],
            ),
            StageConfig(
                name="stage2_skill_guided",
                weight=1.0,
                description="Skill-guided deep exploration",
                n_min=8,
                n_max=30,
                min_distinct_tools=3,
            ),
        ],
        description="Two-stage exploration: random tool exposure + skill-guided",
    )
    affinity_rules: list[AffinityRuleConfig] = Field(
        default_factory=list,
        description="Tool affinity rules for Stage 1 multi-anchor sampling",
    )
    coverage: CoverageConfig = Field(
        default_factory=CoverageConfig,
        description="Coverage tracking and optimization settings",
    )
    skill_guided: SkillGuidedConfig = Field(
        default_factory=SkillGuidedConfig,
        description="Skill-guided exploration configuration",
    )

    def get_enabled_stages(self) -> list[StageConfig]:
        return [s for s in self.stages if s.enabled]

    def get_stage_by_name(self, name: str) -> Optional[StageConfig]:
        for s in self.stages:
            if s.name == name:
                return s
        return None


class RecoverableModeConfig(BaseModel):
    """Configuration for recoverable trajectory collection."""

    enabled: bool = Field(
        default=False, description="Enable recoverable mode with checkpoint/rollback"
    )
    max_failures: int = Field(
        default=3, description="Max failures before salvaging episode"
    )
    max_failures_per_tool: int = Field(
        default=2, description="Max failures per tool before skipping"
    )
    max_retries_before_rollback: int = Field(
        default=1, description="Level 1: in-place retries before rollback (PRD 4.1)"
    )
    enable_filesystem_snapshots: bool = Field(
        default=True, description="Enable filesystem state snapshots"
    )
    snapshot_strategy: str = Field(
        default="hardlink",
        description="Snapshot strategy: 'hardlink', 'full', 'incremental'",
    )


class ReplayVerificationConfig(BaseModel):
    """Configuration for Phase4 replay verification."""

    enabled: bool = Field(default=False, description="Enable replay verification")
    similarity_threshold: float = Field(
        default=0.8, description="Diff similarity threshold for passing (0-1)"
    )
    max_replay_steps: int = Field(
        default=15, description="Max steps for replay attempt"
    )
    skip_retrieval: bool = Field(
        default=True, description="Skip verification for retrieval mode"
    )
    fail_on_mismatch: bool = Field(
        default=False, description="Reject samples that fail verification"
    )


class SelfQuestioningConfig(BaseModel):
    """Configuration for Self-Questioning candidate generation."""

    enabled: bool = Field(default=False, description="Enable self-questioning mode")
    num_candidates: int = Field(
        default=3, description="Number of candidates to generate"
    )
    novelty_weight: float = Field(
        default=0.6, description="Weight for novelty in selection"
    )
    coverage_weight: float = Field(
        default=0.4, description="Weight for coverage in selection"
    )
    use_embeddings: bool = Field(
        default=False, description="Use embeddings for novelty (requires API)"
    )


class HindsightConfig(BaseModel):
    """Configuration for hindsight reasoning (PRD 4.2 Step 3)."""

    enabled: bool = Field(
        default=False, description="Enable hindsight thought rewriting"
    )
    rewrite_thoughts: bool = Field(
        default=True,
        description="Rewrite trajectory thoughts with 'God mode' reasoning",
    )


class DataSynthesisConfig(BaseModel):
    """Configuration for offline data_synthesis quality loops."""

    max_problem_refine_loops: int = Field(
        default=3,
        ge=1,
        le=10,
        description=(
            "Maximum synth-judge refinement loops for problem synthesis in "
            "data_synthesis pipeline"
        ),
    )
    max_trajectory_refine_loops: int = Field(
        default=3,
        ge=1,
        le=10,
        description=(
            "Maximum synth-judge refinement loops for trajectory rewriting in "
            "data_synthesis pipeline"
        ),
    )
    require_planning_step: bool = Field(
        default=True,
        description=(
            "Require rewritten trajectory to start with an explicit planning thought"
        ),
    )
    require_final_answer: bool = Field(
        default=True,
        description=(
            "Require rewritten trajectory to end with a final answer/completion summary"
        ),
    )
    enable_heuristic_fallback: bool = Field(
        default=True,
        description=(
            "Enable rule-based fallback acceptance when LLM judge/rewrite is unstable"
        ),
    )
    min_step_coverage_ratio: float = Field(
        default=0.75,
        ge=0.5,
        le=1.0,
        description=(
            "Minimum step-reasoning coverage ratio for heuristic fallback acceptance"
        ),
    )
    save_llm_io: bool = Field(
        default=False,
        description=(
            "Persist model call inputs/outputs (including judge/rewrite calls) for "
            "diagnosis in offline data_synthesis"
        ),
    )
    llm_io_file: str = Field(
        default="",
        description=(
            "Optional output path for LLM trace JSON. Empty => "
            "same dir as synthesized output with default filename."
        ),
    )
    llm_io_include_prompts: bool = Field(
        default=True,
        description="Whether to store full prompt messages in LLM trace output",
    )
    llm_io_max_text_chars: int = Field(
        default=0,
        ge=0,
        le=2000000,
        description=(
            "Max characters per stored text field in LLM traces. "
            "0 means no truncation."
        ),
    )
    rewrite_context_max_chars: int = Field(
        default=5000,
        ge=500,
        le=50000,
        description=(
            "Max chars for original trajectory excerpt passed to stage-2 rewrite prompt"
        ),
    )
    rewrite_tool_sequence_max_steps: int = Field(
        default=40,
        ge=3,
        le=300,
        description=(
            "Max number of tool steps included in compact stage-2 tool sequence context"
        ),
    )
    rewrite_segment_size: int = Field(
        default=6,
        ge=3,
        le=20,
        description=(
            "Max tool calls per segment in segmented trajectory rewrite. "
            "Trajectories longer than this are split into multiple LLM rewrite "
            "passes with running context summaries to avoid attention dilution."
        ),
    )
    compress_tool_sequence: bool = Field(
        default=False,
        description=(
            "Enable tool-call sequence compression before rewrite. Removes "
            "redundant exploration calls (same tool, same target) while "
            "preserving calls whose outputs are referenced by later steps."
        ),
    )
    compress_min_keep_ratio: float = Field(
        default=0.5,
        ge=0.3,
        le=1.0,
        description="Minimum ratio of original tool calls to preserve during compression.",
    )
    skip_invalid_structure: bool = Field(
        default=True,
        description=(
            "Skip episodes whose trajectory has structural mismatches "
            "(assistant tool_calls vs tool outputs vs trajectory.tool_calls)."
        ),
    )
    reject_failure_only_tools: bool = Field(
        default=True,
        description=(
            "Skip episodes before synthesis if any tool appears only as failed calls "
            "and never succeeds in the trajectory."
        ),
    )
    max_tool_failure_rate: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description=(
            "Skip episodes before synthesis when failed_tool_calls / total_tool_calls "
            "exceeds this threshold."
        ),
    )
    trajectory_mode: Literal["llm_rewrite", "fallback_polish", "fallback_only"] = Field(
        default="llm_rewrite",
        description=(
            "Stage-2 trajectory rewrite mode: llm_rewrite (default), "
            "fallback_polish (fallback skeleton + polish), fallback_only"
        ),
    )
    use_dual_judge: bool = Field(
        default=True,
        description=(
            "Whether to use hard+soft dual-judge for trajectory validation "
            "(False = legacy single-judge)"
        ),
    )
    max_polish_loops: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Max polish iterations in fallback_polish mode",
    )
    polish_model: str = Field(
        default="synthesis_model",
        description=(
            "Model alias/name used by fallback polish. "
            "Common aliases: synthesis_model, nl_rewrite, judge_model"
        ),
    )
    soft_judge_threshold: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Reserved soft-judge threshold for future strict gating. "
            "Currently soft judge remains advisory."
        ),
    )
    quality_policy: Literal["legacy_all", "high_and_acceptable", "high_only"] = Field(
        default="legacy_all",
        description=(
            "Training-set selection policy after Stage-2 quality scoring. "
            "legacy_all keeps current behavior for backward compatibility."
        ),
    )
    quality_gate_enabled: bool = Field(
        default=False,
        description=(
            "Enable training-set quality gate. "
            "When false, quality is computed for shadow report only."
        ),
    )
    fallback_for_training: bool = Field(
        default=False,
        description=(
            "Whether fallback_based trajectories are allowed into training set "
            "when quality gate is enabled."
        ),
    )
    fallback_min_tool_steps: int = Field(
        default=3,
        ge=1,
        le=100,
        description=(
            "Minimum tool steps required for a fallback-based trajectory "
            "to be eligible for training. Only applies when fallback_for_training "
            "is enabled and quality gate is active. Shorter trajectories are "
            "excluded regardless."
        ),
    )
    quality_score_enabled: bool = Field(
        default=True,
        description=(
            "Whether to compute unified quality_score in Stage-2 outputs "
            "(recommended for quality analytics and filtering)."
        ),
    )
    min_quality_score_high: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Minimum quality_score threshold for high_quality tier",
    )
    min_quality_score_acceptable: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Minimum quality_score threshold for acceptable tier",
    )
    quality_shadow_report: bool = Field(
        default=True,
        description=(
            "Emit quality tier/score distribution in run summary logs/records "
            "even when gate is disabled."
        ),
    )

    # --- Dataset-level deduplication (used by data_synthesis pipeline) ---
    dedup_enabled: bool = Field(
        default=False,
        description="Enable dataset-level deduplication in data_synthesis pipeline",
    )
    dedup_mode: str = Field(
        default="hash",
        description="Dedup strategy: 'hash' | 'semantic' | 'hybrid'",
    )
    dedup_problem_similarity_threshold: float = Field(
        default=0.90, ge=0.5, le=1.0,
        description="Cosine similarity threshold for 'same problem' (semantic/hybrid)",
    )
    dedup_trajectory_similarity_threshold: float = Field(
        default=0.85, ge=0.5, le=1.0,
        description="Threshold for 'same trajectory' via signature comparison",
    )
    dedup_max_variants_per_problem: int = Field(
        default=3, ge=1, le=20,
        description="Max trajectory variants to keep per problem cluster",
    )
    dedup_embedding_model: str = Field(
        default="text-embedding-v4",
        description="Embedding model name (semantic/hybrid mode)",
    )
    dedup_embedding_base_url: Optional[str] = Field(
        default=None, description="Embedding API base URL (None = maas default)",
    )
    dedup_embedding_api_key: Optional[str] = Field(
        default=None, description="Embedding API key (None = maas default)",
    )
    dedup_vector_store_path: Optional[str] = Field(
        default=None, description="ChromaDB vector store path (None = in-memory)",
    )
    dedup_state_file: str = Field(
        default="dedup_state.json",
        description="Filename for persisting dedup state (relative to output dir)",
    )

    # --- Pre-screening (fast metadata-only filter executed before parallel synthesis) ---
    pre_screening_enabled: bool = Field(
        default=True,
        description=(
            "When True, apply fast metadata-only heuristics before synthesis "
            "to reject episodes that cannot produce useful training data "
            "(no state changes, too few tool calls, read-only trajectories, etc.). "
            "Rejected episodes are recorded in meta for resume support."
        ),
    )
    pre_screening_min_tool_calls: int = Field(
        default=2,
        ge=1,
        le=100,
        description="Minimum total tool calls required to pass pre-screening.",
    )
    pre_screening_min_distinct_tools: int = Field(
        default=1,
        ge=1,
        le=50,
        description="Minimum distinct tools attempted to pass pre-screening.",
    )

    # --- Per-episode timeout (replaces brittle coordinator-level timeout) ---
    episode_timeout_seconds: int = Field(
        default=600,
        ge=30,
        le=1800,
        description=(
            "Maximum wall-clock seconds allowed per individual episode during "
            "parallel synthesis. If exceeded, the episode is rejected with "
            "rejected_stage='episode_timeout' but all other workers continue."
        ),
    )


class ExperienceManagerConfig(BaseModel):
    """Configuration for experience management (PRD 4.7)."""

    model_config = {"populate_by_name": True}

    enabled: bool = Field(default=False, description="Enable experience manager")
    store_path: str = Field(
        default="experience_store.json",
        description="Path to experience store file (relative to output dir)",
    )
    max_experiences: int = Field(default=100, alias="max_skills", description="Maximum experiences to retain")
    similarity_threshold: float = Field(
        default=0.85, description="Threshold for considering experiences as duplicates"
    )
    retrieve_top_k: int = Field(
        default=3, description="Number of experiences to retrieve for hints"
    )
    experience_template: str = Field(
        default="\n[Relevant Experience]\n{experience}\n",
        alias="skill_template",
        description="Template for injecting experiences into prompts",
    )
    extract_on_success: bool = Field(
        default=True, description="Extract experiences from successful trajectories"
    )
    inject_to_prompt: bool = Field(
        default=True, description="Inject retrieved experiences into exploration prompts"
    )
    namespace_scoping_enabled: bool = Field(
        default=False,
        description="Scope experience retrieval to the current output_namespace",
    )


class EfficiencyMonitorConfig(BaseModel):
    """Configuration for efficiency monitoring and auto-adjustment (PRD 4.5)."""

    enabled: bool = Field(default=False, description="Enable efficiency monitoring")
    min_success_rate: float = Field(
        default=0.1, description="Minimum saved/attempted ratio (0-1)"
    )
    window_size: int = Field(
        default=20, description="Window size for rolling rate calculation"
    )
    auto_adjust: bool = Field(
        default=True, description="Auto-adjust strategy on low efficiency"
    )
    reduce_target_n_on_low_rate: bool = Field(
        default=True, description="Reduce target_n when rate is low"
    )
    target_n_reduction_step: int = Field(
        default=1, description="How much to reduce target_n each time"
    )
    min_target_n: int = Field(default=1, description="Minimum target_n after reduction")


class Trajs2DataConfig(BaseModel):
    """Configuration for Trajs2Data pipeline mode."""

    language: str = Field(
        default="en", description="Output language: 'en' (English) or 'zh' (Chinese)"
    )
    max_attempts: int = Field(
        default=3, description="Maximum retry attempts per episode"
    )
    save_filtered: bool = Field(
        default=True, description="Save filtered trajectories for debugging"
    )
    exploration_system_prompt: Optional[str] = Field(
        default=None,
        description="Custom system prompt for exploration (None = use default)",
    )
    use_exploration_objective: bool = Field(
        default=True,
        description=(
            "When True, the exploration prompt asks the model to conceive a "
            "concrete task objective from world context before exploring. "
            "This produces goal-directed trajectories that are easier to "
            "synthesize into high-quality training samples."
        ),
    )
    synthesis_in_collection: bool = Field(
        default=True,
        description=(
            "Whether to run problem synthesis/hindsight inside data_collection. "
            "Set False to save raw episodes and defer synthesis to data_synthesis."
        ),
    )

    # Task specific configuration (Polymorphic)
    # Default to filesystem for backward compatibility if needed, but better to require it
    # For now, let's keep it optional but ideally it should be required
    # But wait, config.yaml might not have this structure yet.
    # We will assume config.yaml will be updated or we provide a default FilesystemTaskConfig

    # This field replaces the old 'filesystem' field
    # We keep 'filesystem' for now if we want backward compat, but the goal is refactoring.
    # Let's add 'task' field.
    task: BaseTaskConfig = Field(default_factory=FilesystemTaskConfig)

    # Tool curriculum learning
    tool_curriculum: ToolCurriculumConfig = Field(default_factory=ToolCurriculumConfig)
    filters: Trajs2DataFiltersConfig = Field(default_factory=Trajs2DataFiltersConfig)
    deduplication: DeduplicationConfig = Field(default_factory=DeduplicationConfig)
    recoverable: RecoverableModeConfig = Field(default_factory=RecoverableModeConfig)
    replay_verification: ReplayVerificationConfig = Field(
        default_factory=ReplayVerificationConfig
    )
    replay_synthesis: ReplaySynthesisConfig = Field(
        default_factory=ReplaySynthesisConfig
    )
    self_questioning: SelfQuestioningConfig = Field(
        default_factory=SelfQuestioningConfig
    )
    efficiency_monitor: EfficiencyMonitorConfig = Field(
        default_factory=EfficiencyMonitorConfig
    )
    hindsight: HindsightConfig = Field(default_factory=HindsightConfig)
    data_synthesis: DataSynthesisConfig = Field(default_factory=DataSynthesisConfig)
    experience_manager: ExperienceManagerConfig = Field(
        default_factory=ExperienceManagerConfig
    )

    # Deprecated fields (kept for compatibility during migration if needed, or removed)
    # The 'filesystem' field is removed in favor of 'task'
    # But to support existing yaml that has 'filesystem', we might need a root validator.
