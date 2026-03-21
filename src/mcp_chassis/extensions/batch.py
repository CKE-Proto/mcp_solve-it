"""Batch tool registration helper for simple wrapper tools.

Reduces boilerplate when many tools follow the same pattern: call a method
on a shared object, return the result as JSON. Supports three patterns:

- **Get by ID**: one required param, method returns a value or None
  (None → ``{"error": "not_found", "id": ...}``)
- **List all**: no params, method returns a list/dict
- **Relationship query**: one required param, method returns a list

Complex tools (custom param mapping, multiple params, special logic)
should use the standard one-file-per-tool pattern instead.

Example usage in an extension file::

    from mcp_chassis.extensions.batch import register_simple_tools

    TOOLS = [
        {
            "name": "my_get_item",
            "description": "Get an item by ID.",
            "method": "get_item",
            "param": "item_id",
            "param_description": "The item ID.",
            "not_found_check": True,
        },
        {
            "name": "my_list_items",
            "description": "List all items.",
            "method": "list_items",
        },
    ]

    def register(server):
        source = server._my_shared_object
        if source is None:
            return
        register_simple_tools(server, source, TOOLS)
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mcp_chassis.context import HandlerContext
    from mcp_chassis.server import ChassisServer

logger = logging.getLogger(__name__)


def register_simple_tools(
    server: ChassisServer,
    source: Any,
    definitions: list[dict[str, Any]],
) -> None:
    """Register multiple tools from declarative definitions.

    Each definition is a dict with:
        name (str): Tool name.
        description (str): Tool description shown to LLM clients.
        method (str): Name of the method to call on ``source``.
        param (str, optional): Parameter name. If omitted, the tool takes no params.
        param_description (str, optional): Description for the parameter.
        not_found_check (bool, optional): If True and the method returns None,
            return ``{"error": "not_found", "id": <param_value>}`` instead.

    Args:
        server: The ChassisServer to register tools on.
        source: The object whose methods are called (e.g., a KnowledgeBase).
        definitions: List of tool definition dicts.
    """
    for defn in definitions:
        _register_one(server, source, defn)


def _register_one(
    server: ChassisServer,
    source: Any,
    defn: dict[str, Any],
) -> None:
    """Register a single tool from a definition dict."""
    name = defn["name"]
    description = defn["description"]
    method_name = defn["method"]
    param = defn.get("param")
    param_description = defn.get("param_description", "")
    not_found_check = defn.get("not_found_check", False)

    method = getattr(source, method_name)

    if param:
        # Tool with one required parameter
        input_schema: dict[str, Any] = {
            "type": "object",
            "properties": {
                param: {"type": "string", "description": param_description},
            },
            "required": [param],
        }

        async def _handle_with_param(
            arguments: dict[str, Any],
            context: HandlerContext,
            _method: Any = method,
            _param: str = param,
            _name: str = name,
            _not_found: bool = not_found_check,
        ) -> str:
            await context.log_debug(f"{_name} called")
            value = arguments[_param]
            result = _method(value)
            if _not_found and result is None:
                return json.dumps({"error": "not_found", "id": value})
            return json.dumps(result)

        server.register_tool(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=_handle_with_param,
        )
    else:
        # Tool with no parameters
        input_schema = {"type": "object", "properties": {}}

        async def _handle_no_param(
            arguments: dict[str, Any],
            context: HandlerContext,
            _method: Any = method,
            _name: str = name,
        ) -> str:
            await context.log_debug(f"{_name} called")
            result = _method()
            return json.dumps(result)

        server.register_tool(
            name=name,
            description=description,
            input_schema=input_schema,
            handler=_handle_no_param,
        )
