from __future__ import annotations

import re
from typing import Any

from ..models import Catalog
from .namespace import build_namespace_map


def compose_manifests(catalog: Catalog, groups: list[list[str]]) -> list[dict[str, Any]]:
    known = catalog.by_id()
    manifests: list[dict[str, Any]] = []
    for index, domain_ids in enumerate(groups, start=1):
        routes: dict[str, dict[str, str]] = {}
        tools: list[dict[str, Any]] = []
        aliases: dict[str, str] = {}
        for domain_id in domain_ids:
            domain = known[domain_id]
            alias = _unique_alias(domain_id, set(aliases.values()))
            aliases[domain_id] = alias
            for operation in domain.operations:
                route = f"{alias}__{operation.name}"
                routes[route] = {"domain_id": domain_id, "operation": operation.name}
                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": route,
                            "description": f"[{domain.name}] {operation.description}",
                            "parameters": dict(operation.parameters),
                        },
                    }
                )
        namespace = build_namespace_map(catalog, domain_ids, aliases)
        manifests.append(
            {
                "id": f"env-{index:04d}",
                "domain_ids": list(domain_ids),
                "aliases": aliases,
                "namespace": namespace,
                "routes": routes,
                "tools": tools,
            }
        )
    return manifests


def _unique_alias(domain_id: str, used: set[str]) -> str:
    base = re.sub(r"[^a-z0-9_]", "_", domain_id.lower()).strip("_") or "domain"
    alias = base
    suffix = 2
    while alias in used:
        alias = f"{base}_{suffix}"
        suffix += 1
    return alias

