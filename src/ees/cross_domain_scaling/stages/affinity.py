from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from itertools import combinations
from typing import Any

from ..llm import EmbeddingProvider, JsonGenerator
from ..models import Catalog, DomainSpec

_TOKEN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]", flags=re.IGNORECASE)
_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "in",
    "of",
    "or",
    "the",
    "to",
    "with",
    "system",
    "service",
}


def build_affinity_graph(
    catalog: Catalog,
    *,
    neighbors_per_domain: int = 6,
    minimum_score: float = 0.03,
    mode: str = "contract",
    embedder: EmbeddingProvider | None = None,
    rubric: JsonGenerator | None = None,
) -> dict[str, Any]:
    if neighbors_per_domain < 1:
        raise ValueError("neighbors_per_domain must be positive")
    if not 0 <= minimum_score <= 1:
        raise ValueError("minimum_score must be between 0 and 1")
    if mode not in {"contract", "semantic"}:
        raise ValueError("affinity mode must be 'contract' or 'semantic'")
    if mode == "semantic" and (embedder is None or rubric is None):
        raise ValueError("semantic affinity mode requires embedding and rubric providers")

    if mode == "semantic":
        assert embedder is not None and rubric is not None
        candidates = _semantic_affinities(
            catalog,
            neighbors_per_domain=neighbors_per_domain,
            embedder=embedder,
            rubric=rubric,
        )
    else:
        candidates = [
            _pair_affinity(left, right) for left, right in combinations(catalog.domains, 2)
        ]
    ranked: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in candidates:
        ranked[edge["left"]].append(edge)
        ranked[edge["right"]].append(edge)
    preferred: set[tuple[str, str]] = set()
    for edges in ranked.values():
        edges.sort(key=lambda item: (-item["score"], item["left"], item["right"]))
        for edge in edges[:neighbors_per_domain]:
            preferred.add((edge["left"], edge["right"]))

    kept = [
        edge
        for edge in candidates
        if (edge["left"], edge["right"]) in preferred and edge["score"] >= minimum_score
    ]
    kept.sort(key=lambda item: (item["left"], item["right"]))

    adjacency: dict[str, list[dict[str, Any]]] = {domain.id: [] for domain in catalog.domains}
    for edge in kept:
        adjacency[edge["left"]].append({"id": edge["right"], "score": edge["score"]})
        adjacency[edge["right"]].append({"id": edge["left"], "score": edge["score"]})
    for values in adjacency.values():
        values.sort(key=lambda item: (-item["score"], item["id"]))

    return {
        "nodes": [
            {"id": domain.id, "name": domain.name, "summary": domain.summary}
            for domain in catalog.domains
        ],
        "edges": kept,
        "adjacency": adjacency,
        "settings": {
            "neighbors_per_domain": neighbors_per_domain,
            "minimum_score": minimum_score,
            "mode": mode,
        },
    }


def _pair_affinity(left: DomainSpec, right: DomainSpec) -> dict[str, Any]:
    left_words = _domain_words(left)
    right_words = _domain_words(right)
    lexical = _jaccard(left_words, right_words)
    entity = _jaccard(
        _tokens(item.name for item in left.entities),
        _tokens(item.name for item in right.entities),
    )
    capability = _jaccard(_tokens(left.capabilities), _tokens(right.capabilities))

    # Entity continuity receives extra weight because it often creates executable workflows;
    # capability overlap provides a weaker signal and avoids rewarding near-duplicate domains.
    score = 0.5 * lexical + 0.35 * entity + 0.15 * math.sqrt(capability)
    return {
        "left": left.id,
        "right": right.id,
        "score": round(score, 6),
        "signals": {
            "lexical": round(lexical, 6),
            "entity": round(entity, 6),
            "capability": round(capability, 6),
        },
        "rubric": "contract",
    }


