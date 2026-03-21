# Architecture — SOLVE-IT MCP Server

## 1. Overview

The SOLVE-IT MCP Server provides programmatic access to the SOLVE-IT digital forensics knowledge base via the Model Context Protocol. It is built on the MCP Chassis framework, which supplies the transport layer, security middleware pipeline, configuration management, and extension auto-discovery. SOLVE-IT-specific logic lives entirely in the init hook and the single extension module.

```
┌─────────────────────────────────────────────────────┐
│                  MCP Client (stdio)                  │
└──────────────────────┬──────────────────────────────┘
                       │ JSON-RPC over stdin/stdout
┌──────────────────────▼──────────────────────────────┐
│               MCP Chassis Framework                  │
│  ┌──────────────────────────────────────────────┐   │
│  │          Security Middleware Pipeline         │   │
│  │  I/O Limits → Auth → Rate Limit →            │   │
│  │  Sanitize → Validate                         │   │
│  └──────────────────────┬───────────────────────┘   │
│  ┌──────────────────────▼───────────────────────┐   │
│  │           ChassisServer._dispatch_tool()      │   │
│  └──────────────────────┬───────────────────────┘   │
└─────────────────────────┼───────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────┐
│               SOLVE-IT Extension Layer               │
│  ┌───────────────────┐  ┌──────────────────────┐    │
│  │  solveit_init.py  │  │  solveit_tools.py    │    │
│  │  (init hook)      │  │  (tool handlers)     │    │
│  └─────────┬─────────┘  └──────────┬───────────┘    │
│            │                       │                 │
│  ┌─────────▼───────────────────────▼───────────┐    │
│  │              KnowledgeBase                   │    │
│  │         (SOLVE-IT library, read-only)        │    │
│  └─────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────┘
```

---

## 2. Startup Sequence

```
1. config/default.toml loaded by MCP Chassis
2. solveit_init.py (init hook) runs
   a. Reads [app] config section
   b. Resolves solveit_data_path
   c. Adds SOLVE-IT library directory to sys.path
   d. Instantiates KnowledgeBase
   e. Attaches instance to server._kb
3. Extension discovery scans extensions/tools/
   → finds solveit_tools.py
4. solveit_tools.py register(server) runs
   a. Always registers: status tool (1)
   b. If KB loaded successfully:
      - Batch tools via register_simple_tools (8)
      - Relationship tools, manual registration (5)
      - Search tool (1)
      - Full-detail tools if config-gated flag enabled (0 or 3)
      - Extension info tool (1)
```

The init hook runs before extension discovery, so `server._kb` is available when `solveit_tools.py` calls `register()`. If the KB fails to load, the status tool still registers and reports the failure; all other tools are skipped.

---

## 3. Request Flow

```
Client → stdio transport → MCP SDK → ChassisServer._dispatch_tool()
  → Middleware Pipeline (I/O limits → Auth → Rate limit → Sanitize → Validate)
  → Tool Handler (in solveit_tools.py)
  → KnowledgeBase method call
  → JSON response → stdout
```

The middleware pipeline is applied before every handler invocation. SOLVE-IT tools do not modify or bypass it. All tool responses are plain Python dicts or strings serialised by the chassis into `CallToolResult`.

---

## 4. Tool Registration

Tools are registered in `solveit_tools.py` via two mechanisms.

### Batch registration (register_simple_tools)

Eight tools are registered through the chassis batch helper. These are straightforward lookups and listings where input schema, handler mapping, and KB method binding follow a uniform pattern:

- `solveit_get_technique` — technique lookup by ID
- `solveit_get_weakness` — weakness lookup by ID
- `solveit_get_mitigation` — mitigation lookup by ID
- `solveit_list_techniques` — list all techniques (ID and name)
- `solveit_list_weaknesses` — list all weaknesses (ID and name)
- `solveit_list_mitigations` — list all mitigations (ID and name)
- `solveit_list_objectives` — list all objectives
- `solveit_get_techniques_for_objective` — techniques for a given objective

### Manual registration

Eleven tools are registered individually to accommodate non-uniform requirements:

| Group | Count | Reason for manual registration |
|---|---|---|
| Relationship tools | 5 | ID format validated before KB call |
| Search tool | 1 | Input schema varies based on config flags |
| Full-detail tools | 0 or 3 | Config-gated; only registered when `enable_full_detail_tools = true` |
| Status tool | 1 | Always registered, even when KB fails to load |
| Extension info tool | 1 | Requires access to extension metadata at registration time |

Total tools exposed: 15 (without full-detail) or 18 (with full-detail), plus status = 16 or 19.

---

## 5. Knowledge Base

The SOLVE-IT library is the authoritative source of forensics knowledge used by all tools.

- Loaded once at startup in the init hook (`solveit_init.py`)
- Not pip-installable — the library directory is added to `sys.path` at runtime using the resolved `solveit_data_path`
- Exposes a `KnowledgeBase` class with methods for lookups, listings, relationship traversal, and search
- Read-only and deterministic — no internal state changes after construction, making it safe for concurrent tool calls
- Supports SOLVE-IT-X extension data; enabled via `enable_extensions = true` in `[app]`

The KB instance is stored on `server._kb` and accessed directly by tool handlers in `solveit_tools.py`.

---

## 6. Configuration

All SOLVE-IT-specific settings live in the `[app]` section of `config/default.toml`. The chassis `[server]`, `[security]`, and `[extensions]` sections are inherited unchanged.

```toml
[app]
solveit_data_path = "../solve-it/solve-it-main"
objective_mapping = "solve-it.json"
enable_extensions = true                          # SOLVE-IT-X data
enable_full_detail_tools = false                  # gates 3 additional tools

[app.search]
enable_item_types_filter = true
enable_substring_match = true
enable_search_logic = true
```

Key points:

- TOML-only — there are no environment variable overrides for `[app]` settings
- `solveit_data_path` controls where the init hook looks for the SOLVE-IT library and data files
- `enable_full_detail_tools` is checked at registration time in `register()`; changing it requires a server restart
- `[app.search]` flags affect both the search tool's input schema (fields are conditionally included) and runtime behaviour

---

## 7. Security

Security is inherited entirely from the MCP Chassis middleware pipeline. The pipeline runs before every tool handler, in this order:

1. I/O limit check (request size)
2. Auth check
3. Rate limit check
4. Input sanitization
5. Input validation against JSON schema

SOLVE-IT tools do not modify, bypass, or extend the pipeline. No user-uploaded content or external API calls are involved — all data access is read-only against the local KB. The primary risk surface is malformed tool arguments, which the pipeline handles before handlers are reached.

For chassis-level security details (profiles, rate limit configuration, sanitization rules), see the MCP Chassis documentation.
