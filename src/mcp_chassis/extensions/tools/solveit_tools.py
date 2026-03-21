"""SOLVE-IT MCP tool extensions.

Registers tools that expose the SOLVE-IT knowledge base to LLM clients.
Requires the init hook (``solveit_init.py``) to have loaded the
KnowledgeBase onto ``server._kb`` before this module's ``register()``
runs.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from mcp_chassis.extensions.batch import register_simple_tools

if TYPE_CHECKING:
    from mcp_chassis.context import HandlerContext
    from mcp_chassis.server import ChassisServer

logger = logging.getLogger(__name__)


def _register_status_tool(server: ChassisServer) -> None:
    """Register solveit_status — always available, even if KB failed."""
    kb = getattr(server, "_kb", None)
    kb_error = getattr(server, "_kb_error", None)

    async def _handle(
        arguments: dict[str, Any], context: HandlerContext
    ) -> str:
        await context.log_debug("solveit_status called")
        if kb is None:
            return json.dumps({
                "status": "error",
                "error": kb_error or "Knowledge base not loaded",
            })
        report: dict[str, Any] = {
            "status": "ok",
            "techniques": len(kb.list_techniques()),
            "weaknesses": len(kb.list_weaknesses()),
            "mitigations": len(kb.list_mitigations()),
            "citations": len(kb.citations),
        }
        if kb.has_extensions():
            report["extensions"] = kb.list_loaded_extensions()
        return json.dumps(report)

    server.register_tool(
        name="solveit_status",
        description=(
            "SOLVE-IT knowledge base status. Returns item counts (techniques, "
            "weaknesses, mitigations, citations) and loaded extensions when "
            "healthy, or error details if the KB failed to load."
        ),
        input_schema={"type": "object", "properties": {}},
        handler=_handle,
    )


_BATCH_TOOLS: list[dict[str, Any]] = [
    {
        "name": "solveit_get_technique",
        "description": "Get full details of a SOLVE-IT technique by its ID (e.g. DFT-1001).",
        "method": "get_technique",
        "param": "technique_id",
        "param_description": "The technique ID (e.g. DFT-1001).",
        "not_found_check": True,
    },
    {
        "name": "solveit_get_weakness",
        "description": "Get full details of a SOLVE-IT weakness by its ID (e.g. DFW-1001).",
        "method": "get_weakness",
        "param": "weakness_id",
        "param_description": "The weakness ID (e.g. DFW-1001).",
        "not_found_check": True,
    },
    {
        "name": "solveit_get_mitigation",
        "description": "Get full details of a SOLVE-IT mitigation by its ID (e.g. DFM-1001).",
        "method": "get_mitigation",
        "param": "mitigation_id",
        "param_description": "The mitigation ID (e.g. DFM-1001).",
        "not_found_check": True,
    },
    {
        "name": "solveit_list_techniques",
        "description": "List all SOLVE-IT techniques (ID and name only).",
        "method": "get_all_techniques_with_name_and_id",
    },
    {
        "name": "solveit_list_weaknesses",
        "description": "List all SOLVE-IT weaknesses (ID and name only).",
        "method": "get_all_weaknesses_with_name_and_id",
    },
    {
        "name": "solveit_list_mitigations",
        "description": "List all SOLVE-IT mitigations (ID and name only).",
        "method": "get_all_mitigations_with_name_and_id",
    },
    {
        "name": "solveit_list_objectives",
        "description": "List all objectives in the current SOLVE-IT mapping.",
        "method": "list_objectives",
    },
    {
        "name": "solveit_get_techniques_for_objective",
        "description": "Get all techniques associated with a given objective name.",
        "method": "get_techniques_for_objective",
        "param": "objective_name",
        "param_description": "The objective name (e.g. 'Acquire data').",
    },
]


_RELATIONSHIP_TOOLS: list[dict[str, Any]] = [
    {
        "tool_name": "solveit_get_weaknesses_for_technique",
        "description": "Get all weaknesses associated with a given technique.",
        "lookup_method": "get_technique",
        "relation_method": "get_weaknesses_for_technique",
        "param_name": "technique_id",
        "param_description": "The technique ID (e.g. DFT-1001).",
    },
    {
        "tool_name": "solveit_get_mitigations_for_weakness",
        "description": "Get all mitigations that address a given weakness.",
        "lookup_method": "get_weakness",
        "relation_method": "get_mitigations_for_weakness",
        "param_name": "weakness_id",
        "param_description": "The weakness ID (e.g. DFW-1001).",
    },
    {
        "tool_name": "solveit_get_techniques_for_weakness",
        "description": "Get all techniques that can exhibit a given weakness.",
        "lookup_method": "get_weakness",
        "relation_method": "get_techniques_for_weakness",
        "param_name": "weakness_id",
        "param_description": "The weakness ID (e.g. DFW-1001).",
    },
    {
        "tool_name": "solveit_get_weaknesses_for_mitigation",
        "description": "Get all weaknesses that a given mitigation addresses.",
        "lookup_method": "get_mitigation",
        "relation_method": "get_weaknesses_for_mitigation",
        "param_name": "mitigation_id",
        "param_description": "The mitigation ID (e.g. DFM-1001).",
    },
    {
        "tool_name": "solveit_get_techniques_for_mitigation",
        "description": "Get all techniques reachable from a given mitigation.",
        "lookup_method": "get_mitigation",
        "relation_method": "get_techniques_for_mitigation",
        "param_name": "mitigation_id",
        "param_description": "The mitigation ID (e.g. DFM-1001).",
    },
]


def _register_relationship_tools(server: ChassisServer, kb: Any) -> None:
    """Register relationship tools with ID validation.

    Args:
        server: The ChassisServer to register tools on.
        kb: The KnowledgeBase instance providing lookup and relation methods.
    """
    for defn in _RELATIONSHIP_TOOLS:
        tool_name = defn["tool_name"]
        description = defn["description"]
        lookup = getattr(kb, defn["lookup_method"])
        relation = getattr(kb, defn["relation_method"])
        param_name = defn["param_name"]
        param_description = defn["param_description"]

        async def _handle(
            arguments: dict[str, Any],
            context: HandlerContext,
            _tool_name: str = tool_name,
            _lookup: Any = lookup,
            _relation: Any = relation,
            _param: str = param_name,
        ) -> str:
            await context.log_debug(f"{_tool_name} called")
            item_id = arguments[_param]
            if _lookup(item_id) is None:
                return json.dumps({"error": "not_found", "id": item_id})
            return json.dumps(_relation(item_id))

        server.register_tool(
            name=tool_name,
            description=description,
            input_schema={
                "type": "object",
                "properties": {
                    param_name: {
                        "type": "string",
                        "description": param_description,
                    },
                },
                "required": [param_name],
            },
            handler=_handle,
        )


_VALID_SEARCH_LOGIC = {"AND", "OR"}


def _register_search_tool(server: ChassisServer, kb: Any) -> None:
    """Register solveit_search with schema based on [app.search] config.

    Args:
        server: The ChassisServer to register tools on.
        kb: The KnowledgeBase instance providing the search method.
    """
    app_cfg = getattr(server, "_app_config", None)
    if app_cfg is not None:
        search_config = {
            "enable_item_types_filter": app_cfg.search.enable_item_types_filter,
            "enable_substring_match": app_cfg.search.enable_substring_match,
            "enable_search_logic": app_cfg.search.enable_search_logic,
        }
    else:
        search_config = server._config.app.get("search", {})

    properties: dict[str, Any] = {
        "keywords": {
            "type": "string",
            "description": "Search terms. Use quotes for exact phrases.",
        },
    }
    required = ["keywords"]

    if search_config.get("enable_item_types_filter", True):
        properties["item_types"] = {
            "type": "array",
            "items": {
                "type": "string",
                "enum": ["techniques", "weaknesses", "mitigations"],
            },
            "description": (
                "Filter results to specific types. "
                "Default: all types are searched."
            ),
        }

    if search_config.get("enable_substring_match", True):
        properties["substring_match"] = {
            "type": "boolean",
            "description": (
                "If true, allow partial word matches. Default: false "
                "(word-boundary matching)."
            ),
        }

    if search_config.get("enable_search_logic", True):
        properties["search_logic"] = {
            "type": "string",
            "enum": ["AND", "OR"],
            "description": (
                "How to combine multiple keywords. "
                "AND = all must match, OR = any can match. Default: AND."
            ),
        }

    async def _handle(
        arguments: dict[str, Any], context: HandlerContext
    ) -> str:
        await context.log_debug("solveit_search called")
        keywords = arguments["keywords"]
        item_types = arguments.get("item_types")
        substring_match = arguments.get("substring_match", False)
        search_logic = arguments.get("search_logic", "AND")

        if search_logic not in _VALID_SEARCH_LOGIC:
            return json.dumps({
                "error": f"Invalid search_logic '{search_logic}'. Must be AND or OR.",
            })

        result = kb.search(
            keywords=keywords,
            item_types=item_types,
            substring_match=substring_match,
            search_logic=search_logic,
        )
        return json.dumps(result)

    server.register_tool(
        name="solveit_search",
        description=(
            "Search the SOLVE-IT knowledge base by keywords. Returns matching "
            "techniques, weaknesses, and mitigations sorted by relevance."
        ),
        input_schema={
            "type": "object",
            "properties": properties,
            "required": required,
        },
        handler=_handle,
    )


_FULL_DETAIL_WARNING = (
    "WARNING: Returns the complete dataset which may be very large "
    "(estimated 25,000-32,000 tokens). Use the summary listing tool "
    "instead unless you specifically need full detail for all items."
)

_FULL_DETAIL_TOOLS: list[dict[str, str]] = [
    {
        "name": "solveit_list_techniques_full_detail",
        "description": f"List ALL techniques with full detail. {_FULL_DETAIL_WARNING}",
        "method": "get_all_techniques_with_full_detail",
    },
    {
        "name": "solveit_list_weaknesses_full_detail",
        "description": f"List ALL weaknesses with full detail. {_FULL_DETAIL_WARNING}",
        "method": "get_all_weaknesses_with_full_detail",
    },
    {
        "name": "solveit_list_mitigations_full_detail",
        "description": f"List ALL mitigations with full detail. {_FULL_DETAIL_WARNING}",
        "method": "get_all_mitigations_with_full_detail",
    },
]


def _register_full_detail_tools(server: ChassisServer, kb: Any) -> None:
    """Register full-detail listing tools (config-gated).

    Args:
        server: The ChassisServer to register tools on.
        kb: The KnowledgeBase instance providing full-detail methods.
    """
    for defn in _FULL_DETAIL_TOOLS:
        tool_name = defn["name"]
        method = getattr(kb, defn["method"])

        async def _handle(
            arguments: dict[str, Any],
            context: HandlerContext,
            _name: str = tool_name,
            _method: Any = method,
        ) -> str:
            await context.log_debug(f"{_name} called")
            return json.dumps(_method())

        server.register_tool(
            name=tool_name,
            description=defn["description"],
            input_schema={"type": "object", "properties": {}},
            handler=_handle,
        )


def _register_extension_info_tool(server: ChassisServer, kb: Any) -> None:
    """Register the solveit_list_loaded_extensions tool.

    Args:
        server: The ChassisServer to register tools on.
        kb: The KnowledgeBase instance providing extension info.
    """
    async def _handle(
        arguments: dict[str, Any], context: HandlerContext
    ) -> str:
        await context.log_debug("solveit_list_loaded_extensions called")
        return json.dumps(kb.list_loaded_extensions())

    server.register_tool(
        name="solveit_list_loaded_extensions",
        description="List all loaded SOLVE-IT-X extensions and their details.",
        input_schema={"type": "object", "properties": {}},
        handler=_handle,
    )


def _register_citation_tools(server: ChassisServer, kb: Any) -> None:
    """Register citation lookup and listing tools.

    Args:
        server: The ChassisServer to register tools on.
        kb: The KnowledgeBase instance providing citation data.
    """
    async def _handle_get(
        arguments: dict[str, Any], context: HandlerContext
    ) -> str:
        await context.log_debug("solveit_get_citation called")
        citation_id = arguments["citation_id"]
        citation = kb.get_citation(citation_id)
        if citation is None:
            return json.dumps({"error": "not_found", "id": citation_id})
        return json.dumps({**citation, "id": citation_id})

    server.register_tool(
        name="solveit_get_citation",
        description=(
            "Get a SOLVE-IT citation by its DFCite ID (e.g. DFCite-1001). "
            "Returns bibtex and/or plaintext content."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "citation_id": {
                    "type": "string",
                    "description": "The citation ID (e.g. DFCite-1001).",
                },
            },
            "required": ["citation_id"],
        },
        handler=_handle_get,
    )

    async def _handle_list(
        arguments: dict[str, Any], context: HandlerContext
    ) -> str:
        await context.log_debug("solveit_list_citations called")
        return json.dumps([{"id": cid} for cid in sorted(kb.citations)])

    server.register_tool(
        name="solveit_list_citations",
        description="List all citation IDs in the SOLVE-IT knowledge base.",
        input_schema={"type": "object", "properties": {}},
        handler=_handle_list,
    )


def register(server: ChassisServer) -> None:
    """Register all SOLVE-IT tools.

    Args:
        server: The ChassisServer instance with ``_kb`` and ``_kb_error``
            attributes set by the init hook.
    """
    _register_status_tool(server)

    kb = getattr(server, "_kb", None)
    if kb is None:
        logger.warning("SOLVE-IT KB not loaded — only solveit_status registered")
        return

    app_cfg = getattr(server, "_app_config", None)

    # Batch-registered tools (8)
    register_simple_tools(server, kb, _BATCH_TOOLS)

    # Relationship tools (5)
    _register_relationship_tools(server, kb)

    # Search tool (1)
    _register_search_tool(server, kb)

    # Full-detail tools (config-gated)
    enable_full_detail = (
        app_cfg.enable_full_detail_tools if app_cfg is not None
        else server._config.app.get("enable_full_detail_tools", False)
    )
    if enable_full_detail:
        _register_full_detail_tools(server, kb)

    # Extension info tool (1)
    _register_extension_info_tool(server, kb)

    # Citation tools (2)
    _register_citation_tools(server, kb)
