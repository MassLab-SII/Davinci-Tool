# Catalog schema

A catalog is a JSON array of domain objects. Unknown fields are rejected so that misspelled
configuration does not silently affect a run.

```json
[
  {
    "id": "inventory",
    "name": "Inventory",
    "summary": "Tracks stock levels for a small warehouse.",
    "entities": [
      {
        "name": "product",
        "fields": ["sku", "quantity"],
        "state_attribute": "stock",
        "container": "mapping",
        "key_field": "sku",
        "value_field": "quantity"
      }
    ],
    "capabilities": ["stock lookup", "inventory adjustment"],
    "policies": ["Stock cannot become negative."],
    "operations": [
      {
        "name": "stock",
        "description": "Return the stock level for a SKU.",
        "mode": "read",
        "result_fields": ["sku", "quantity"],
        "parameters": {
          "type": "object",
          "properties": {"sku": {"type": "string"}},
          "required": ["sku"]
        }
      }
    ],
    "runtime": {
      "class_name": "InventoryDomain",
      "source": "class InventoryDomain:\n    ..."
    }
  }
]
```

## Domain fields

| Field | Required | Meaning |
|---|---:|---|
| `id` | yes | Stable lowercase identifier (`a-z`, `0-9`, `_`, `-`). |
| `name` | yes | Human-readable name. |
| `summary` | yes | Short description used by affinity scoring. |
| `entities` | yes | Entity contracts and their optional runtime state bindings. |
| `capabilities` | yes | User-facing capabilities. |
| `policies` | no | Domain constraints. |
| `operations` | yes | Callable public methods and JSON parameter schemas. |
| `runtime` | yes | Python source plus the class to instantiate. |

Each operation name must match a public method on the runtime class. Constructors must be
callable without arguments. Runtime source executes locally; therefore only use catalogs from
trusted sources.

## Entity contract

An entity that participates in cross-domain linking declares:

- `fields`: fields that may be referenced by linking rules;
- `state_attribute`: the runtime instance attribute holding its records;
- `container`: `mapping` or `sequence`;
- `key_field`: optional field represented by a mapping key;
- `value_field`: optional field represented by a scalar mapping value.

Name-only entities are accepted for retrieval vocabulary, but they cannot be used as executable
link endpoints.

## Operation contract

`mode` is `read` or `write`. `result_fields` describes values observable in a successful result.
These fields allow scenario construction to prove that a value observed in one domain is consumed
by an operation in another domain.

## Generated bundle

`bundle.json` contains the source catalog snapshot, affinity graph, namespace maps, shared-world
contracts, linked initial states, scenarios, optional trajectories, verification evidence, and build
configuration. Including the snapshot makes a run reproducible, but also means the bundle inherits
the catalog's provenance and licensing obligations.


