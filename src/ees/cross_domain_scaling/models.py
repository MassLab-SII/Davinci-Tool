from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


class CatalogError(ValueError):
    """Raised when a domain catalog violates its public contract."""


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_PYTHON_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_CONTAINER_TYPES = {"mapping", "sequence"}


def _object(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise CatalogError(f"{path} must be a JSON object")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"{path} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, path: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, list) or (not allow_empty and not value):
        qualifier = "a non-empty" if not allow_empty else "a"
        raise CatalogError(f"{path} must be {qualifier} JSON array")
    result = tuple(_string(item, f"{path}[{index}]") for index, item in enumerate(value))
    if len(set(result)) != len(result):
        raise CatalogError(f"{path} contains duplicate values")
    return result


def _reject_unknown(data: Mapping[str, Any], allowed: Iterable[str], path: str) -> None:
    extra = sorted(set(data) - set(allowed))
    if extra:
        raise CatalogError(f"{path} contains unknown fields: {', '.join(extra)}")


@dataclass(frozen=True, slots=True)
class OperationSpec:
    name: str
    description: str
    parameters: Mapping[str, Any]
    mode: str
    result_fields: tuple[str, ...]

    @classmethod
    def from_dict(cls, raw: Any, path: str) -> OperationSpec:
        data = _object(raw, path)
        _reject_unknown(
            data,
            {"name", "description", "parameters", "mode", "result_fields"},
            path,
        )
        name = _string(data.get("name"), f"{path}.name")
        if not _PYTHON_IDENTIFIER.fullmatch(name) or name.startswith("_"):
            raise CatalogError(f"{path}.name must be a public Python method name")

        parameters = _object(data.get("parameters"), f"{path}.parameters")
        if parameters.get("type") != "object":
            raise CatalogError(f"{path}.parameters.type must be 'object'")
        properties = parameters.get("properties", {})
        if not isinstance(properties, dict):
            raise CatalogError(f"{path}.parameters.properties must be an object")
        required = parameters.get("required", [])
        if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
            raise CatalogError(f"{path}.parameters.required must be an array of strings")
        missing = sorted(set(required) - set(properties))
        if missing:
            raise CatalogError(f"{path}.parameters.required references unknown fields: {missing}")

        mode = data.get("mode", _infer_operation_mode(name))
        if mode not in {"read", "write"}:
            raise CatalogError(f"{path}.mode must be 'read' or 'write'")
        result_fields = _string_list(data.get("result_fields", []), f"{path}.result_fields")
        return cls(
            name=name,
            description=_string(data.get("description"), f"{path}.description"),
            parameters=dict(parameters),
            mode=mode,
            result_fields=result_fields,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": dict(self.parameters),
            "mode": self.mode,
            "result_fields": list(self.result_fields),
        }


def _infer_operation_mode(name: str) -> str:
    read_prefixes = (
        "check_",
        "find_",
        "get_",
        "history",
        "list_",
        "quote",
        "search_",
        "stock",
        "view_",
    )
    return "read" if name.startswith(read_prefixes) else "write"


@dataclass(frozen=True, slots=True)
class RuntimeSpec:
    class_name: str
    source: str

    @classmethod
    def from_dict(cls, raw: Any, path: str) -> RuntimeSpec:
        data = _object(raw, path)
        _reject_unknown(data, {"class_name", "source"}, path)
        class_name = _string(data.get("class_name"), f"{path}.class_name")
        if not _PYTHON_IDENTIFIER.fullmatch(class_name):
            raise CatalogError(f"{path}.class_name is not a valid Python class name")
        return cls(
            class_name=class_name,
            source=_string(data.get("source"), f"{path}.source"),
        )

    def to_dict(self) -> dict[str, str]:
        return {"class_name": self.class_name, "source": self.source}


@dataclass(frozen=True, slots=True)
class EntitySpec:
    """State-facing entity contract supplied by an already executable domain."""

    name: str
    fields: tuple[str, ...]
    state_attribute: str | None = None
    container: str | None = None
    key_field: str | None = None
    value_field: str | None = None

    @classmethod
    def from_value(cls, raw: Any, path: str) -> EntitySpec:
        # A name-only entity remains useful for retrieval, but cannot participate in a state link.
        if isinstance(raw, str):
            return cls(name=_string(raw, path), fields=())

        data = _object(raw, path)
        allowed = {
            "name",
            "fields",
            "state_attribute",
            "container",
            "key_field",
            "value_field",
        }
        _reject_unknown(data, allowed, path)
        name = _string(data.get("name"), f"{path}.name")
        fields = _string_list(data.get("fields", []), f"{path}.fields")
        state_attribute = data.get("state_attribute")
        if state_attribute is not None:
            state_attribute = _string(state_attribute, f"{path}.state_attribute")
            if not _PYTHON_IDENTIFIER.fullmatch(state_attribute):
                raise CatalogError(f"{path}.state_attribute must be a Python attribute name")

        container = data.get("container")
        if container is not None:
            container = _string(container, f"{path}.container")
            if container not in _CONTAINER_TYPES:
                raise CatalogError(
                    f"{path}.container must be one of: {', '.join(sorted(_CONTAINER_TYPES))}"
                )
        if (state_attribute is None) != (container is None):
            raise CatalogError(f"{path}.state_attribute and container must be declared together")

        key_field = data.get("key_field")
        if key_field is not None:
            key_field = _string(key_field, f"{path}.key_field")
            if container != "mapping":
                raise CatalogError(f"{path}.key_field requires a mapping container")
            if key_field not in fields:
                raise CatalogError(f"{path}.key_field must appear in fields")

        value_field = data.get("value_field")
        if value_field is not None:
            value_field = _string(value_field, f"{path}.value_field")
            if container != "mapping":
                raise CatalogError(f"{path}.value_field requires a mapping container")
            if value_field not in fields:
                raise CatalogError(f"{path}.value_field must appear in fields")

        return cls(
            name=name,
            fields=fields,
            state_attribute=state_attribute,
            container=container,
            key_field=key_field,
            value_field=value_field,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"name": self.name, "fields": list(self.fields)}
        if self.state_attribute is not None:
            result["state_attribute"] = self.state_attribute
            result["container"] = self.container
        if self.key_field is not None:
            result["key_field"] = self.key_field
        if self.value_field is not None:
            result["value_field"] = self.value_field
        return result


@dataclass(frozen=True, slots=True)
class DomainSpec:
    id: str
    name: str
    summary: str
    entities: tuple[EntitySpec, ...]
    capabilities: tuple[str, ...]
    policies: tuple[str, ...]
    operations: tuple[OperationSpec, ...]
    runtime: RuntimeSpec

    @classmethod
    def from_dict(cls, raw: Any, path: str = "domain") -> DomainSpec:
        data = _object(raw, path)
        allowed = {
            "id",
            "name",
            "summary",
            "entities",
            "capabilities",
            "policies",
            "operations",
            "runtime",
        }
        _reject_unknown(data, allowed, path)
        domain_id = _string(data.get("id"), f"{path}.id")
        if not _IDENTIFIER.fullmatch(domain_id):
            raise CatalogError(
                f"{path}.id must start with a lowercase letter and contain only "
                "lowercase letters, digits, '_' or '-'"
            )

        operations_raw = data.get("operations")
        if not isinstance(operations_raw, list) or not operations_raw:
            raise CatalogError(f"{path}.operations must be a non-empty array")
        operations = tuple(
            OperationSpec.from_dict(item, f"{path}.operations[{index}]")
            for index, item in enumerate(operations_raw)
        )
        operation_names = [operation.name for operation in operations]
        if len(set(operation_names)) != len(operation_names):
            raise CatalogError(f"{path}.operations contains duplicate operation names")

        entities_raw = data.get("entities")
        if not isinstance(entities_raw, list) or not entities_raw:
            raise CatalogError(f"{path}.entities must be a non-empty array")
        entities = tuple(
            EntitySpec.from_value(item, f"{path}.entities[{index}]")
            for index, item in enumerate(entities_raw)
        )
        entity_names = [entity.name for entity in entities]
        if len(set(entity_names)) != len(entity_names):
            raise CatalogError(f"{path}.entities contains duplicate entity names")

        return cls(
            id=domain_id,
            name=_string(data.get("name"), f"{path}.name"),
            summary=_string(data.get("summary"), f"{path}.summary"),
            entities=entities,
            capabilities=_string_list(
                data.get("capabilities"), f"{path}.capabilities", allow_empty=False
            ),
            policies=_string_list(data.get("policies", []), f"{path}.policies"),
            operations=operations,
            runtime=RuntimeSpec.from_dict(data.get("runtime"), f"{path}.runtime"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "summary": self.summary,
            "entities": [entity.to_dict() for entity in self.entities],
            "capabilities": list(self.capabilities),
            "policies": list(self.policies),
            "operations": [operation.to_dict() for operation in self.operations],
            "runtime": self.runtime.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class Catalog:
    domains: tuple[DomainSpec, ...]

    @classmethod
    def from_data(cls, raw: Any) -> Catalog:
        if not isinstance(raw, list) or len(raw) < 2:
            raise CatalogError("catalog must be a JSON array containing at least two domains")
        domains = tuple(
            DomainSpec.from_dict(item, f"catalog[{index}]") for index, item in enumerate(raw)
        )
        ids = [domain.id for domain in domains]
        if len(set(ids)) != len(ids):
            raise CatalogError("catalog contains duplicate domain ids")
        return cls(domains=domains)

    def by_id(self) -> dict[str, DomainSpec]:
        return {domain.id: domain for domain in self.domains}

    def to_data(self) -> list[dict[str, Any]]:
        return [domain.to_dict() for domain in self.domains]

