# SOLVE-IT MCP Server

**Summary**: This project is an [MCP (Model Context Protocol)](https://modelcontextprotocol.io/) server that wraps the [SOLVE-IT](https://github.com/SOLVE-IT-DF/solve-it) digital forensics knowledge base and its built-in library in order to provision LLMs with programmatic access to SOLVE-IT content.

SOLVEI-IT provides a structured taxonomy of digital forensic techniques, the weaknesses that affect evidence reliability, and the mitigations that address those weaknesses. This server exposes tools for querying, navigating, and searching that knowledge base. 

## Quick Start

### 1. Install dependencies

**Option 1:**

```bash
pip install "mcp>=1.6.0,<2.0" pydantic pybtex
```

**Option 2:**
 From within the root directory of this folder.
```bash
pip install -e ".[dev]"
```

### 2. Download this repo.

### 3. Download the main SOLVE-IT repo. 

**Ref**: https://github.com/SOLVE-IT-DF/solve-it

### 4. Configure config/default.toml 

The default.toml file from this repository must point to your downloaded instance of the main SOLVE-IT repository. 

**Example:**
```
solveit_data_path = "<full path to your>/solve-it-main"
```

### 5. Run the MCP server

**Note**: You will not need to run the server manually if your MCP client runs the server when connecting to it, such as with the example in step 6 below.

**Example 1:**
```
python3 run.py --config config/default.toml
```

**Example 2:**
```
python -m mcp_chassis
```

### 6. Configure your MCP client

Configure your MCP client to connect to the MCP server. In some cases (e.g. Claude Desktop), the client will also start the MCP server.

**Example Claude Desktop Config:**

**Example File:** `claude_desktop_config.json` \
**Example Path (macOS)**: `~/Library/Application Support/Claude/claude_desktop_config.json`):

**Example Config**:
```json
{
  "mcpServers": {
    "solveit": {
      "command": "python3",
      "args": ["/path/to/mcp_server/run.py", "--config", "/path/to/mcp_server/config/default.toml"]
    }
  }
}
```


## Available MCP Tools

### Lookup (3 tools)

| Tool | Description |
|---|---|
| `solveit_get_technique` | Retrieve full details for a single technique by ID |
| `solveit_get_weakness` | Retrieve full details for a single weakness by ID |
| `solveit_get_mitigation` | Retrieve full details for a single mitigation by ID |

### Summary Listing (3 tools)

| Tool | Description |
|---|---|
| `solveit_list_techniques` | List all techniques with ID and name |
| `solveit_list_weaknesses` | List all weaknesses with ID and name |
| `solveit_list_mitigations` | List all mitigations with ID and name |

### Objectives (2 tools)

| Tool | Description |
|---|---|
| `solveit_list_objectives` | List all forensic objectives defined in the active mapping |
| `solveit_get_techniques_for_objective` | List techniques categorized under a given objective |

### Relationships (5 tools)

| Tool | Description |
|---|---|
| `solveit_get_weaknesses_for_technique` | List weaknesses that affect a given technique |
| `solveit_get_mitigations_for_weakness` | List mitigations that address a given weakness |
| `solveit_get_techniques_for_weakness` | List techniques affected by a given weakness |
| `solveit_get_weaknesses_for_mitigation` | List weaknesses addressed by a given mitigation |
| `solveit_get_techniques_for_mitigation` | List techniques related to a given mitigation |

### Search (1 tool)

| Tool | Description |
|---|---|
| `solveit_search` | Full-text search across techniques, weaknesses, and mitigations |

### Extension Info (1 tool)

| Tool | Description |
|---|---|
| `solveit_list_loaded_extensions` | List any SOLVE-IT-X extension datasets currently loaded |

### Citations (2 tools)

| Tool | Description |
|---|---|
| `solveit_get_citation` | Retrieve a citation by its DFCite ID |
| `solveit_list_citations` | List all citation IDs in the knowledge base |

### Status (1 tool)

