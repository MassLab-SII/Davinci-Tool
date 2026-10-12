from __future__ import annotations

import inspect
import types
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .models import Catalog, DomainSpec


@dataclass(slots=True)
class _LoadedDomain:
    spec: DomainSpec
    instance: Any


class CompositeRuntime:
    """Load trusted domain classes independently and route namespaced operations."""

    def __init__(self, catalog: Catalog, manifest: dict[str, Any]) -> None:
        known = catalog.by_id()
        domain_ids = manifest.get("domain_ids")
        routes = manifest.get("routes")
        if not isinstance(domain_ids, list) or not isinstance(routes, dict):
            raise ValueError("invalid environment manifest")

        self._domains: dict[str, _LoadedDomain] = {}
        for domain_id in domain_ids:
            if domain_id not in known:
                raise ValueError(f"manifest references unknown domain: {domain_id}")
            spec = known[domain_id]
            self._domains[domain_id] = _LoadedDomain(spec, _instantiate(spec))
        self._routes = dict(routes)
        self._namespace = dict(manifest.get("namespace", {}))
        self._verify_routes()
        self._baseline = self._capture_raw_state()
        if "initial_state" in manifest:
            self.restore(manifest["initial_state"])
            self.commit_initial_state()

    @property
    def routes(self) -> tuple[str, ...]:
        return tuple(sorted(self._routes))

    def invoke(self, route: str, arguments: dict[str, Any] | None = None) -> Any:
        if route not in self._routes:
            raise KeyError(f"unknown operation route: {route}")
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            raise TypeError("operation arguments must be an object")
        binding = self._routes[route]
        loaded = self._domains[binding["domain_id"]]
        method = getattr(loaded.instance, binding["operation"])
        signature = inspect.signature(method)
        try:
            signature.bind(**arguments)
        except TypeError as exc:
            raise TypeError(f"invalid arguments for {route}: {exc}") from exc
        return method(**arguments)

    def domain_instance(self, domain_id: str) -> Any:
        """Expose an instance to trusted state-linking and verification components."""
        if domain_id not in self._domains:
            raise KeyError(f"domain is not loaded: {domain_id}")
        return self._domains[domain_id].instance

    def snapshot(self) -> dict[str, Any]:
        """Return the public composite state using πᵢ-transformed attribute names."""
        if not self._namespace:
            return {
                domain_id: deepcopy(
                    {
                        key: value
                        for key, value in vars(loaded.instance).items()
                        if not key.startswith("_")
                    }
                )
                for domain_id, loaded in self._domains.items()
            }

        state: dict[str, Any] = {}
        for domain_id, loaded in self._domains.items():
            attributes = self._namespace.get(domain_id, {}).get("state_attributes", {})
            for original, transformed in attributes.items():
                if hasattr(loaded.instance, original):
                    state[transformed] = deepcopy(getattr(loaded.instance, original))
        return state

    def restore(self, snapshot: dict[str, Any]) -> None:
        if not isinstance(snapshot, dict):
            raise TypeError("state snapshot must be an object")
        if not self._namespace:
            for domain_id, values in snapshot.items():
                if domain_id not in self._domains or not isinstance(values, dict):
                    raise ValueError(f"invalid state snapshot entry: {domain_id}")
                instance = self._domains[domain_id].instance
                for attribute, value in values.items():
                    setattr(instance, attribute, deepcopy(value))
            return

        reverse: dict[str, tuple[str, str]] = {}
        for domain_id, mapping in self._namespace.items():
            for original, transformed in mapping.get("state_attributes", {}).items():
                reverse[transformed] = (domain_id, original)
        unknown = sorted(set(snapshot) - set(reverse))
        if unknown:
            raise ValueError(f"snapshot contains unknown state attributes: {unknown}")
        for transformed, value in snapshot.items():
            domain_id, original = reverse[transformed]
            setattr(self._domains[domain_id].instance, original, deepcopy(value))

    def reset(self) -> None:
        for domain_id, values in self._baseline.items():
            instance = self._domains[domain_id].instance
            instance.__dict__.clear()
            instance.__dict__.update(deepcopy(values))

    def commit_initial_state(self) -> None:
        self._baseline = self._capture_raw_state()

    def _capture_raw_state(self) -> dict[str, dict[str, Any]]:
        return {
            domain_id: deepcopy(vars(loaded.instance))
            for domain_id, loaded in self._domains.items()
        }

    def _verify_routes(self) -> None:
        for route, binding in self._routes.items():
            if not isinstance(route, str) or not isinstance(binding, dict):
                raise ValueError("route table must map strings to objects")
            domain_id = binding.get("domain_id")
            operation = binding.get("operation")
            if domain_id not in self._domains:
                raise ValueError(f"route {route} references an unloaded domain")
            method = getattr(self._domains[domain_id].instance, operation, None)
            if not callable(method):
                raise ValueError(f"route {route} references a missing method: {operation}")


def _instantiate(spec: DomainSpec) -> Any:
    module = types.ModuleType(f"_cross_domain_scaling_{spec.id.replace('-', '_')}")
    code = compile(spec.runtime.source, f"<{spec.id}>", "exec")
    exec(code, module.__dict__)  # noqa: S102 - catalogs are explicitly trusted local code
    candidate = module.__dict__.get(spec.runtime.class_name)
    if not isinstance(candidate, type):
        raise ValueError(
            f"domain {spec.id} did not define class {spec.runtime.class_name}"
        )
    try:
        return candidate()
    except TypeError as exc:
        raise ValueError(f"domain {spec.id} constructor must not require arguments") from exc