def _semantic_affinities(
    catalog: Catalog,
    *,
    neighbors_per_domain: int,
    embedder: EmbeddingProvider,
    rubric: JsonGenerator,
) -> list[dict[str, Any]]:
    descriptors = [_descriptor(domain) for domain in catalog.domains]
    vectors = embedder.embed(descriptors)
    if len(vectors) != len(catalog.domains):
        raise ValueError("embedding provider returned an unexpected number of vectors")
    by_id = catalog.by_id()
    similarities: list[tuple[str, str, float]] = []
    for left_index, right_index in combinations(range(len(catalog.domains)), 2):
        left = catalog.domains[left_index].id
        right = catalog.domains[right_index].id
        similarities.append((left, right, _cosine(vectors[left_index], vectors[right_index])))

    ranked: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
    for item in similarities:
        ranked[item[0]].append(item)
        ranked[item[1]].append(item)
    candidate_pairs: dict[tuple[str, str], float] = {}
    for edges in ranked.values():
        edges.sort(key=lambda item: (-item[2], item[0], item[1]))
        for left, right, similarity in edges[:neighbors_per_domain]:
            candidate_pairs[(left, right)] = similarity

    results: list[dict[str, Any]] = []
    for (left_id, right_id), similarity in sorted(candidate_pairs.items()):
        results.append(
            _rubric_affinity(by_id[left_id], by_id[right_id], similarity, rubric)
        )
    return results


def _descriptor(domain: DomainSpec) -> str:
    parts = [domain.name, domain.summary]
    parts.extend(
        f"entity:{entity.name} fields:{','.join(entity.fields)}"
        for entity in domain.entities
    )
    parts.extend(f"capability:{item}" for item in domain.capabilities)
    parts.extend(f"operation:{item.name} {item.description}" for item in domain.operations)
    return "\n".join(parts)


def _rubric_affinity(
    left: DomainSpec,
    right: DomainSpec,
    similarity: float,
    rubric: JsonGenerator,
) -> dict[str, Any]:
    payload = {
        "left": _rubric_contract(left),
        "right": _rubric_contract(right),
        "embedding_similarity": round(similarity, 6),
        "rubric": {
            "1": "unrelated systems with no credible shared workflow",
            "2": "weak thematic relation but no operational dependency",
            "3": "credible workflow with a usable entity, state, or policy relation",
            "4": "strong functional complementarity and explicit linking fields",
            "5": "highly coordinated systems with multiple executable dependencies",
        },
        "required_output": {
            "score": "integer 1-5",
            "reason": "string",
            "candidate_links": [
                {
                    "left_entity": "string",
                    "left_field": "string",
                    "right_entity": "string",
                    "right_field": "string",
                }
            ],
        },
    }
    judged = rubric.generate(
        system=(
            "Evaluate whether two executable domain contracts can form a coordinated cross-domain "
            "workflow. Only reference declared entities, fields, operations, and policies. Return "
            "one JSON object."
        ),
        prompt=json.dumps(payload, ensure_ascii=False),
    )
    raw_score = judged.get("score")
    if not isinstance(raw_score, int) or not 1 <= raw_score <= 5:
        raise ValueError("affinity rubric must return an integer score from 1 to 5")
    return {
        "left": left.id,
        "right": right.id,
        "score": round(raw_score / 5, 6),
        "rubric_score": raw_score,
        "embedding_similarity": round(similarity, 6),
        "reason": str(judged.get("reason", "")),
        "candidate_links": judged.get("candidate_links", []),
        "rubric": "model",
    }


def _rubric_contract(domain: DomainSpec) -> dict[str, Any]:
    return {
        "id": domain.id,
        "name": domain.name,
        "summary": domain.summary,
        "entities": [entity.to_dict() for entity in domain.entities],
        "capabilities": list(domain.capabilities),
        "policies": list(domain.policies),
        "operations": [
            {"name": operation.name, "description": operation.description}
            for operation in domain.operations
        ],
    }


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("embedding vectors must have the same non-zero dimension")
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _domain_words(domain: DomainSpec) -> set[str]:
    entity_terms = [entity.name for entity in domain.entities]
    entity_terms.extend(field for entity in domain.entities for field in entity.fields)
    content = [domain.name, domain.summary, *entity_terms, *domain.capabilities]
    content.extend(operation.description for operation in domain.operations)
    return _tokens(content)


def _tokens(values: Any) -> set[str]:
    if isinstance(values, str):
        values = [values]
    result: set[str] = set()
    for value in values:
        for token in _TOKEN.findall(value.lower()):
            if token not in _STOPWORDS and len(token) > 1:
                result.add(token)
    return result


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0



