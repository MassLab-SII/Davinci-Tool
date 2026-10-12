# EES user guide

EES-Cross (Python package `cross_domain_scaling`, CLI `cross-domain-scaling`) builds multi-domain tool environments from a portable JSON catalog. It does not require a fixed dataset or a specific model provider.

The project is deliberately scoped to **cross-domain composition and verification**. Input domains
must already be executable; single-domain synthesis and single-domain auditing are out of scope.

The runtime uses **composition instead of source-code rewriting**. Every domain is loaded in
an isolated module, and its operations are exposed through namespaced routes such as
`calendar__create_event`. This preserves domain boundaries and avoids class, method, and state
collisions.

## Highlights

- dependency-free offline pipeline with deterministic results;
- optional embedding retrieval and model-based affinity rubric;
- explicit namespaces for tools, entities, identifiers, and state attributes;
- contract-grounded entity links, policies, and coherence constraints;
- linked initial state with reset/restore;
- cross-domain tasks, executable predicates, rollout traces, and outcome evidence;
- no bundled generated datasets or model credentials.

## Install

From the repository root:

```bash
pip install -e .
```

For optional LLM-assisted generation:

```bash
pip install -e '.[llm]'
cp .env.example .env
```

The EES CLI does not automatically read `.env`. Export the variables in your shell or use
your preferred secret manager.

## Quick start

Validate a domain catalog (see [ees-catalog-schema.md](ees-catalog-schema.md); EES domain catalogs
are not included in this release):

```bash
cross-domain-scaling validate path/to/catalog.json
```

Build five environments and verify one reference trajectory per environment entirely offline:

```bash
cross-domain-scaling build path/to/catalog.json \
  --output artifacts/demo \
  --count 5 \
  --min-domains 2 \
  --max-domains 3 \
  --seed 17 \
  --scenarios-per-environment 1 \
  --scenario-mode offline \
  --rollout-mode reference
```

Inspect or invoke a generated environment:

```bash
cross-domain-scaling inspect artifacts/demo/bundle.json
cross-domain-scaling invoke artifacts/demo/bundle.json <environment_id> <domain>__<operation> '<json-arguments>'
```

Use an OpenAI-compatible endpoint for richer world contexts and an additional semantic judge:

```bash
export CROSS_DOMAIN_SCALING_API_KEY='...'
export CROSS_DOMAIN_SCALING_BASE_URL='https://api.openai.com/v1'
export CROSS_DOMAIN_SCALING_MODEL='gpt-4.1-mini'
export CROSS_DOMAIN_SCALING_EMBEDDING_MODEL='text-embedding-3-large'

cross-domain-scaling build path/to/catalog.json \
  --output artifacts/llm-run \
  --affinity-mode semantic \
  --affinity-threshold 0.6 \
  --context-mode llm \
  --judge-mode llm \
  --scenarios-per-environment 2 \
  --scenario-mode llm \
  --rollout-mode llm
```

## Pipeline

1. Validate already executable domain contracts.
2. Retrieve related domains using embeddings or the deterministic offline scorer.
3. Apply a compatibility rubric and build the affinity graph.
4. Sample connected domain groups using bounded, coverage-aware random walks.
5. Build explicit namespace maps for tools, entities, identifiers, and state.
6. Construct and audit shared entities, linking fields, policies, and coherence constraints.
7. Initialize linked records and retain a restorable composite state.
8. Generate state-grounded cross-domain tasks and executable predicates.
9. Collect reference or model-driven trajectories from the same reset state.
10. Verify execution, domain transitions, entity transfer, state changes, and final coherence.

See [ees-catalog-schema.md](ees-catalog-schema.md) for the input contract.

## Development

See [development.md](development.md).

