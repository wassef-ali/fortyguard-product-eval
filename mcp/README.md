# FortyGuard MCP — demo & setup

The third FortyGuard product is the **Temperature MCP**: an MCP server that gives
AI agents (Claude Code, Cursor, Codex, …) 12 tools over the same Temperature API
used by this project. It is the official way to let an agent automate
heatmaps, environmental parameters, satellite/street-view segmentation, and
Heat Intelligence reports.

Reference: [fortyguard-mcp on PyPI](https://pypi.org/project/fortyguard-mcp/) and
its [GitHub repository](https://github.com/mohamedxadel/fortyguard-mcp).

## What the server exposes (12 tools)

- `get_credit_usage` — account plan, credits, per-endpoint breakdown
- `get_storage_info` — local result archive
- `validate_aoi` — measure a GeoJSON AOI locally (no API call)
- `split_aoi` — split an AOI into pieces under a per-plan area cap
- `submit_heatmap` / `create_heatmap` — temperature heatmap (async / wait-inline)
- `get_env_params` — environmental parameters at a point (temperature sourced
  from a completed heatmap via `from_activity_id=`, or passed directly)
- `submit_satellite` / `submit_streetview` — imagery segmentation (premium)
- `submit_heat_intelligence` — report with geographic/environmental/urban/
  events/anthropogenic sections (premium)
- `check_status` / `get_result_slice` — collect and slice a submitted analysis

## Install

```bash
# Option A: run without a permanent install (uv)
uvx --from git+https://github.com/mohamedxadel/fortyguard-mcp fortyguard-mcp

# Option B: install from PyPI
pip install fortyguard-mcp
```

The server reads `FORTYGUARD_API_KEY` from the environment (or a user-level
`.env` — deliberately **not** the current directory).

## Wire it into an MCP client

### Claude Code / Claude Desktop (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "fortyguard": {
      "command": "fortyguard-mcp",
      "env": { "FORTYGUARD_API_KEY": "YOUR_API_KEY" }
    }
  }
}
```

### Cursor (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "fortyguard": {
      "command": "fortyguard-mcp",
      "env": { "FORTYGUARD_API_KEY": "YOUR_API_KEY" }
    }
  }
}
```

## Smoke test (no API call, no credits)

`tools_list.py` performs a stdio JSON-RPC handshake with the server and lists
its tools. It never calls the API, so it spends nothing:

```bash
pip install fortyguard-mcp
python mcp/tools_list.py
```

If the server binary is not on PATH, the script falls back to
`python -m fortyguard_mcp`.
