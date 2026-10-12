"""Problem candidate generator for Self-Questioning task abstraction.

Generates multiple candidate problem formulations from a single trajectory/evidence,
enabling selection of the best problem based on novelty, coverage, and executability.

Reference: AgentEvolver's TaskManager explore→summarize approach.
"""

import logging
import json
import random
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set, Tuple
from pathlib import Path

from .maas_client import MaaSClient
from .utils.config import MaaSConfig, ModelConfig
from .state.filesystem_snapshot import FilesystemDiff
from .trajs2data_collector import StrictTrajectory, ToolCallRecord
from .problem_synthesizer import IntentSpec, RetrievalSpec, TaskType

logger = logging.getLogger(__name__)


@dataclass
class ProblemCandidate:
    """A candidate problem formulation."""
    problem_text: str
    task_type: TaskType
    
    # Perspective/framing of the problem
    framing: str  # e.g., "direct_instruction", "scenario", "goal_oriented", "constraint_based"
    
    # Specificity level
    specificity: str  # "high" (exact paths), "medium" (patterns), "low" (abstract)
    
    # What aspects of the evidence does it emphasize?
    emphasis: List[str] = field(default_factory=list)  # ["file_types", "structure", "content", "tools"]
    
    # Reference answer for retrieval tasks
    reference_answer: Optional[str] = None
    
    # Raw generation metadata
    generation_prompt_variant: Optional[str] = None
    raw_response: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "problem_text": self.problem_text,
            "task_type": self.task_type.value,
            "framing": self.framing,
            "specificity": self.specificity,
            "emphasis": self.emphasis,
            "reference_answer": self.reference_answer
        }


