"""Public package for cross-domain-scaling."""

from .models import Catalog, CatalogError, DomainSpec, EntitySpec
from .pipeline import BuildOptions, build_bundle
from .runtime import CompositeRuntime

__all__ = [
    "BuildOptions",
    "Catalog",
    "CatalogError",
    "CompositeRuntime",
    "DomainSpec",
    "EntitySpec",
    "build_bundle",
]

__version__ = "0.1.0"

