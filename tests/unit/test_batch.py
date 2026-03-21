"""Unit tests for mcp_chassis.extensions.batch module."""

from __future__ import annotations

import json
from typing import Any

import pytest

from mcp_chassis.server import ChassisServer
from tests.conftest import make_test_config


class FakeSource:
    """A fake object with methods that batch registration can call."""

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        if item_id == "FOUND-1":
            return {"id": "FOUND-1", "name": "Found Item"}
        return None

    def list_items(self) -> list[dict[str, str]]:
        return [{"id": "A-1", "name": "Alpha"}, {"id": "A-2", "name": "Beta"}]

    def get_related(self, item_id: str) -> list[dict[str, Any]]:
        if item_id == "FOUND-1":
            return [{"id": "R-1", "name": "Related"}]
        return []


class TestRegisterSimpleTools:
    """Tests for the batch register_simple_tools helper."""

    def test_registers_get_tool(self) -> None:
        """A get-by-id tool is registered and dispatches correctly."""
        from mcp_chassis.extensions.batch import register_simple_tools

        config = make_test_config()
        server = ChassisServer(config)
        source = FakeSource()

        register_simple_tools(server, source, [
            {
                "name": "test_get_item",
                "description": "Get an item by ID.",
                "method": "get_item",
                "param": "item_id",
                "param_description": "The item ID.",
                "not_found_check": True,
            },
        ])

        assert "test_get_item" in server.list_tool_names()

    @pytest.mark.asyncio
    async def test_get_tool_returns_found_item(self) -> None:
        from mcp_chassis.extensions.batch import register_simple_tools

        config = make_test_config()
        server = ChassisServer(config)
        source = FakeSource()

        register_simple_tools(server, source, [
            {
                "name": "test_get_item",
                "description": "Get an item.",
                "method": "get_item",
                "param": "item_id",
                "param_description": "The item ID.",
                "not_found_check": True,
            },
        ])

        result = await server._dispatch_tool("test_get_item", {"item_id": "FOUND-1"})
        assert not result.isError
        data = json.loads(result.content[0].text)
        assert data["id"] == "FOUND-1"

    @pytest.mark.asyncio
    async def test_get_tool_returns_not_found(self) -> None:
        from mcp_chassis.extensions.batch import register_simple_tools

        config = make_test_config()
        server = ChassisServer(config)
        source = FakeSource()

        register_simple_tools(server, source, [
            {
                "name": "test_get_item",
                "description": "Get an item.",
                "method": "get_item",
                "param": "item_id",
                "param_description": "The item ID.",
                "not_found_check": True,
            },
        ])

        result = await server._dispatch_tool("test_get_item", {"item_id": "MISSING"})
        data = json.loads(result.content[0].text)
        assert data["error"] == "not_found"

    @pytest.mark.asyncio
    async def test_list_tool_returns_results(self) -> None:
        from mcp_chassis.extensions.batch import register_simple_tools

        config = make_test_config()
        server = ChassisServer(config)
        source = FakeSource()

        register_simple_tools(server, source, [
            {
                "name": "test_list_items",
                "description": "List all items.",
                "method": "list_items",
            },
        ])

        result = await server._dispatch_tool("test_list_items", {})
        data = json.loads(result.content[0].text)
        assert isinstance(data, list)
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_relationship_tool_returns_list(self) -> None:
        from mcp_chassis.extensions.batch import register_simple_tools

        config = make_test_config()
        server = ChassisServer(config)
        source = FakeSource()

        register_simple_tools(server, source, [
            {
                "name": "test_get_related",
                "description": "Get related items.",
                "method": "get_related",
                "param": "item_id",
                "param_description": "The item ID.",
            },
        ])

        result = await server._dispatch_tool("test_get_related", {"item_id": "FOUND-1"})
        data = json.loads(result.content[0].text)
        assert isinstance(data, list)
        assert len(data) == 1

    def test_multiple_tools_registered(self) -> None:
        from mcp_chassis.extensions.batch import register_simple_tools

        config = make_test_config()
        server = ChassisServer(config)
        source = FakeSource()

        register_simple_tools(server, source, [
            {"name": "tool_a", "description": "A.", "method": "list_items"},
            {"name": "tool_b", "description": "B.", "method": "list_items"},
            {"name": "tool_c", "description": "C.", "method": "get_item",
             "param": "item_id", "param_description": "ID.", "not_found_check": True},
        ])

        names = server.list_tool_names()
        assert "tool_a" in names
        assert "tool_b" in names
        assert "tool_c" in names
