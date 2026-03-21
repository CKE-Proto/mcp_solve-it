# Troubleshooting Guide — SOLVE-IT MCP Server

This guide covers common issues when running, configuring, or extending the
SOLVE-IT MCP Server. Issues are grouped into SOLVE-IT-specific problems
(KB loading, path resolution, tool availability) and general server issues
inherited from the underlying chassis.

> **Note:** Commands in this guide use `python -m mcp_chassis`. If you haven't
> installed the package with `pip install`, use `python3 run.py` (from the
> project root) as a drop-in replacement — it accepts the same arguments.

---

## SOLVE-IT-Specific Issues

---

## Issue S1: Knowledge Base Fails to Load at Startup

**Symptom:** The server starts, but most SOLVE-IT tools are missing from the tool
list. Calling `solveit_status` returns `{"status": "error", "error": "..."}`.

**Causes and fixes:**

1. **Wrong `solveit_data_path` in config.** The path in `config/default.toml` must
   point to the root of the SOLVE-IT repository (the directory that contains the
   `data/` folder and the `solve_it_library` package). Check the path:
   ```toml
   [app]
   solveit_data_path = "../solve-it/solve-it-main"   # relative to server CWD
   ```
   Use an absolute path to avoid ambiguity:
   ```toml
   solveit_data_path = "/absolute/path/to/solve-it/solve-it-main"
   ```

2. **`solve_it_library` package not importable.** The init hook adds `solveit_data_path`
   to `sys.path` at runtime. If the library is not in that directory, the import will
   fail. Verify:
   ```bash
   python -c "import sys; sys.path.insert(0, '/path/to/solve-it/solve-it-main'); from solve_it_library import KnowledgeBase; print('OK')"
   ```

3. **Wrong `objective_mapping` file name.** The mapping file must exist in the
   `data/` subdirectory of the SOLVE-IT repository. The default is `solve-it.json`.
   List available mappings:
   ```bash
   ls /path/to/solve-it/solve-it-main/data/*.json
   ```

4. **Check startup logs for the exact error.** Run the server with debug logging to
   see the full traceback:
   ```bash
   python -m mcp_chassis --config config/default.toml --log-level DEBUG 2>&1 | head -80
   ```
   Search for `Failed to load SOLVE-IT KB` in the output.

---

## Issue S2: Only `solveit_status` Appears in Tool List

**Symptom:** The tool list contains `solveit_status` and `__health_check` but none
of the other SOLVE-IT tools (`solveit_get_technique`, `solveit_search`, etc.).

**Cause:** The KnowledgeBase failed to load. `solveit_status` is registered
unconditionally; all other tools are skipped when `server._kb` is `None`.

**Fix:** Resolve the KB load failure first (see Issue S1 above). Once
`solveit_status` returns `{"status": "ok", ...}`, all tools will be present.

---

## Issue S3: `solveit_search` Returns No Results

**Symptom:** Calling `solveit_search` with expected keywords returns an empty list.

**Causes and fixes:**

1. **Strict sanitization strips search characters.** The `strict` security profile
   removes shell metacharacters, quotes, and some punctuation from string inputs
   before they reach the handler. If the search keywords contain these characters,
   they will be stripped before the search runs. Switch to `moderate` sanitization
   for search-heavy use:
   ```toml
   [security.input_sanitization]
   level = "moderate"
   ```

2. **`search_logic = "AND"` with multiple keywords is too restrictive.** The default
   is AND — all keywords must appear. Try OR logic:
   ```json
   {"keywords": "file system", "search_logic": "OR"}
   ```

3. **Word-boundary matching is filtering out partial matches.** The default
   `substring_match = false` requires whole-word matches. Set `substring_match = true`
   for partial matching.

---

## Issue S4: Tools Return `{"error": "not_found"}` for Valid IDs

**Symptom:** Calling `solveit_get_technique` with a known ID like `DFT-1001`
returns `{"error": "not_found", "id": "DFT-1001"}`.

**Causes and fixes:**