class ProblemCandidateGenerator:
    """Generates multiple candidate problems from trajectory evidence.
    
    Uses different prompt variants to produce diverse problem formulations:
    - Direct instruction: "Create a file named X..."
    - Scenario-based: "You're organizing a project..."
    - Goal-oriented: "The goal is to..."
    - Constraint-based: "Without using X, achieve Y..."
    """
    
    # Different framing templates for diversity
    FRAMING_TEMPLATES = {
        "direct_instruction": """Based on the evidence, write a direct task instruction.
Format: A clear, imperative statement telling the user exactly what to do.
Example: "Create a new directory called 'reports' and move all .pdf files into it."
""",
        "scenario": """Based on the evidence, write a scenario-based task.
Format: Set up a context/scenario, then describe what needs to be done.
Example: "You're reorganizing your project files. Currently there are several documents scattered in the root directory. Group them by file type into appropriate folders."
""",
        "goal_oriented": """Based on the evidence, write a goal-oriented task description.
Format: Describe the desired end state or goal, letting the solver determine the steps.
Example: "Ensure all configuration files in the project follow a consistent naming convention using lowercase and underscores."
""",
        "abstract": """Based on the evidence, write an abstract task that captures the pattern without specific filenames.
Format: Describe the task in general terms that could apply to similar situations.
Example: "Organize files by their extension into separate subdirectories."
"""
    }
    
    SPECIFICITY_GUIDANCE = {
        "high": "Include exact file names, paths, and specific content when relevant.",
        "medium": "Use file patterns (like '*.txt') and relative descriptions rather than exact names.",
        "low": "Describe the task abstractly without mentioning specific files."
    }
    
    def __init__(
        self,
        maas_client: MaaSClient,
        maas_config: MaaSConfig,
        num_candidates: int = 3,
        language: str = "en"
    ):
        """Initialize generator.
        
        Args:
            maas_client: MaaS client for LLM generation
            maas_config: Model configuration
            num_candidates: Number of candidates to generate per trajectory
            language: Output language ("en" or "zh")
        """
        self.maas_client = maas_client
        self.maas_config = maas_config
        self.num_candidates = num_candidates
        self.language = language
        
        # Select framings to use based on num_candidates
        self._select_framings()
    
    def _select_framings(self):
        """Select which framings to use for generation."""
        all_framings = list(self.FRAMING_TEMPLATES.keys())
        
        if self.num_candidates >= len(all_framings):
            self.selected_framings = all_framings
        else:
            # Always include direct_instruction, sample the rest
            self.selected_framings = ["direct_instruction"]
            remaining = [f for f in all_framings if f != "direct_instruction"]
            self.selected_framings.extend(
                random.sample(remaining, min(self.num_candidates - 1, len(remaining)))
            )
    
    async def generate_candidates(
        self,
        evidence: Dict[str, Any],
        task_type: TaskType,
        intent_spec: Optional[IntentSpec] = None,
        retrieval_spec: Optional["RetrievalSpec"] = None,
        tools_used: Optional[List[str]] = None
    ) -> List[ProblemCandidate]:
        """Generate multiple problem candidates from evidence.
        
        Args:
            evidence: Dict containing diff, tool_calls, S0/S1 snapshots
            task_type: Whether this is a mutation or retrieval task
            intent_spec: Intent specification for mutation tasks
            retrieval_spec: Retrieval specification for Q&A tasks
            tools_used: List of tools used in the trajectory
            
        Returns:
            List of ProblemCandidate objects
        """
        candidates = []
        
        # Build evidence summary
        evidence_summary = self._build_evidence_summary(
            evidence, task_type, intent_spec, retrieval_spec
        )
        
        # Generate candidates with different framings
        for framing in self.selected_framings[:self.num_candidates]:
            try:
                candidate = await self._generate_single_candidate(
                    evidence_summary=evidence_summary,
                    task_type=task_type,
                    framing=framing,
                    tools_used=tools_used or [],
                    retrieval_spec=retrieval_spec
                )
                if candidate:
                    candidates.append(candidate)
            except Exception as e:
                logger.warning(f"Failed to generate candidate with framing '{framing}': {e}")
        
        # If we didn't get enough candidates, try with different specificity levels
        if len(candidates) < self.num_candidates:
            for specificity in ["high", "medium", "low"]:
                if len(candidates) >= self.num_candidates:
                    break
                
                try:
                    candidate = await self._generate_single_candidate(
                        evidence_summary=evidence_summary,
                        task_type=task_type,
                        framing="direct_instruction",
                        tools_used=tools_used or [],
                        retrieval_spec=retrieval_spec,
                        specificity=specificity
                    )
                    if candidate:
                        # Check it's not too similar to existing
                        if not self._is_too_similar(candidate, candidates):
                            candidates.append(candidate)
                except Exception as e:
                    logger.warning(f"Failed to generate candidate with specificity '{specificity}': {e}")
        
        logger.info(f"Generated {len(candidates)} problem candidates")
        return candidates
    
    def _build_evidence_summary(
        self,
        evidence: Dict[str, Any],
        task_type: TaskType,
        intent_spec: Optional[IntentSpec],
        retrieval_spec: Optional["RetrievalSpec"]
    ) -> str:
        """Build a summary of the evidence for the LLM prompt."""
        parts = []
        
        if task_type == TaskType.MUTATION and intent_spec:
            parts.append(f"Task Category: {intent_spec.task_category.value}")
            parts.append(f"Primary Action: {intent_spec.primary_action}")
            parts.append(f"Changes: {intent_spec.files_created} files created, "
                        f"{intent_spec.files_modified} modified, "
                        f"{intent_spec.files_deleted} deleted, "
                        f"{intent_spec.files_moved} moved")
            if intent_spec.directories_created:
                parts.append(f"Directories created: {intent_spec.directories_created}")
            if intent_spec.file_types_involved:
                parts.append(f"File types: {', '.join(intent_spec.file_types_involved)}")
            if intent_spec.naming_patterns:
                parts.append(f"Naming patterns: {', '.join(intent_spec.naming_patterns)}")
            if intent_spec.sample_changes:
                parts.append("Sample changes:")
                for change in intent_spec.sample_changes[:5]:
                    parts.append(f"  - {change}")
        
        elif task_type == TaskType.RETRIEVAL and retrieval_spec:
            parts.append(f"Query Type: {retrieval_spec.query_type}")
            parts.append(f"Query Focus: {retrieval_spec.query_focus}")
            parts.append(f"Tools Used: {', '.join(retrieval_spec.tools_used)}")
            if retrieval_spec.paths_queried:
                parts.append(f"Paths queried: {', '.join(retrieval_spec.paths_queried[:5])}")
            if retrieval_spec.key_results:
                parts.append("Key results (summary):")
                for result in retrieval_spec.key_results[:3]:
                    result_preview = str(result)[:200]
                    parts.append(f"  - {result_preview}")
        
        # Add tool call summary from evidence
        tool_calls = evidence.get("tool_calls", [])
        if tool_calls:
            tool_names = [tc.get("tool_name", tc.get("name", "unknown")) for tc in tool_calls[:10]]
            parts.append(f"Tool sequence: {' → '.join(tool_names)}")
        
        return "\n".join(parts)
    
    async def _generate_single_candidate(
        self,
        evidence_summary: str,
        task_type: TaskType,
        framing: str,
        tools_used: List[str],
        retrieval_spec: Optional["RetrievalSpec"] = None,
        specificity: str = "medium"
    ) -> Optional[ProblemCandidate]:
        """Generate a single problem candidate."""
        
        framing_instruction = self.FRAMING_TEMPLATES.get(
            framing, self.FRAMING_TEMPLATES["direct_instruction"]
        )
        specificity_guidance = self.SPECIFICITY_GUIDANCE.get(specificity, "")
        
        lang_instruction = (
            "Write the task in English." if self.language == "en" 
            else "用中文写这个任务。"
        )
        
        system_prompt = f"""You are a task description writer. Given evidence of actions performed on a filesystem, you write clear task descriptions that someone could follow to reproduce those actions.

{framing_instruction}

Specificity: {specificity_guidance}

{lang_instruction}

Output ONLY the task description, no explanations or meta-commentary."""

        user_prompt = f"""Evidence of performed actions:

{evidence_summary}

Write a task description that would lead to these actions being performed."""

        if task_type == TaskType.RETRIEVAL and retrieval_spec:
            user_prompt += f"""

This is an information retrieval/Q&A task. The question should ask for information that was retrieved.
The expected answer should be based on what was actually found.
Format your response as:
Question: [the question]
Expected Answer: [brief answer based on what was retrieved]"""

        try:
            # Use nl_rewrite model for generation
            response = await self.maas_client.generate_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                model_config=self.maas_config.models.nl_rewrite
            )
            
            content = response.get("content", "")
            if not content:
                return None
            
            # Parse response
            problem_text = content.strip()
            reference_answer = None
            
            if task_type == TaskType.RETRIEVAL:
                # Try to extract question and answer
                if "Expected Answer:" in content or "Answer:" in content:
                    parts = content.split("Expected Answer:" if "Expected Answer:" in content else "Answer:")
                    if len(parts) >= 2:
                        question_part = parts[0].replace("Question:", "").strip()
                        answer_part = parts[1].strip()
                        problem_text = question_part
                        reference_answer = answer_part
            
            # Determine emphasis based on content
            emphasis = []
            if any(ext in problem_text.lower() for ext in ['.txt', '.py', '.md', '.json']):
                emphasis.append("file_types")
            if any(word in problem_text.lower() for word in ['directory', 'folder', 'structure']):
                emphasis.append("structure")
            if any(word in problem_text.lower() for word in ['content', 'text', 'data']):
                emphasis.append("content")
            if any(tool in problem_text.lower() for tool in tools_used):
                emphasis.append("tools")
            
            return ProblemCandidate(
                problem_text=problem_text,
                task_type=task_type,
                framing=framing,
                specificity=specificity,
                emphasis=emphasis,
                reference_answer=reference_answer,
                generation_prompt_variant=f"{framing}_{specificity}",
                raw_response=content
            )
            
        except Exception as e:
            logger.error(f"Error generating candidate: {e}")
            return None
    
    def _is_too_similar(
        self, 
        candidate: ProblemCandidate, 
        existing: List[ProblemCandidate],
        threshold: float = 0.8
    ) -> bool:
        """Check if candidate is too similar to existing ones."""
        if not existing:
            return False
        
        candidate_words = set(candidate.problem_text.lower().split())
        
        for existing_candidate in existing:
            existing_words = set(existing_candidate.problem_text.lower().split())
            
            if not candidate_words or not existing_words:
                continue
            
            # Jaccard similarity
            intersection = len(candidate_words & existing_words)
            union = len(candidate_words | existing_words)
            similarity = intersection / union if union > 0 else 0
            
            if similarity >= threshold:
                return True
        
        return False
