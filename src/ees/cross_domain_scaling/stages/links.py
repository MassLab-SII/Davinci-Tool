from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..models import Catalog, EntitySpec
from ..runtime import CompositeRuntime


def discover_entity_links(catalog: Catalog, domain_ids: list[str]) -> list[dict[str, Any]]:
    """Propose contract-grounded linking fields between distinct executable domains."""
    known = catalog.by_id()
    links: list[dict[str, Any]] = []
    for left_index, left_id in enumerate(domain_ids):
        left = known[left_id]
        for right_id in domain_ids[left_index + 1 :]:
            right = known[right_id]
            candidates: list[tuple[int, EntitySpec, EntitySpec, str]] = []
            for left_entity in left.entities:
                if left_entity.state_attribute is None:
                    continue
                for right_entity in right.entities:
                    if right_entity.state_attribute is None:
                        continue
                    common_fields = set(left_entity.fields) & set(right_entity.fields)
                    for field in common_fields:
                        priority = 0
                        if field.endswith("_id") or field == left_entity.key_field:
                            priority += 3
                        if left_entity.name.lower() == right_entity.name.lower():
                            priority += 2
                        if field == right_entity.key_field:
                            priority += 1
                        candidates.append((priority, left_entity, right_entity, field))
            if not candidates:
                continue
            _, left_entity, right_entity, field = max(
                candidates,
                key=lambda item: (
                    item[0],
                    item[1].name == item[2].name,
                    item[3],
                ),
            )
            links.append(
                {
                    "id": f"link-{len(links) + 1:03d}",
                    "left": {
                        "domain_id": left_id,
                        "entity": left_entity.name,
                        "field": field,
                    },
                    "right": {
                        "domain_id": right_id,
                        "entity": right_entity.name,
                        "field": field,
                    },
                    "cardinality": "many-to-one",
                    "description": (
                        f"{left.name}.{left_entity.name}.{field} refers to the same logical value "
                        f"as {right.name}.{right_entity.name}.{field}."
                    ),
                }
            )
    return links


def validate_entity_links(
    catalog: Catalog,
    manifest: dict[str, Any],
    links: Any,
) -> list[str]:
    if not isinstance(links, list):
        return ["entity_links must be an array"]
    known = catalog.by_id()
    selected = set(manifest.get("domain_ids", []))
    errors: list[str] = []
    link_ids: set[str] = set()
    for index, link in enumerate(links):
        path = f"entity_links[{index}]"
        if not isinstance(link, dict):
            errors.append(f"{path} must be an object")
            continue
        link_id = link.get("id")
        if not isinstance(link_id, str) or not link_id:
            errors.append(f"{path}.id must be a non-empty string")
        elif link_id in link_ids:
            errors.append(f"duplicate link id: {link_id}")
        else:
            link_ids.add(link_id)
        for side in ("left", "right"):
            reference = link.get(side)
            if not isinstance(reference, dict):
                errors.append(f"{path}.{side} must be an object")
                continue
            domain_id = reference.get("domain_id")
            entity_name = reference.get("entity")
            field = reference.get("field")
            if domain_id not in selected or domain_id not in known:
                errors.append(f"{path}.{side} references an unavailable domain: {domain_id}")
                continue
            entity = _entity(known[domain_id], entity_name)
            if entity is None:
                errors.append(
                    f"{path}.{side} references unknown entity {domain_id}.{entity_name}"
                )
                continue
            if entity.state_attribute is None:
                errors.append(f"{path}.{side} entity has no state binding")
            if field not in entity.fields:
                errors.append(
                    f"{path}.{side} references unknown field {domain_id}.{entity_name}.{field}"
                )
        left = link.get("left", {})
        right = link.get("right", {})
        if left.get("domain_id") == right.get("domain_id"):
            errors.append(f"{path} must connect two distinct domains")
    return errors


def state_contract_errors(
    catalog: Catalog,
    manifest: dict[str, Any],
    runtime: CompositeRuntime,
) -> list[str]:
    known = catalog.by_id()
    errors: list[str] = []
    for domain_id in manifest["domain_ids"]:
        instance = runtime.domain_instance(domain_id)
        for entity in known[domain_id].entities:
            if entity.state_attribute is None:
                continue
            if not hasattr(instance, entity.state_attribute):
                errors.append(
                    f"{domain_id}.{entity.name} state attribute is missing: "
                    f"{entity.state_attribute}"
                )
                continue
            container = getattr(instance, entity.state_attribute)
            expected = dict if entity.container == "mapping" else list
            if not isinstance(container, expected):
                errors.append(
                    f"{domain_id}.{entity.name} expected {entity.container} state at "
                    f"{entity.state_attribute}"
                )
                continue
            records = list(container.values()) if isinstance(container, dict) else list(container)
            required_record_fields = set(entity.fields) - {
                entity.key_field,
                entity.value_field,
            }
            for record_index, record in enumerate(records):
                if not required_record_fields:
                    continue
                if not isinstance(record, dict):
                    errors.append(
                        f"{domain_id}.{entity.name} record {record_index} must be an object"
                    )
                    continue
                missing = sorted(required_record_fields - set(record))
                if missing:
                    errors.append(
                        f"{domain_id}.{entity.name} record {record_index} misses fields: {missing}"
                    )
    return errors