1. **ID case sensitivity.** IDs are case-sensitive. Ensure the ID matches exactly
   (e.g. `DFT-1001` not `dft-1000`).

2. **Wrong KB data version.** The technique may not exist in the version of the
   SOLVE-IT data currently loaded. Use `solveit_list_techniques` to see all available
   IDs.

3. **Strict sanitization modified the ID.** The `-` in IDs like `DFT-1001` is safe,
   but if an ID somehow contains shell metacharacters, strict sanitization may
   alter it. Check by temporarily switching to `moderate` sanitization.

---

## Issue S5: `solveit_status` Shows Wrong Item Counts

**Symptom:** The `techniques`, `weaknesses`, or `mitigations` counts in
`solveit_status` do not match what is expected for the current SOLVE-IT version.

**Causes and fixes:**

1. **Wrong data directory.** Verify `solveit_data_path` points to the correct
   SOLVE-IT version.

2. **Extensions not loading.** If `enable_extensions = true` but `extensions` is not
   in the `solveit_status` response, the SOLVE-IT-X extension data failed to load.
   Check logs for extension load errors at startup.

3. **Stale `__pycache__`.** Old cached `.pyc` files may prevent the latest KB code
   from loading:
   ```bash
   find /path/to/solve-it -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
   ```
   Then restart the server.

---

## Issue S6: Batch Helper `not_found_check` Doesn't Catch Your Sentinel

**Symptom:** You added a new tool using the batch helper (`register_simple_tools`)
with `not_found_check = True`, but the tool returns the raw empty result instead of
`{"error": "not_found", "id": "..."}` when an item is missing.

**Cause:** The batch helper's `not_found_check` only detects `None` as the
not-found sentinel. If your data source method returns `{}`, `[]`, or another
falsy value for missing items, the check won't trigger.

**Fix:** Use manual tool registration instead of the batch helper for tools whose
data source uses a non-`None` sentinel. See the relationship tools in
`solveit_tools.py` for an example of manual registration with custom ID validation.

---

## General Server Issues

---

## Issue 1: Server Starts But Client Receives No Response

**Symptom:** The MCP client connects but never receives a response to `initialize`.

**Causes and fixes:**

1. **Log output going to stdout.** MCP requires stdout to be reserved for JSON-RPC.
   Check that logging is configured to write to stderr only. The server does this
   by default. If you added custom logging, ensure it uses `logging.StreamHandler(sys.stderr)`.

2. **Extension crashing on import.** A bad extension can crash the server before
   it processes any messages. Run:
   ```bash
   python -m mcp_chassis --config config/default.toml --log-level DEBUG 2>&1 | head -50
   ```
   Look for `ERROR` lines about extension loading.

3. **Config file not found.** If the config path is wrong, the server exits silently.
   Check the exit code: `echo $?` after starting the server.

---

## Issue 2: Rate Limit Exceeded Immediately

**Symptom:** Tools return `RATE_LIMIT_EXCEEDED` on the first call.

**Causes and fixes:**

1. **Burst size is 0.** In `config/default.toml`, ensure `burst_size` is at least 1.
   The default is 10.

2. **Testing code reuses the same server instance.** The rate limiter is in-memory
   and per-server-instance. In tests, call `server._middleware._rate_limiter.reset()`
   between test cases, or create a fresh server per test.

3. **Rate limiting is overly strict for development.** Set `profile = "permissive"` in
   `config/default.toml` during development, or use the env var:
   ```bash
   MCP_RATE_LIMIT_ENABLED=false python -m mcp_chassis
   ```

---

## Issue 3: Input Validation Rejects Valid Arguments

**Symptom:** Tool calls fail with `VALIDATION_ERROR` even with correct arguments.

**Causes and fixes:**

1. **Schema mismatch.** The `input_schema` registered for the tool must match the
   arguments the client sends. Verify the schema:
   ```python
   print(server._tools["my_tool"]["input_schema"])
   ```

