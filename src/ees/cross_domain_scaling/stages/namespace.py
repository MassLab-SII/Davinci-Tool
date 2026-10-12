from __future__ import annotations

from typing import Any

from ..models import Catalog


def build_namespace_map(
    catalog: Catalog,
    domain_ids: list[str],
    aliases: dict[str, str],
) -> dict[str, dict[str, Any]]:
    """Create an explicit πᵢ map for every externally visible contract symbol."""
    known = catalog.by_id()
    result: dict[str, dict[str, Any]] = {}
    for domain_id in domain_ids:
        domain = known[domain_id]
        alias = aliases[domain_id]
        tools = {operation.name: f"{alias}__{operation.name}" for operation in domain.operations}
        entities = {entity.name: f"{alias}__{entity.name}" for entity in domain.entities}
        identifiers = {
            f"{entity.name}.{field}": f"{alias}__{entity.name}__{field}"
            for entity in domain.entities
            for field in entity.fields
        }
        state_attributes = {
            entity.state_attribute: f"{alias}__{entity.state_attribute}"
            for entity in domain.entities
            if entity.state_attribute is not None
        }
        result[domain_id] = {
            "alias": alias,
            "tools": tools,
            "entities": entities,
            "identifiers": identifiers,
            "state_attributes": state_attributes,
        }
    return result


def namespace_collisions(namespace: dict[str, dict[str, Any]]) -> list[str]:
    collisions: list[str] = []
    for category in ("tools", "entities", "identifiers", "state_attributes"):
        owners: dict[str, str] = {}
        for domain_id, mapping in namespace.items():
            for transformed in mapping[category].values():
                previous = owners.get(transformed)
                if previous is not None and previous != domain_id:
                    collisions.append(f"{category}:{transformed}")
                owners[transformed] = domain_id
    return sorted(set(collisions))


def namespace_contract_errors(catalog: Catalog, manifest: dict[str, Any]) -> list[str]:
    expected = build_namespace_map(
        catalog,
        manifest.get("domain_ids", []),
        manifest.get("aliases", {}),
    )
    actual = manifest.get("namespace")
    if not isinstance(actual, dict):
        return ["namespace must be an object"]
    errors: list[str] = []
    for domain_id, mapping in expected.items():
        if actual.get(domain_id) != mapping:
            errors.append(f"namespace map does not match the contract for {domain_id}")
    errors.extend(f"namespace collision: {item}" for item in namespace_collisions(actual))
    return errors

