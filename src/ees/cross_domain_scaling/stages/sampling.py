from __future__ import annotations

import itertools
import random
from collections import Counter
from typing import Any


def sample_domain_groups(
    graph: dict[str, Any],
    *,
    count: int,
    minimum_size: int,
    maximum_size: int,
    seed: int,
) -> list[list[str]]:
    adjacency = graph.get("adjacency", {})
    nodes = sorted(adjacency)
    if count < 1:
        raise ValueError("count must be positive")
    if not 2 <= minimum_size <= maximum_size <= len(nodes):
        raise ValueError("domain group sizes must satisfy 2 <= min <= max <= catalog size")

    rng = random.Random(seed)
    coverage: Counter[str] = Counter()
    unique: set[tuple[str, ...]] = set()
    groups: list[list[str]] = []

    attempts = max(500, count * 100)
    for _ in range(attempts):
        if len(groups) >= count:
            break
        target_size = rng.randint(minimum_size, maximum_size)
        minimum_coverage = min(coverage[node] for node in nodes)
        starts = [node for node in nodes if coverage[node] == minimum_coverage]
        selected = {rng.choice(starts)}

        while len(selected) < target_size:
            choices: dict[str, float] = {}
            for current in selected:
                for neighbor in adjacency[current]:
                    candidate = neighbor["id"]
                    if candidate in selected:
                        continue
                    balance = 1 / (1 + coverage[candidate])
                    choices[candidate] = choices.get(candidate, 0.0) + neighbor["score"] * balance
            if not choices:
                break
            population = sorted(choices)
            weights = [max(choices[item], 0.000001) for item in population]
            selected.add(rng.choices(population, weights=weights, k=1)[0])

        key = tuple(sorted(selected))
        if len(key) < minimum_size or key in unique:
            continue
        unique.add(key)
        groups.append(list(key))
        coverage.update(key)

    # A deterministic exhaustive fallback fills combinations missed by the random walks.
    fallback: list[tuple[str, ...]] = []
    for size in range(minimum_size, maximum_size + 1):
        for candidate in itertools.combinations(nodes, size):
            if candidate not in unique and _connected(candidate, adjacency):
                fallback.append(candidate)
    rng.shuffle(fallback)
    for candidate in fallback:
        if len(groups) >= count:
            break
        groups.append(list(candidate))

    return groups


def _connected(group: tuple[str, ...], adjacency: dict[str, list[dict[str, Any]]]) -> bool:
    allowed = set(group)
    seen = {group[0]}
    frontier = [group[0]]
    while frontier:
        current = frontier.pop()
        for neighbor in adjacency[current]:
            candidate = neighbor["id"]
            if candidate in allowed and candidate not in seen:
                seen.add(candidate)
                frontier.append(candidate)
    return seen == allowed