2. **String too long.** The default `max_string_length` is 10,000 characters. Increase
   it in config if needed:
   ```toml
   [security.input_validation]
   max_string_length = 100000
   ```

3. **Array too long.** Default `max_array_length` is 100. Adjust in config similarly.

4. **Object too deeply nested.** Default `max_object_depth` is 10. Adjust if your
   tool accepts deeply nested JSON structures.

5. **Disable validation for testing:**
   ```toml
   [security.input_validation]
   enabled = false
   ```

---

## Issue 4: Sanitization Strips Expected Characters

**Symptom:** Tool receives modified input — shell characters, slashes, or special
characters are removed.

**Causes and fixes:**

1. **Strict sanitization removes shell metacharacters.** The default `strict` profile
   strips `;`, `|`, `&`, `$`, backticks, and other shell-special characters.
   If your tool legitimately needs these, switch to `moderate` or `permissive`:
   ```toml
   [security.input_sanitization]
   level = "moderate"
   ```

2. **Path traversal sequences are stripped.** Sequences like `../` are removed in
   `strict` and `moderate` modes. If your tool works with file paths, consider
   implementing your own path validation after sanitization.

3. **Control characters are removed.** Newlines inside strings survive in `moderate`
   and `permissive` modes. Only `strict` mode removes them.

---

## Issue 5: Extension Not Being Discovered

**Symptom:** A new tool/resource/prompt is not appearing in the server's listings.

**Causes and fixes:**

1. **Missing `register()` function.** The extension file must define `def register(server)`.
   Check spelling — it must be exactly `register`.

2. **`auto_discover = false` in config.** Ensure auto-discovery is enabled:
   ```toml
   [extensions]
   auto_discover = true
   ```

3. **File named `__init__.py`.** Files named `__init__.py` are excluded from
   discovery. Rename your file.

4. **File in wrong directory.** Tools must go in `extensions/tools/`, resources
   in `extensions/resources/`, prompts in `extensions/prompts/`. Files in the
   `extensions/` root are NOT discovered.

5. **Syntax error in the extension file.** Run:
   ```bash
   python -c "import mcp_chassis.extensions.tools.solveit_tools"
   ```
   This will show the syntax error directly.

6. **Check logs for discovery errors:**
   ```bash
   python -m mcp_chassis --log-level DEBUG 2>&1 | grep extension
   ```

---

## Issue 6: Health Check Shows Wrong Tools/Resources/Prompts

**Symptom:** `__health_check` output lists unexpected tools or is missing expected ones.

**Causes and fixes:**

1. **Extensions loaded from a previous run cached in `__pycache__`.** Clear cache:
   ```bash
   find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
   ```

2. **Config has `auto_discover = false`** — extensions won't load. See Issue 5.

3. **Extension failed silently.** Check logs for `ERROR` messages during startup.

---

## Issue 7: Server Crashes on Startup with `FileNotFoundError`

**Symptom:** Server exits with a traceback mentioning a missing config file.

**Fix:** The config path must be absolute or relative to the current working directory.
When running from the repo root:
```bash
python -m mcp_chassis --config config/default.toml
```

From another directory, use an absolute path:
```bash
python -m mcp_chassis --config /path/to/repo/config/default.toml
```

Or set the env var:
```bash
MCP_CHASSIS_CONFIG=/path/to/config.toml python -m mcp_chassis
```

---

## Issue 8: Docker Container Exits Immediately

**Symptom:** `docker run` exits with code 0 or 1 without processing any messages.

**Causes and fixes:**

1. **No stdin attached.** MCP servers require an interactive stdin pipe. Use `-i`:
   ```bash
   docker run -i my-mcp-server
   ```

2. **Config file not found in container.** The default config is at `/app/config/default.toml`
   inside the container. Mount a custom config if needed:
   ```bash
   docker run -i -v $(pwd)/config/my-config.toml:/app/config/default.toml my-mcp-server
   ```

3. **Startup error.** Add `--log-level DEBUG` to see startup errors:
   ```bash
   docker run -i my-mcp-server --log-level DEBUG
   ```