def initialize_linked_state(
    catalog: Catalog,
    runtime: CompositeRuntime,
    links: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Make selected records share linking-field values and return executable evidence."""
    known = catalog.by_id()
    evidence: list[dict[str, Any]] = []
    for link in links:
        left_ref = link["left"]
        right_ref = link["right"]
        left_entity = _entity(known[left_ref["domain_id"]], left_ref["entity"])
        right_entity = _entity(known[right_ref["domain_id"]], right_ref["entity"])
        assert left_entity is not None and right_entity is not None
        left_records = _records(
            runtime.domain_instance(left_ref["domain_id"]), left_entity
        )
        right_records = _records(
            runtime.domain_instance(right_ref["domain_id"]), right_entity
        )
        if not left_records or not right_records:
            evidence.append(
                {
                    "link_id": link["id"],
                    "initialized": False,
                    "reason": "one or both linked entity collections are empty",
                }
            )
            continue
        left_record, right_record = left_records[0], right_records[0]
        left_value = left_record.get(left_ref["field"])
        right_value = right_record.get(right_ref["field"])
        canonical = left_value if left_value is not None else right_value
        if canonical is None:
            evidence.append(
                {
                    "link_id": link["id"],
                    "initialized": False,
                    "reason": "neither linked record contains a usable field value",
                }
            )
            continue
        left_record.set(left_ref["field"], canonical)
        right_record.set(right_ref["field"], canonical)
        evidence.append(
            {
                "link_id": link["id"],
                "initialized": True,
                "value": canonical,
                "left_record": left_record.identity,
                "right_record": right_record.identity,
            }
        )
    runtime.commit_initial_state()
    return evidence


def link_consistency_errors(
    catalog: Catalog,
    runtime: CompositeRuntime,
    links: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
) -> list[str]:
    known = catalog.by_id()
    evidence_by_id = {item["link_id"]: item for item in evidence if item.get("initialized")}
    errors: list[str] = []
    for link in links:
        recorded = evidence_by_id.get(link["id"])
        if recorded is None:
            errors.append(f"{link['id']} has no initialization evidence")
            continue
        left_ref, right_ref = link["left"], link["right"]
        left_entity = _entity(known[left_ref["domain_id"]], left_ref["entity"])
        right_entity = _entity(known[right_ref["domain_id"]], right_ref["entity"])
        assert left_entity is not None and right_entity is not None
        left = _find_record(
            runtime.domain_instance(left_ref["domain_id"]),
            left_entity,
            recorded["left_record"],
        )
        right = _find_record(
            runtime.domain_instance(right_ref["domain_id"]),
            right_entity,
            recorded["right_record"],
        )
        if left is None or right is None:
            errors.append(f"{link['id']} can no longer locate its linked records")
            continue
        if left.get(left_ref["field"]) != right.get(right_ref["field"]):
            errors.append(f"{link['id']} linking fields diverged")
    return errors


def _entity(domain: Any, name: Any) -> EntitySpec | None:
    return next((entity for entity in domain.entities if entity.name == name), None)


@dataclass(slots=True)
class _Record:
    container: Any
    key: Any
    value: Any
    entity: EntitySpec

    @property
    def identity(self) -> str:
        return str(self.key if self.key is not None else "sequence-record")

    def get(self, field: str) -> Any:
        if field == self.entity.key_field:
            return self.key
        if field == self.entity.value_field and not isinstance(self.value, dict):
            return self.value
        if isinstance(self.value, dict):
            return self.value.get(field)
        return None

    def set(self, field: str, value: Any) -> None:
        if field == self.entity.key_field and isinstance(self.container, dict):
            if self.key != value:
                self.container[value] = self.container.pop(self.key)
                self.key = value
            return
        if field == self.entity.value_field and not isinstance(self.value, dict):
            self.container[self.key] = value
            self.value = value
            return
        if isinstance(self.value, dict):
            self.value[field] = value
            return
        raise ValueError(f"field {field} is not writable for entity {self.entity.name}")


def _records(instance: Any, entity: EntitySpec) -> list[_Record]:
    if entity.state_attribute is None:
        return []
    container = getattr(instance, entity.state_attribute)
    if isinstance(container, dict):
        return [
            _Record(container=container, key=key, value=value, entity=entity)
            for key, value in container.items()
        ]
    if isinstance(container, list):
        return [
            _Record(container=container, key=index, value=value, entity=entity)
            for index, value in enumerate(container)
            if isinstance(value, dict)
        ]
    return []


def _find_record(instance: Any, entity: EntitySpec, identity: str) -> _Record | None:
    return next(
        (record for record in _records(instance, entity) if record.identity == identity),
        None,
    )

