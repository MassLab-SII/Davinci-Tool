# Executable environments

The executable environments are **not included in this release** and will be released later. This
covers both the EGTS worlds and the EES domain catalogs.

## EGTS worlds

Each world wraps an authored environment as an MCP server (`/mcp`) with `/admin/reset` and
`/admin/status` endpoints and runs in its own container. The collection configs in
`configs/egts/` and the launchers in `scripts/egts/` already target the default ports below.

| World | Config | Launcher | Default port |
|---|---|---|---|
| ToolSandbox | `tool_sandbox.yaml` | `run_tool_sandbox.sh` | 30017 |
| API-Bank | `apibank.yaml` | `run_apibank.sh` | 30001 |
| StableToolBench | `stabletoolbench.yaml` | `run_stabletoolbench.sh` | 30014 |
| MCPMark filesystem / GitHub / Playwright / Postgres | `mcpmark_*.yaml` | `run_mcpmark_*.sh` | 30007–30010 |
| Terminal-Bench | `terminal-bench.yaml` | `run_terminal_bench.sh` | 30016 |
| MiniWoB | `miniwob.yaml` | `run_miniwob.sh` | 30012 |
| WebShop | `webshop.yaml` | `run_webshop.sh` | 30019 |
| ScienceWorld | `scienceworld.yaml` | `run_scienceworld.sh` | 30013 |
| DiscoveryWorld | `discoveryworld.yaml` | `run_discoveryworld.sh` | 30004 |
| Toolathlon | `toolathlon.yaml` | `run_toolathlon.sh` | 30018 |
| AppWorld | `appworld.yaml` | `run_appworld.sh` | 30002 |

## EES domains

EES takes a catalog of already-executable domains: a JSON array of domain contracts with Python
runtime source. The format is described in [ees-catalog-schema.md](ees-catalog-schema.md). Runtime
source in a catalog is executed locally; only use catalogs from trusted sources.