---

## Issue 9: `ModuleNotFoundError` for `mcp_chassis`

**Symptom:** `python -m mcp_chassis` fails with `No module named mcp_chassis`.

**Fix:** The package is not installed. Install it in editable mode:
```bash
pip install -e ".[dev]"
```

Or non-editable:
```bash
pip install .
```

---

## Issue 10: `asyncio.TimeoutError` in Integration Tests

**Symptom:** Integration tests time out waiting for the server subprocess to respond.

**Causes and fixes:**

1. **Server not starting fast enough.** Increase the startup timeout in the test
   fixture. The default is 15 seconds.

2. **Server crashing on startup.** Run the server manually to see error output:
   ```bash
   python -m mcp_chassis --config config/default.toml --log-level DEBUG 2>&1
   ```

3. **Server writing debug logs to stdout.** If any code writes to `stdout` (e.g., a
   `print()` statement), the test client may misinterpret it as a JSON-RPC message.
   Search for `print(` in extension code and replace with `logging.getLogger().info(...)`.

4. **pytest-asyncio version mismatch.** Ensure `pytest-asyncio>=0.24.0` is installed
   and `asyncio_mode = "auto"` is set in `pyproject.toml`.

---

## Issue 11: `ValidationError` on Tool Call from MCP Client

**Symptom:** An MCP client (e.g., Claude Desktop) sends a tool call and receives a
validation error, but the arguments look correct.

**Causes and fixes:**

1. **Schema mismatch between client and server.** The MCP client caches the tool
   schema from `tools/list`. After changing a tool's schema, restart both the server
   and the client to clear the cache.

2. **Strict sanitization removing characters the schema allows.** For example, a
   `"pattern"` regex in the schema may reference characters that sanitization strips.
   Consider loosening the sanitization profile or removing the pattern constraint.

   Note: the validator enforces `enum` constraints (allowed values lists) but does
   **not** enforce `pattern` (regex) constraints. If you need pattern validation,
   implement it in your handler.

3. **Argument type mismatch.** Ensure the JSON type in `input_schema` matches what
   the client sends. `"type": "integer"` rejects `"42"` (string). Use `"type": "string"`
   and parse in the handler if needed.

---

## Issue 12: `KEY_COLLISION` Error on Tool or Prompt Call

**Symptom:** A tool or prompt call fails with `KEY_COLLISION` during sanitization.

**Cause:** Two distinct argument keys collide after sanitization strips characters.
For example, `"path../a"` and `"patha"` both become `"patha"` after path traversal
stripping. The server rejects the request to prevent silent data loss.

**Fixes:**

1. **Rename conflicting keys.** Choose argument names that don't contain characters
   stripped by sanitization (path traversal sequences, shell metacharacters, control
   characters). Plain alphanumeric names with underscores are always safe.

2. **Lower the sanitization level.** If your keys legitimately need special characters,
   use `moderate` or `permissive` sanitization:
   ```toml
   [security.input_sanitization]
   level = "moderate"
   ```

---

## Issue 13: Server Refuses to Start with Token Auth on Stdio

**Symptom:** Server raises `ValueError: Token auth is not supported on stdio transport`.

**Cause:** Token auth (`provider = "token"`) is not meaningful over stdio pipes —
there is no mechanism for a caller to present a token. The OS provides
process-level isolation instead.

**Fix:** Disable auth for stdio transport:
```toml
[security.auth]
enabled = false
provider = "none"
```

Token auth will be enforced when HTTP transport is implemented, where
the token will come from the HTTP `Authorization` header.

---

## Enabling Debug Logging

To see all server internals:
```bash
python -m mcp_chassis --log-level DEBUG 2>debug.log
```

The log is JSON-structured. Filter for specific loggers:
```bash
python -m mcp_chassis --log-level DEBUG 2>&1 | python -c "
import sys, json
for line in sys.stdin:
    try:
        r = json.loads(line)
        if 'extension' in r.get('logger', ''):
            print(line, end='')
    except:
        pass
"
```