| Tool | Description |
|---|---|
| `solveit_status` | Report data load status, item counts (including citations), and active configuration |

### Full-Detail Listings

**Note:** These tools are disabled by default due to the large volume of data they return. They can be enabled in **config/default.toml**. 

| Tool | Description |
|---|---|
| `solveit_list_techniques_full_detail` | List all techniques with complete field data |
| `solveit_list_weaknesses_full_detail` | List all weaknesses with complete field data |
| `solveit_list_mitigations_full_detail` | List all mitigations with complete field data |

## Configuration

The `[app]` section in `config/default.toml` controls SOLVE-IT-specific settings. Top-level `[app]` keys can also be overridden by environment variables with the `MCP_APP_` prefix (env vars take precedence over TOML values):

| Environment Variable | Config Key | Type |
|---|---|---|
| `MCP_APP_SOLVEIT_DATA_PATH` | `solveit_data_path` | string |
| `MCP_APP_OBJECTIVE_MAPPING` | `objective_mapping` | string |
| `MCP_APP_ENABLE_EXTENSIONS` | `enable_extensions` | bool (`true`/`false`/`1`/`0`/`yes`/`no`) |
| `MCP_APP_INIT_REQUIRED` | `init_required` | bool |
| `MCP_APP_ENABLE_FULL_DETAIL_TOOLS` | `enable_full_detail_tools` | bool |

```toml
[app]
# Path to the SOLVE-IT repository root (absolute or relative to CWD).
solveit_data_path = "/<path>/<to>/<your>/solve-it-main"

# Objective mapping file (must exist in the SOLVE-IT data/ directory).
# Default: "solve-it.json" (the standard SOLVE-IT categorization).
# Custom mapping files can be placed in the data/ directory to provide
# alternative categorizations of techniques into objectives.
# See: https://custom-viewer.solveit-df.org
objective_mapping = "solve-it.json"

# Whether to load SOLVE-IT-X extension data.
enable_extensions = true

# If true (default), the server exits immediately when the KB fails to load.
# If false, the server starts in degraded mode with only solveit_status available.
init_required = true

# Enable full-detail listing tools (large payloads, disabled by default).
# WARNING: These tools return the entire dataset for a given type and may
# consume significant LLM context. You may also need to increase
# [security.io_limits] max_response_size when enabling this.
enable_full_detail_tools = false

[app.search]
# Each flag controls whether the corresponding parameter is exposed
# in the solveit_search tool's schema. When disabled, the default
# value is used: item_types=all, substring_match=false, search_logic="AND"
enable_item_types_filter = true
enable_substring_match = true
enable_search_logic = true
```

**`solveit_data_path`** — Path to the cloned SOLVE-IT repository. Accepts an absolute path or a path relative to the working directory when the server is started.

**`objective_mapping`** — Filename of the JSON mapping that categorizes techniques into forensic objectives. Must exist inside the SOLVE-IT `data/` directory. The default `solve-it.json` reflects the official categorization.

**`enable_extensions`** — When `true`, the server loads any SOLVE-IT-X extension datasets found in the repository.

**`init_required`** — When `true` (the default), the server exits with a clear error if the knowledge base fails to load. When `false`, the server starts in degraded mode with only `solveit_status` available, which reports the load failure. Set to `false` during development if you need to test server behavior without valid KB data.

**`enable_full_detail_tools`** — Controls whether the three full-detail listing tools are registered. See the section below before enabling.

**Search parameter flags** — The three `[app.search]` flags each control whether the corresponding parameter appears in the `solveit_search` tool schema. When a flag is `false`, the parameter is hidden and its default value is applied silently: `item_types` defaults to all types, `substring_match` defaults to `false` (word-boundary matching), and `search_logic` defaults to `"AND"`.

## Enabling Full-Detail Tools

Set `enable_full_detail_tools = true` in `config/default.toml` to register the three full-detail listing tools.

