"""Problem candidate selector for Self-Questioning task abstraction.

Selects the best problem candidate based on:
- Novelty: How different is it from existing problems?
- Coverage: Does it include underrepresented tools/patterns?
- Executability: Is it clear, unambiguous, and achievable?

Reference: AgentEvolver's TaskManager selection criteria.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Set, Tuple

from .problem_candidate_generator import ProblemCandidate
from .dedup import SemanticDeduplicator, TrajectorySignature

logger = logging.getLogger(__name__)


@dataclass
class SelectionScore:
    """Detailed scoring breakdown for a candidate."""
    novelty_score: float = 0.0       # 0-1, higher = more novel
    coverage_score: float = 0.0      # 0-1, higher = better coverage
    executability_score: float = 0.0 # 0-1, higher = more executable
    
    # Component scores
    length_score: float = 0.0        # Penalize too short or too long
    specificity_score: float = 0.0   # Medium specificity preferred
    clarity_score: float = 0.0       # Clear language indicators
    
    # Final weighted score
    total_score: float = 0.0
    
    # Explanation
    explanation: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "novelty_score": self.novelty_score,
            "coverage_score": self.coverage_score,
            "executability_score": self.executability_score,
            "length_score": self.length_score,
            "specificity_score": self.specificity_score,
            "clarity_score": self.clarity_score,
            "total_score": self.total_score,
            "explanation": self.explanation
        }


@dataclass
class SelectionResult:
    """Result of candidate selection."""
    selected: ProblemCandidate
    selected_index: int
    score: SelectionScore
    all_scores: List[SelectionScore]
    candidates_count: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "selected_problem": self.selected.problem_text,
            "selected_index": self.selected_index,
            "score": self.score.to_dict(),
            "candidates_count": self.candidates_count
        }


class ProblemCandidateSelector:
    """Selects the best problem candidate from multiple options.
    
    Selection criteria:
    1. Novelty (40%): Different from existing problems in the dataset
    2. Coverage (30%): Includes underused tools/patterns
    3. Executability (30%): Clear, achievable, well-formed
    """
    
    # Weights for combining scores
    NOVELTY_WEIGHT = 0.4
    COVERAGE_WEIGHT = 0.3
    EXECUTABILITY_WEIGHT = 0.3
    
    # Ideal problem length range (words)
    MIN_WORDS = 10
    MAX_WORDS = 100
    IDEAL_MIN_WORDS = 20
    IDEAL_MAX_WORDS = 60
    
    # Clarity indicators (positive)
    CLARITY_POSITIVE = [
        r'\bcreate\b', r'\bmove\b', r'\bdelete\b', r'\brename\b',
        r'\bedit\b', r'\bwrite\b', r'\bread\b', r'\bfind\b',
        r'\borganize\b', r'\blist\b', r'\bsearch\b',
        r'\binto\b', r'\bfrom\b', r'\bto\b',
        r'\bnamed\b', r'\bcalled\b'
    ]
    
    # Clarity indicators (negative - vague)
    CLARITY_NEGATIVE = [
        r'\bsomething\b', r'\bsomehow\b', r'\bmaybe\b',
        r'\bperhaps\b', r'\bkind of\b', r'\bsort of\b',
        r'\betc\b', r'\band so on\b'
    ]
    
    def __init__(
        self,
        deduplicator: Optional[SemanticDeduplicator] = None,
        tool_coverage: Optional[Dict[str, int]] = None,
        novelty_weight: float = 0.4,
        coverage_weight: float = 0.3,
        executability_weight: float = 0.3
    ):
        """Initialize selector.
        
        Args:
            deduplicator: Optional semantic deduplicator for novelty scoring
            tool_coverage: Optional dict of tool -> usage count for coverage scoring
            novelty_weight: Weight for novelty score
            coverage_weight: Weight for coverage score
            executability_weight: Weight for executability score
        """
        self.deduplicator = deduplicator
        self.tool_coverage = tool_coverage or {}
        
        self.novelty_weight = novelty_weight
        self.coverage_weight = coverage_weight
        self.executability_weight = executability_weight
        
        # Cache of seen problem hashes for novelty
        self._seen_problems: Set[str] = set()
    
    def select_best(
        self,
        candidates: List[ProblemCandidate],
        trajectory: Dict[str, Any],
        tools_used: Optional[List[str]] = None,
        anchors: Optional[List[str]] = None
    ) -> SelectionResult:
        """Select the best candidate from the list.
        
        Args:
            candidates: List of problem candidates
            trajectory: The trajectory data
            tools_used: Tools used in this trajectory
            anchors: Anchor tools that should ideally be mentioned
            
        Returns:
            SelectionResult with selected candidate and scores
        """
        if not candidates:
            raise ValueError("No candidates to select from")
        
        if len(candidates) == 1:
            score = self._score_candidate(candidates[0], tools_used, anchors)
            return SelectionResult(
                selected=candidates[0],
                selected_index=0,
                score=score,
                all_scores=[score],
                candidates_count=1
            )
        
        # Score all candidates
        all_scores = []
        for candidate in candidates:
            score = self._score_candidate(candidate, tools_used, anchors)
            all_scores.append(score)
        
        # Select the one with highest total score
        best_index = max(range(len(candidates)), key=lambda i: all_scores[i].total_score)
        
        logger.info(
            f"Selected candidate {best_index + 1}/{len(candidates)} "
            f"(score={all_scores[best_index].total_score:.3f})"
        )
        
        return SelectionResult(
            selected=candidates[best_index],
            selected_index=best_index,
            score=all_scores[best_index],
            all_scores=all_scores,
            candidates_count=len(candidates)
        )
    
    def _score_candidate(
        self,
        candidate: ProblemCandidate,
        tools_used: Optional[List[str]] = None,
        anchors: Optional[List[str]] = None
    ) -> SelectionScore:
        """Score a single candidate."""
        score = SelectionScore()
        
        # Calculate component scores
        score.novelty_score = self._score_novelty(candidate)
        score.coverage_score = self._score_coverage(candidate, tools_used, anchors)
        score.executability_score = self._score_executability(candidate)
        
        # Calculate total weighted score
        score.total_score = (
            self.novelty_weight * score.novelty_score +
            self.coverage_weight * score.coverage_score +
            self.executability_weight * score.executability_score
        )
        
        # Build explanation
        explanations = []
        if score.novelty_score >= 0.8:
            explanations.append("highly novel")
        elif score.novelty_score <= 0.3:
            explanations.append("similar to existing")
        
        if score.coverage_score >= 0.8:
            explanations.append("good tool coverage")
        elif score.coverage_score <= 0.3:
            explanations.append("missing key tools")
        
        if score.executability_score >= 0.8:
            explanations.append("clear and executable")
        elif score.executability_score <= 0.3:
            explanations.append("vague or unclear")
        
        score.explanation = ", ".join(explanations) if explanations else "average quality"
        
        return score
    
    def _score_novelty(self, candidate: ProblemCandidate) -> float:
        """Score how novel/different this candidate is."""
        problem_text = candidate.problem_text.lower().strip()
        
        # Simple hash-based check for exact duplicates
        import hashlib
        problem_hash = hashlib.md5(problem_text.encode()).hexdigest()[:16]
        
        if problem_hash in self._seen_problems:
            return 0.0
        
        # Check similarity with deduplicator if available
        if self.deduplicator:
            # Use trajectory signature for comparison
            traj_sig = TrajectorySignature(tool_sequence=[], success_pattern=[])
            decision = self.deduplicator.should_keep(
                problem_text=candidate.problem_text,
                trajectory={"tool_calls": []},  # Dummy for novelty check
                sample_path=None
            )
            
            if not decision.should_keep:
                if decision.similarity_score:
                    # Return inverse of similarity
                    return max(0.0, 1.0 - decision.similarity_score)
                return 0.2  # Some novelty but flagged
        
        # Check word-level similarity with recent problems
        if self._seen_problems:
            candidate_words = set(problem_text.split())
            max_overlap = 0.0
            
            # Compare with recent (sample of seen problems)
            import random
            sample_size = min(50, len(self._seen_problems))
            sample_hashes = random.sample(list(self._seen_problems), sample_size) if len(self._seen_problems) > sample_size else list(self._seen_problems)
            
            # This is a simplified check - in practice would need to store more than hashes
            # For now, give high novelty to new problems
            return 0.8
        
        return 1.0  # Completely novel
    
    def _score_coverage(
        self,
        candidate: ProblemCandidate,
        tools_used: Optional[List[str]],
        anchors: Optional[List[str]]
    ) -> float:
        """Score how well this candidate covers important tools."""
        if not tools_used:
            return 0.5  # Neutral if no tool info
        
        problem_text = candidate.problem_text.lower()
        score = 0.5  # Base score
        
        # Check if problem mentions or implies tools used
        tool_mentions = 0
        for tool in tools_used:
            # Check for tool name or related action words
            tool_lower = tool.lower()
            action_keywords = self._tool_to_keywords(tool_lower)
            
            if any(kw in problem_text for kw in action_keywords):
                tool_mentions += 1
        
        if tools_used:
            mention_ratio = tool_mentions / len(tools_used)
            score += 0.3 * mention_ratio
        
        # Bonus for mentioning anchor tools (underused tools)
        if anchors:
            anchor_mentions = 0
            for anchor in anchors:
                anchor_keywords = self._tool_to_keywords(anchor.lower())
                if any(kw in problem_text for kw in anchor_keywords):
                    anchor_mentions += 1
            
            anchor_ratio = anchor_mentions / len(anchors)
            score += 0.2 * anchor_ratio
        
        # Bonus for mentioning underused tools from coverage tracker
        if self.tool_coverage:
            # Find underused tools (below median)
            counts = list(self.tool_coverage.values())
            if counts:
                median = sorted(counts)[len(counts) // 2]
                underused = [t for t, c in self.tool_coverage.items() if c < median]
                
                underused_mentioned = 0
                for tool in underused:
                    tool_keywords = self._tool_to_keywords(tool.lower())
                    if any(kw in problem_text for kw in tool_keywords):
                        underused_mentioned += 1
                
                if underused:
                    underused_ratio = underused_mentioned / len(underused)
                    score += 0.1 * underused_ratio
        
        return min(1.0, score)
    
    def _tool_to_keywords(self, tool_name: str) -> List[str]:
        """Convert tool name to related keywords for matching."""
        keywords = [tool_name]
        
        # Common tool name patterns
        mapping = {
            "create_directory": ["create", "directory", "folder", "mkdir"],
            "write_file": ["write", "create", "file", "save"],
            "read_file": ["read", "open", "view", "content"],
            "edit_file": ["edit", "modify", "change", "update"],
            "move_file": ["move", "relocate", "transfer"],
            "delete_file": ["delete", "remove", "erase"],
            "rename": ["rename", "name"],
            "copy": ["copy", "duplicate"],
            "list_directory": ["list", "show", "display", "contents"],
            "search_files": ["search", "find", "locate"],
            "directory_tree": ["tree", "structure", "hierarchy"],
            "get_file_info": ["info", "information", "details", "properties"]
        }
        
        for pattern, kws in mapping.items():
            if pattern in tool_name or tool_name in pattern:
                keywords.extend(kws)
        
        # Also split tool name by underscores
        parts = tool_name.split("_")
        keywords.extend(parts)
        
        return list(set(keywords))
    
    def _score_executability(self, candidate: ProblemCandidate) -> float:
        """Score how clear and executable the problem is."""
        problem_text = candidate.problem_text
        score = 0.5  # Base score
        
        # Length scoring
        words = problem_text.split()
        word_count = len(words)
        
        if word_count < self.MIN_WORDS:
            score -= 0.3  # Too short
        elif word_count > self.MAX_WORDS:
            score -= 0.2  # Too long
        elif self.IDEAL_MIN_WORDS <= word_count <= self.IDEAL_MAX_WORDS:
            score += 0.2  # Ideal length
        
        # Clarity indicators
        text_lower = problem_text.lower()
        
        # Positive indicators
        positive_count = sum(
            1 for pattern in self.CLARITY_POSITIVE 
            if re.search(pattern, text_lower)
        )
        score += 0.05 * min(positive_count, 5)  # Cap bonus
        
        # Negative indicators
        negative_count = sum(
            1 for pattern in self.CLARITY_NEGATIVE
            if re.search(pattern, text_lower)
        )
        score -= 0.1 * negative_count
        
        # Specificity preference (medium is best)
        if candidate.specificity == "medium":
            score += 0.1
        elif candidate.specificity == "low":
            score -= 0.05  # Too abstract
        # "high" is fine, no adjustment
        
        # Check for concrete nouns/paths
        has_path = "/" in problem_text or "\\" in problem_text
        has_extension = re.search(r'\.\w{2,4}\b', problem_text) is not None
        
        if has_path or has_extension:
            score += 0.1  # Concrete references
        
        # Sentence structure (should have subject + verb)
        if problem_text and problem_text[0].isupper():
            score += 0.05  # Proper sentence start
        
        return max(0.0, min(1.0, score))
    
    def register_selected(self, candidate: ProblemCandidate):
        """Register a selected candidate to track novelty."""
        problem_text = candidate.problem_text.lower().strip()
        import hashlib
        problem_hash = hashlib.md5(problem_text.encode()).hexdigest()[:16]
        self._seen_problems.add(problem_hash)
