from __future__ import annotations

import json
from typing import Any

from ..llm import JsonGenerator
from ..models import Catalog
from .links import discover_entity_links


def attach_contexts(
    catalog: Catalog,
    manifests: list[dict[str, Any]],
    *,
    mode: str,
    generator: JsonGenerator | None,
) -> list[dict[str, Any]]:
    if mode not in {"offline", "llm"}:
        raise ValueError("context mode must be 'offline' or 'llm'")
    if mode == "llm" and generator is None:
        raise ValueError("LLM context mode requires a configured generator")
    known = catalog.by_id()
    enriched: list[dict[str, Any]] = []
    for manifest in manifests:
        domains = [known[domain_id] for domain_id in manifest["domain_ids"]]
        context = (
            _offline_context(catalog, manifest, domains)
            if mode == "offline"
            else _llm_context(catalog, domains, manifest, generator)
        )
        enriched.append({**manifest, "world": context})
    return enriched


def _offline_context(
    catalog: Catalog,
    manifest: dict[str, Any],
    domains: list[Any],
) -> dict[str, Any]:
    names = [domain.name for domain in domains]
    capabilities = [capability for domain in domains for capability in domain.capabilities]
    links = discover_entity_links(catalog, manifest["domain_ids"])
    shared = _shared_entities(links)
    policies = [
        {
            "id": f"policy-{index:03d}",
            "domains": [link["left"]["domain_id"], link["right"]["domain_id"]],
            "description": (
                f"Operations involving {link['left']['entity']} and {link['right']['entity']} "
                f"must preserve their shared {link['left']['field']} value."
            ),
            "predicate": {"kind": "link_preserved", "link_id": link["id"]},
        }
        for index, link in enumerate(links, start=1)
    ]
    constraints = [
        {
            "id": f"constraint-{index:03d}",
            "link_id": link["id"],
            "type": "field_equality",
            "description": link["description"],
        }
        for index, link in enumerate(links, start=1)
    ]
    return {
        "organization": {
            "name": "Integrated Operations Workspace",
            "description": "A shared workspace connecting " + ", ".join(names) + ".",
        },
        "roles": [
            {
                "name": "cross-functional operations coordinator",
                "domain_access": [domain.id for domain in domains],
                "responsibilities": capabilities[:6],
            }
        ],
        "scenario": (
            "Coordinate a traceable workflow across "
            + ", ".join(names)
            + " while respecting each domain's local policies."
        ),
        "shared_entities": shared,
        "entity_links": links,
        "cross_domain_policies": policies,
        "coherence_constraints": constraints,
        "generation": "offline",
    }


def _shared_entities(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": f"{link['left']['entity']}--{link['right']['entity']}",
            "domains": [link["left"]["domain_id"], link["right"]["domain_id"]],
            "link_id": link["id"],
        }
        for link in links
    ]


def _llm_context(
    catalog: Catalog,
    domains: list[Any],
    manifest: dict[str, Any],
    generator: JsonGenerator | None,
) -> dict[str, Any]:
    assert generator is not None
    domain_payload = [
        {
            "id": domain.id,
            "name": domain.name,
            "summary": domain.summary,
            "entities": [entity.to_dict() for entity in domain.entities],
            "capabilities": list(domain.capabilities),
            "policies": list(domain.policies),
        }
        for domain in domains
    ]
    prompt = {
        "domains": domain_payload,
        "namespace": manifest["namespace"],
        "available_routes": sorted(manifest["routes"]),
        "contract_grounded_link_candidates": discover_entity_links(
            catalog, manifest["domain_ids"]
        ),
        "required_schema": {
            "organization": {"name": "string", "description": "string"},
            "roles": [
                {
                    "name": "string",
                    "domain_access": ["domain id"],
                    "responsibilities": ["string"],
                }
            ],
            "scenario": "string",
            "shared_entities": [
                {"name": "string", "domains": ["domain id"], "link_id": "string"}
            ],
            "entity_links": [
                {
                    "id": "string",
                    "left": {"domain_id": "string", "entity": "string", "field": "string"},
                    "right": {"domain_id": "string", "entity": "string", "field": "string"},
                    "cardinality": "string",
                    "description": "string",
                }
            ],
            "cross_domain_policies": [
                {
                    "id": "string",
                    "domains": ["domain id"],
                    "description": "string",
                    "predicate": {"kind": "link_preserved", "link_id": "string"},
                }
            ],
            "coherence_constraints": [
                {
                    "id": "string",
                    "link_id": "string",
                    "type": "field_equality",
                    "description": "string",
                }
            ],
        },
    }
    result = generator.generate(
        system=(
            "Design a coherent multi-system workspace. Use only the supplied domains, entities, "
            "and operation routes. Return exactly one JSON object and no prose."
        ),
        prompt=json.dumps(prompt, ensure_ascii=False),
    )
    result["generation"] = "llm"
    return result

