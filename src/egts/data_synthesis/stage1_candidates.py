"""Stage-1 problem candidate scoring for execution-anchored synthesis."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, List, Sequence


@dataclass
class CandidateScore:
    novelty_score: float
    coverage_score: float
    total_score: float
    explanation: str

    def to_dict(self) -> dict:
        return {
            "novelty_score": self.novelty_score,
            "coverage_score": self.coverage_score,
            "total_score": self.total_score,
            "explanation": self.explanation,
        }


@dataclass
class CandidateSelection:
    selected_problem: str
    selected_index: int
    selected_score: CandidateScore
    all_scores: List[CandidateScore]
    candidates: List[str]

    def to_dict(self) -> dict:
        return {
            "selected_problem": self.selected_problem,
            "selected_index": self.selected_index,
            "selected_score": self.selected_score.to_dict(),
            "all_scores": [score.to_dict() for score in self.all_scores],
            "candidates_count": len(self.candidates),
        }


_TOOL_KEYWORDS = {
    "create_directory": ["create", "directory", "folder", "mkdir"],
    "write_file": ["write", "create", "file", "save"],
    "read_file": ["read", "open", "view", "content"],
    "read_text_file": ["read", "open", "view", "content"],
    "edit_file": ["edit", "modify", "change", "update"],
    "move_file": ["move", "relocate", "archive", "transfer"],
    "delete_file": ["delete", "remove", "erase"],
    "rename_file": ["rename", "name"],
    "copy_file": ["copy", "duplicate"],
    "list_directory": ["list", "show", "display", "contents", "look"],
    "search_files": ["search", "find", "locate"],
    "directory_tree": ["tree", "structure", "hierarchy"],
    "get_file_info": ["info", "information", "details", "properties"],
}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9_]+", (text or "").lower()))


def _tool_keywords(tool_name: str) -> set[str]:
    lowered = tool_name.lower()
    keywords = set(_TOOL_KEYWORDS.get(lowered, []))
    keywords.add(lowered)
    keywords.update(part for part in lowered.split("_") if part)
    return keywords


def _novelty(problem: str, existing_problem_texts: Sequence[str]) -> float:
    candidate_tokens = _tokens(problem)
    if not existing_problem_texts or not candidate_tokens:
        return 1.0

    max_similarity = 0.0
    for existing in existing_problem_texts:
        existing_tokens = _tokens(existing)
        if not existing_tokens:
            continue
        similarity = len(candidate_tokens & existing_tokens) / len(
            candidate_tokens | existing_tokens
        )
        max_similarity = max(max_similarity, similarity)

    return round(max(0.0, 1.0 - max_similarity), 4)


def _coverage(problem: str, tools_used: Sequence[str], anchor_tools: Sequence[str]) -> float:
    problem_tokens = _tokens(problem)
    if not tools_used and not anchor_tools:
        return 0.5

    tool_matches = 0
    unique_tools = list(dict.fromkeys(tools_used))
    for tool_name in unique_tools:
        if problem_tokens & _tool_keywords(tool_name):
            tool_matches += 1

    base_score = tool_matches / len(unique_tools) if unique_tools else 0.0

    anchor_matches = 0
    unique_anchors = list(dict.fromkeys(anchor_tools))
    for tool_name in unique_anchors:
        if problem_tokens & _tool_keywords(tool_name):
            anchor_matches += 1
    anchor_score = anchor_matches / len(unique_anchors) if unique_anchors else base_score

    if unique_anchors:
        return round(0.6 * base_score + 0.4 * anchor_score, 4)
    return round(base_score, 4)


def select_problem_candidate(
    *,
    candidates: Sequence[str],
    tools_used: Sequence[str],
    anchor_tools: Sequence[str] = (),
    existing_problem_texts: Sequence[str] = (),
    novelty_weight: float = 0.6,
    coverage_weight: float = 0.4,
) -> CandidateSelection:
    """Select the best Stage-1 problem candidate by novelty and coverage."""
    cleaned = [candidate.strip() for candidate in candidates if candidate and candidate.strip()]
    if not cleaned:
        raise ValueError("No problem candidates to select from")

    total_weight = max(1e-9, novelty_weight + coverage_weight)
    novelty_w = novelty_weight / total_weight
    coverage_w = coverage_weight / total_weight

    scores: list[CandidateScore] = []
    for candidate in cleaned:
        novelty_score = _novelty(candidate, existing_problem_texts)
        coverage_score = _coverage(candidate, tools_used, anchor_tools)
        total = round(novelty_w * novelty_score + coverage_w * coverage_score, 4)
        explanation = (
            f"novelty={novelty_score:.2f}, coverage={coverage_score:.2f}, "
            f"weights=({novelty_w:.2f},{coverage_w:.2f})"
        )
        scores.append(
            CandidateScore(
                novelty_score=novelty_score,
                coverage_score=coverage_score,
                total_score=total,
                explanation=explanation,
            )
        )

    selected_index = max(range(len(cleaned)), key=lambda idx: scores[idx].total_score)
    return CandidateSelection(
        selected_problem=cleaned[selected_index],
        selected_index=selected_index,
        selected_score=scores[selected_index],
        all_scores=scores,
        candidates=cleaned,
    )


def extract_problem_candidates(problem_data: dict, raw_context: dict | None = None) -> list[str]:
    """Extract candidate problem strings from common raw/synthesized structures."""
    candidates: list[str] = []
    for source in (problem_data, raw_context or {}):
        raw = source.get("problem_candidates") or source.get("candidates")
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, str):
                    candidates.append(item)
                elif isinstance(item, dict):
                    text = item.get("problem") or item.get("problem_text") or item.get("task")
                    if text:
                        candidates.append(str(text))
    if not candidates and problem_data.get("problem"):
        candidates.append(str(problem_data["problem"]))
    # Include the model's stated exploration objective as a candidate when
    # available — it is a task-grounded starting point for problem synthesis.
    objective = (problem_data.get("collection_task_objective", "") or "").strip()
    if objective and objective not in candidates:
        candidates.append(objective)
    return list(dict.fromkeys(candidate.strip() for candidate in candidates if candidate and candidate.strip()))
