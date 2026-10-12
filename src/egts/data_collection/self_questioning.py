"""Self-Questioning module for candidate task generation and selection.

Implements the Self-Questioning paradigm from AgentEvolver:
1. Generate multiple candidate tasks from trajectory
2. Compute novelty scores using embedding similarity
3. Select the most novel candidate

This helps reduce template-like problems by encouraging diversity
in task descriptions.
"""

import logging
import json
import re
import math
import hashlib
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, TYPE_CHECKING

from prompts import PromptLoader

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class CandidateTask:
    """A candidate task generated from trajectory."""

    problem: str
    context: str = ""
    expected_outcome: str = ""

    # Scoring
    novelty_score: float = 0.0  # Lower similarity to existing = higher novelty
    coverage_score: float = 0.0  # Coverage of trajectory tools
    executability_score: float = 1.0  # Assumed executable since from trajectory

    # Combined score
    final_score: float = 0.0

    def compute_final_score(
        self, novelty_weight: float = 0.6, coverage_weight: float = 0.4
    ) -> float:
        """Compute weighted final score.

        Args:
            novelty_weight: Weight for novelty score
            coverage_weight: Weight for coverage score

        Returns:
            The computed final score
        """
        self.final_score = (
            self.novelty_score * novelty_weight + self.coverage_score * coverage_weight
        )
        return self.final_score

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "problem": self.problem,
            "context": self.context,
            "expected_outcome": self.expected_outcome,
            "novelty_score": self.novelty_score,
            "coverage_score": self.coverage_score,
            "final_score": self.final_score,
        }


@dataclass
class SelfQuestioningResult:
    """Result of self-questioning process."""

    candidates: List[CandidateTask]
    selected: CandidateTask
    selection_reason: str
    existing_problems_checked: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "num_candidates": len(self.candidates),
            "selected_problem": self.selected.problem,
            "selection_reason": self.selection_reason,
            "existing_problems_checked": self.existing_problems_checked,
            "candidates": [c.to_dict() for c in self.candidates],
        }


class CandidateGenerator:
    """Generates multiple candidate task descriptions from a trajectory."""

    def __init__(
        self,
        maas_client,
        model_config,
        num_candidates: int = 3,
        language: str = "en",
        mcp_server: str = "filesystem",
    ):
        """Initialize the candidate generator.

        Args:
            maas_client: Client for LLM API calls
            model_config: Model configuration
            num_candidates: Number of candidates to generate
            language: Output language ('en' or 'zh')
        """
        self.maas_client = maas_client
        self.model_config = model_config
        self.num_candidates = num_candidates
        self.language = language
        self.mcp_server = mcp_server
        self.prompt_loader = PromptLoader(mcp_server)

    async def generate_candidates(
        self,
        intent_spec,  # IntentSpec or RetrievalSpec
        tools_used: List[str],
        sample_changes: List[Dict[str, Any]],
    ) -> List[CandidateTask]:
        """Generate multiple candidate task descriptions.

        Args:
            intent_spec: The intent specification from trajectory
            tools_used: List of tools used in trajectory
            sample_changes: Sample file changes for context

        Returns:
            List of CandidateTask objects
        """
        prompt = self._build_multi_candidate_prompt(
            intent_spec, tools_used, sample_changes
        )

        messages = [
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": prompt},
        ]

        try:
            response = await self.maas_client.generate_completion(
                messages=messages, model_config=self.model_config, tools=None
            )

            content = response.get("content", "")
            candidates = self._parse_candidates(content)

        except Exception as e:
            logger.warning(f"Failed to generate candidates: {e}")
            candidates = []

        # Ensure we have at least one candidate
        if not candidates:
            candidates = [
                CandidateTask(
                    problem=f"Process the files using {', '.join(tools_used[:3])}.",
                    context="Fallback task description",
                )
            ]

        return candidates

    def _get_system_prompt(self) -> str:
        """Get system prompt for candidate generation."""
        return self.prompt_loader.get_self_questioning_system(language=self.language)

    def _build_multi_candidate_prompt(
        self, intent_spec, tools_used: List[str], sample_changes: List[Dict[str, Any]]
    ) -> str:
        """Build prompt for multi-candidate generation."""
        # Handle both IntentSpec and dict
        if hasattr(intent_spec, "primary_action"):
            action = intent_spec.primary_action
            category = getattr(
                intent_spec.task_category, "value", str(intent_spec.task_category)
            )
        else:
            action = intent_spec.get("primary_action", "unknown")
            category = intent_spec.get("task_category", "unknown")

        changes_str = (
            json.dumps(sample_changes[:3], indent=2) if sample_changes else "[]"
        )
        tools_text = ", ".join(tools_used)

        return self.prompt_loader.get_self_questioning_user(
            language=self.language,
            action=action,
            category=category,
            tools_used=tools_text,
            sample_changes=changes_str,
            sample_operations=changes_str,
            sql_patterns="unknown",
        )

    def _parse_candidates(self, content: str) -> List[CandidateTask]:
        """Parse candidates from LLM response.

        Args:
            content: Raw LLM response content

        Returns:
            List of parsed CandidateTask objects
        """
        # Try to find JSON in the response
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            try:
                data = json.loads(json_match.group())
                candidates = data.get("candidates", [])
                return [
                    CandidateTask(
                        problem=c.get("problem", ""),
                        context=c.get("context", ""),
                        expected_outcome=c.get("expected_outcome", ""),
                    )
                    for c in candidates
                    if c.get("problem")
                ]
            except json.JSONDecodeError:
                pass

        return []


