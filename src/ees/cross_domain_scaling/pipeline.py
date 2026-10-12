from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .llm import EmbeddingProvider, JsonGenerator
from .models import Catalog
from .stages.affinity import build_affinity_graph
from .stages.composition import compose_manifests
from .stages.context import attach_contexts
from .stages.sampling import sample_domain_groups
from .stages.scenarios import attach_scenarios
from .stages.trajectory import collect_trajectories
from .stages.validation import validate_manifests
from .stages.verification import verify_trajectories


@dataclass(frozen=True, slots=True)
class BuildOptions:
    count: int = 25
    minimum_domains: int = 2
    maximum_domains: int = 4
    seed: int = 0
    neighbors_per_domain: int = 6
    affinity_threshold: float = 0.03
    affinity_mode: str = "contract"
    context_mode: str = "offline"
    judge_mode: str = "none"
    scenarios_per_environment: int = 0
    scenario_mode: str = "offline"
    rollout_mode: str = "none"
    max_steps: int = 12

    def validate(self, catalog_size: int) -> None:
        if self.count < 1:
            raise ValueError("count must be positive")
        if not 2 <= self.minimum_domains <= self.maximum_domains <= catalog_size:
            raise ValueError(
                "domain group sizes must satisfy 2 <= minimum <= maximum <= catalog size"
            )
        if self.neighbors_per_domain < 1:
            raise ValueError("neighbors_per_domain must be positive")
        if not 0 <= self.affinity_threshold <= 1:
            raise ValueError("affinity_threshold must be between 0 and 1")
        if self.affinity_mode not in {"contract", "semantic"}:
            raise ValueError("affinity_mode must be 'contract' or 'semantic'")
        if self.context_mode not in {"offline", "llm"}:
            raise ValueError("context_mode must be 'offline' or 'llm'")
        if self.judge_mode not in {"none", "llm"}:
            raise ValueError("judge_mode must be 'none' or 'llm'")
        if self.scenarios_per_environment < 0:
            raise ValueError("scenarios_per_environment cannot be negative")
        if self.scenario_mode not in {"offline", "llm"}:
            raise ValueError("scenario_mode must be 'offline' or 'llm'")
        if self.rollout_mode not in {"none", "reference", "llm"}:
            raise ValueError("rollout_mode must be 'none', 'reference', or 'llm'")
        if self.max_steps < 1:
            raise ValueError("max_steps must be positive")


def build_bundle(
    catalog: Catalog,
    options: BuildOptions | None = None,
    *,
    generator: JsonGenerator | None = None,
    embedder: EmbeddingProvider | None = None,
) -> dict[str, Any]:
    options = options or BuildOptions()
    options.validate(len(catalog.domains))
    needs_generator = (
        options.affinity_mode == "semantic"
        or options.context_mode == "llm"
        or options.judge_mode == "llm"
        or (options.scenarios_per_environment > 0 and options.scenario_mode == "llm")
        or (options.scenarios_per_environment > 0 and options.rollout_mode == "llm")
    )
    if needs_generator and generator is None:
        raise ValueError("the selected build modes require a configured JSON generator")
    if options.affinity_mode == "semantic" and embedder is None:
        raise ValueError("semantic affinity mode requires a configured embedding provider")

    graph = build_affinity_graph(
        catalog,
        neighbors_per_domain=options.neighbors_per_domain,
        minimum_score=options.affinity_threshold,
        mode=options.affinity_mode,
        embedder=embedder,
        rubric=generator,
    )
    groups = sample_domain_groups(
        graph,
        count=options.count,
        minimum_size=options.minimum_domains,
        maximum_size=options.maximum_domains,
        seed=options.seed,
    )
    manifests = compose_manifests(catalog, groups)
    manifests = attach_contexts(
        catalog,
        manifests,
        mode=options.context_mode,
        generator=generator,
    )
    manifests = validate_manifests(
        catalog,
        manifests,
        judge_mode=options.judge_mode,
        generator=generator,
    )
    manifests = attach_scenarios(
        catalog,
        manifests,
        count=options.scenarios_per_environment,
        mode=options.scenario_mode,
        generator=generator,
    )
    manifests = collect_trajectories(
        catalog,
        manifests,
        mode=options.rollout_mode,
        generator=generator,
        max_steps=options.max_steps,
    )
    manifests = verify_trajectories(catalog, manifests)
    accepted = sum(item["validation"]["accepted"] for item in manifests)
    scenarios = [scenario for item in manifests for scenario in item.get("scenarios", [])]
    verified = sum(
        scenario.get("verification", {}).get("accepted") is True for scenario in scenarios
    )

    return {
        "schema_version": "1.0",
        "generator": "cross-domain-scaling",
        "build": asdict(options),
        "summary": {
            "catalog_domains": len(catalog.domains),
            "requested_environments": options.count,
            "generated_environments": len(manifests),
            "accepted_environments": accepted,
            "generated_scenarios": len(scenarios),
            "verified_trajectories": verified,
        },
        "catalog": catalog.to_data(),
        "affinity_graph": graph,
        "groups": groups,
        "environments": manifests,
    }