**Warning:** These tools return the complete dataset for an entire item type in a single response. Depending on the size of the SOLVE-IT data and any loaded extensions, responses can be very large and may consume a significant portion of an LLM's context window. If you enable these tools you will likely also need to raise the response size limit:

```toml
[security.io_limits]
max_response_size = 20971520   # 20 MB; default is 5 MB
```

## Security

Security behavior is inherited from the MCP server chassis on which this MCP server was built. Every tool request passes through the middleware pipeline in this order:

```
I/O limits → Auth → Rate limit → Sanitize → Validate
```

Through this pipeline, sanitization attempts can be applied to inputs before they reach tool handlers. The default security profile is `moderate`. 

**IMPORTANT**: These protections are a basic attempt to provide some security by default. If you decide to use this server in a production setting, we recommend you still perform security testing and modify the code of this project to implement security mitigations as appropriate for your threat environment and risk tolerance.

| Profile | Rate Limit | I/O Limits | Sanitization | Error Detail |
|---|---|---|---|---|
| `strict` | 60 rpm global, 30 rpm/tool | 1 MB req, 5 MB resp | Full (path traversal, shell metachars, control chars) | Generic |
| `moderate` | 120 rpm global, 60 rpm/tool | 5 MB req, 20 MB resp | Path traversal + control chars | Detailed |
| `permissive` | Disabled | 50 MB req/resp | Null bytes only | Detailed |

The active profile is set via `[security] profile` in `config/default.toml`, where the individual settings can be used to override elements of the specified profile. Furthermore, the profile set in default.toml can be overridden with the `MCP_SECURITY_PROFILE` environment variable.

## Testing

```bash
python -m pytest tests/              # All tests
python -m pytest tests/unit/         # Unit tests only
python -m pytest tests/integration/  # Integration tests only
```

## Project Structure

```
src/mcp_chassis/
  server.py                        — ChassisServer: central orchestrator
  config.py                        — Configuration dataclasses and TOML loading
  __main__.py                      — CLI entry point
  extensions/
    solveit_init.py                — Initializes the SOLVE-IT data loader on startup
    tools/
      solveit_tools.py             — All 21 SOLVE-IT tool registrations and handlers
  middleware/
    pipeline.py                    — Security middleware pipeline
  security/                        — Rate limiting, sanitization, validation, profiles
  transport/                       — Stdio transport (production)
config/
  default.toml                     — Server and application configuration
tests/
  unit/                            — Unit tests
  integration/                     — Integration tests (stdio subprocess)
docs/
  ARCHITECTURE.md                  — Component design and data flow
  TROUBLESHOOTING.md               — Common issues and fixes
```

## Using with MCP Clients

The project includes a `run.py` launcher that handles Python path setup automatically. Use absolute paths for both `run.py` and `--config` so the server works regardless of the client's working directory.

**Prerequisites:** Python dependencies must be installed on the machine running the server:

```bash
cd /path/to/mcp_server
pip install "mcp>=1.2.0,<2.0" pydantic pybtex   # minimum dependencies
```

Before configuring a client, set `solveit_data_path` in `config/default.toml` to an absolute path:

```toml
[app]
solveit_data_path = "/absolute/path/to/solve-it/solve-it-main"
```

### Claude Code

Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "solveit": {
      "type": "stdio",
      "command": "python3",
      "args": ["/path/to/mcp_server/run.py", "--config", "/path/to/mcp_server/config/default.toml"]
    }
  }
}
```

### Claude Desktop

Add to `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "solveit": {
      "command": "python3",
      "args": ["/path/to/mcp_server/run.py", "--config", "/path/to/mcp_server/config/default.toml"]
    }
  }
}
```

### Alternative: Using `pip install`

If you prefer not to use `run.py`, install the package and use `-m` directly:

```bash
pip install -e .
```

```json
{
  "mcpServers": {
    "solveit": {
      "command": "python3",
      "args": ["-m", "mcp_chassis", "--config", "/path/to/mcp_server/config/default.toml"]
    }
  }
}
```