class NoveltySelector:
    """Selects the most novel candidate using embedding similarity."""

    # Tool keywords for coverage computation
    TOOL_KEYWORDS = {
        "list_directory": ["list", "directory", "folder", "contents", "browse"],
        "read_file": ["read", "content", "file", "look at", "view", "open"],
        "write_file": ["write", "create", "save", "put", "new file"],
        "move_file": ["move", "relocate", "transfer"],
        "edit_file": ["edit", "modify", "change", "update", "alter"],
        "create_directory": ["create", "make", "directory", "folder", "mkdir"],
        "delete_file": ["delete", "remove", "clean", "erase"],
        "search_files": ["search", "find", "look for", "grep"],
        "get_file_info": ["info", "details", "metadata", "properties"],
    }

    # Common patterns that reduce novelty
    COMMON_PATTERNS = [
        "help me",
        "please",
        "the files",
        "organize",
        "can you",
        "i want",
        "i need",
    ]

    def __init__(
        self,
        embedding_provider=None,
        existing_embeddings: List[List[float]] = None,
        novelty_weight: float = 0.6,
        coverage_weight: float = 0.4,
    ):
        """Initialize the novelty selector.

        Args:
            embedding_provider: Optional embedding provider for semantic novelty
            existing_embeddings: List of existing problem embeddings
            novelty_weight: Weight for novelty in final score (vs coverage)
            coverage_weight: Weight for coverage in final score (vs novelty)
        """
        self.embedding_provider = embedding_provider
        self.existing_embeddings = existing_embeddings or []
        self.novelty_weight = novelty_weight
        self.coverage_weight = coverage_weight

    def select_best(
        self, candidates: List[CandidateTask], tools_used: List[str]
    ) -> Tuple[CandidateTask, str]:
        """Select the best candidate based on novelty and coverage.

        Args:
            candidates: List of candidate tasks
            tools_used: Tools used in the trajectory

        Returns:
            (selected_candidate, selection_reason)
        """
        if not candidates:
            raise ValueError("No candidates to select from")

        if len(candidates) == 1:
            return candidates[0], "Only one candidate"

        # Compute scores for each candidate
        for candidate in candidates:
            # Novelty score (1 - max similarity to existing)
            if self.embedding_provider and self.existing_embeddings:
                candidate.novelty_score = self._compute_novelty(candidate.problem)
            else:
                # Without embeddings, use hash-based pseudo-novelty
                candidate.novelty_score = self._compute_hash_novelty(candidate.problem)

            # Coverage score (how many tools mentioned)
            candidate.coverage_score = self._compute_coverage(
                candidate.problem, tools_used
            )

            # Final score
            candidate.compute_final_score(novelty_weight=self.novelty_weight, coverage_weight=self.coverage_weight)

        # Select highest scoring
        best = max(candidates, key=lambda c: c.final_score)

        reason = (
            f"novelty={best.novelty_score:.2f}, "
            f"coverage={best.coverage_score:.2f}, "
            f"final={best.final_score:.2f}"
        )
        return best, reason

    def _compute_novelty(self, problem: str) -> float:
        """Compute novelty using embedding similarity.

        Args:
            problem: The problem text

        Returns:
            Novelty score (1 - max similarity to existing)
        """
        if not self.embedding_provider:
            return 0.5

        try:
            embedding = self.embedding_provider.get_embedding(problem)

            if not self.existing_embeddings:
                return 1.0  # First problem is maximally novel

            # Compute max similarity to existing
            max_sim = 0.0
            for existing in self.existing_embeddings:
                sim = self._cosine_similarity(embedding, existing)
                max_sim = max(max_sim, sim)

            # Novelty = 1 - similarity
            return 1.0 - max_sim

        except Exception as e:
            logger.warning(f"Novelty computation failed: {e}")
            return 0.5

    def _compute_hash_novelty(self, problem: str) -> float:
        """Pseudo-novelty based on text characteristics.

        Uses heuristics when embedding provider is not available.

        Args:
            problem: The problem text

        Returns:
            Pseudo-novelty score
        """
        normalized = " ".join(problem.lower().split())

        # Penalize common patterns
        penalty = sum(1 for p in self.COMMON_PATTERNS if p in normalized) * 0.1

        # Bonus for length and specificity
        length_bonus = min(0.1, len(problem) / 500)

        return max(0.0, min(1.0, 0.7 - penalty + length_bonus))

    def _compute_coverage(self, problem: str, tools_used: List[str]) -> float:
        """Compute how well the problem describes the tools used.

        Args:
            problem: The problem text
            tools_used: List of tools used

        Returns:
            Coverage score (0-1)
        """
        problem_lower = problem.lower()

        covered = 0
        for tool in tools_used:
            keywords = self.TOOL_KEYWORDS.get(tool, [tool.replace("_", " ")])
            if any(kw in problem_lower for kw in keywords):
                covered += 1

        return covered / max(1, len(tools_used))

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors.

        Args:
            a: First vector
            b: Second vector

        Returns:
            Cosine similarity (-1 to 1)
        """
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot / (norm_a * norm_b)

    def add_to_existing(self, problem: str):
        """Add a selected problem to existing embeddings for future novelty computation.

        Args:
            problem: The selected problem text
        """
        if self.embedding_provider:
            try:
                embedding = self.embedding_provider.get_embedding(problem)
                self.existing_embeddings.append(embedding)
            except Exception:
                pass


class SelfQuestioningPipeline:
    """Complete self-questioning pipeline combining generation and selection."""

    def __init__(self, generator: CandidateGenerator, selector: NoveltySelector):
        """Initialize the pipeline.

        Args:
            generator: CandidateGenerator for creating candidates
            selector: NoveltySelector for choosing the best
        """
        self.generator = generator
        self.selector = selector

    async def process(
        self, intent_spec, tools_used: List[str], sample_changes: List[Dict[str, Any]]
    ) -> SelfQuestioningResult:
        """Run the complete self-questioning process.

        Args:
            intent_spec: Intent specification from trajectory
            tools_used: Tools used in trajectory
            sample_changes: Sample file changes

        Returns:
            SelfQuestioningResult with candidates and selected task
        """
        # Generate candidates
        candidates = await self.generator.generate_candidates(
            intent_spec=intent_spec,
            tools_used=tools_used,
            sample_changes=sample_changes,
        )

        # Select best
        selected, reason = self.selector.select_best(candidates, tools_used)

        # Add to existing for future novelty computation
        self.selector.add_to_existing(selected.problem)

        return SelfQuestioningResult(
            candidates=candidates,
            selected=selected,
            selection_reason=reason,
            existing_problems_checked=len(self.selector.existing_embeddings),
        )
