"""Structural integration tests for the MCP Chassis server over stdio transport.

Tests the MCP protocol lifecycle (initialize, tools/list, tools/call, etc.)
without depending on any specific extension. These tests work regardless of
which extensions are loaded — they verify protocol behavior, not extension logic.

Extension-specific integration tests (for the bundled examples) live in
test_stdio_examples.py and are auto-skipped when the examples are removed.
"""

from __future__ import annotations

import json

import pytest

from .conftest import MCPTestClient


class TestInitialize:
    """Tests for the MCP initialize handshake."""

    @pytest.mark.asyncio
    async def test_initialize_returns_result(self, mcp_client: MCPTestClient) -> None:
        """Verify the fixture itself completes initialize successfully."""
        # The fixture already did initialize; just verify the client is alive
        response = await mcp_client.send_request("tools/list")
        assert "result" in response


class TestToolsList:
    """Tests for tools/list endpoint."""

    @pytest.mark.asyncio
    async def test_tools_list_returns_list(self, mcp_client: MCPTestClient) -> None:
        """tools/list should return a list of tools."""
        response = await mcp_client.send_request("tools/list")
        assert "result" in response, f"Expected result, got: {response}"
        tools = response["result"]["tools"]
        assert isinstance(tools, list)

    @pytest.mark.asyncio
    async def test_tools_list_contains_health_check(self, mcp_client: MCPTestClient) -> None:
        """tools/list should include the built-in __health_check tool."""
        response = await mcp_client.send_request("tools/list")
        tools = response["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        assert "__health_check" in tool_names

    @pytest.mark.asyncio
    async def test_tools_list_tool_has_required_fields(self, mcp_client: MCPTestClient) -> None:
        """Each tool in the list should have name, description, and inputSchema."""
        response = await mcp_client.send_request("tools/list")
        tools = response["result"]["tools"]
        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "inputSchema" in tool


class TestToolsCall:
    """Tests for tools/call endpoint."""

    @pytest.mark.asyncio
    async def test_call_health_check(self, mcp_client: MCPTestClient) -> None:
        """Calling __health_check should return valid JSON with expected fields."""
        response = await mcp_client.send_request(
            "tools/call",
            {"name": "__health_check", "arguments": {}},
        )
        assert "result" in response, f"Expected result, got: {response}"
        result = response["result"]
        assert result.get("isError") is not True
        content = result["content"]
        assert len(content) > 0
        data = json.loads(content[0]["text"])
        assert "server_name" in data
        assert "server_version" in data
        assert "tools_loaded" in data
        assert "uptime_seconds" in data
        assert "security_profile" in data

    @pytest.mark.asyncio
    async def test_call_health_check_shows_loaded_tools(self, mcp_client: MCPTestClient) -> None:
        """Health check should list __health_check in tools_loaded."""
        response = await mcp_client.send_request(
            "tools/call",
            {"name": "__health_check", "arguments": {}},
        )
        data = json.loads(response["result"]["content"][0]["text"])
        tool_names = data["tools_loaded"]
        assert "__health_check" in tool_names

    @pytest.mark.asyncio
    async def test_call_nonexistent_tool(self, mcp_client: MCPTestClient) -> None:
        """Calling a nonexistent tool should return an error result."""
        response = await mcp_client.send_request(
            "tools/call",
            {"name": "does_not_exist", "arguments": {}},
        )
        assert "result" in response, f"Expected result, got: {response}"
        result = response["result"]
        assert result.get("isError") is True
        text = result["content"][0]["text"]
        assert "TOOL_NOT_FOUND" in text or "does_not_exist" in text


class TestResourcesList:
    """Tests for resources/list endpoint."""

    @pytest.mark.asyncio
    async def test_resources_list_returns_list(self, mcp_client: MCPTestClient) -> None:
        """resources/list should return a list of resources."""
        response = await mcp_client.send_request("resources/list")
        assert "result" in response, f"Expected result, got: {response}"
        resources = response["result"]["resources"]
        assert isinstance(resources, list)

    @pytest.mark.asyncio
    async def test_resources_list_resource_has_required_fields(
        self, mcp_client: MCPTestClient
    ) -> None:
        """Each resource should have uri and name fields."""
        response = await mcp_client.send_request("resources/list")
        resources = response["result"]["resources"]
        for resource in resources:
            assert "uri" in resource
            assert "name" in resource


class TestPromptsList:
    """Tests for prompts/list endpoint."""

    @pytest.mark.asyncio
    async def test_prompts_list_returns_list(self, mcp_client: MCPTestClient) -> None:
        """prompts/list should return a list of prompts."""
        response = await mcp_client.send_request("prompts/list")
        assert "result" in response, f"Expected result, got: {response}"
        prompts = response["result"]["prompts"]
        assert isinstance(prompts, list)

    @pytest.mark.asyncio
    async def test_prompts_list_prompt_has_required_fields(
        self, mcp_client: MCPTestClient
    ) -> None:
        """Each prompt should have name and optionally description and arguments."""
        response = await mcp_client.send_request("prompts/list")
        prompts = response["result"]["prompts"]
        for prompt in prompts:
            assert "name" in prompt


class TestPromptsGet:
    """Tests for prompts/get endpoint."""

    @pytest.mark.asyncio
    async def test_get_prompt_returns_error_for_unknown_prompt(
        self, mcp_client: MCPTestClient
    ) -> None:
        """Getting a nonexistent prompt should return a JSON-RPC error."""
        response = await mcp_client.send_request(
            "prompts/get",
            {"name": "nonexistent_prompt", "arguments": {}},
        )
        # Either an error field or isError in result
        has_error = "error" in response or (
            "result" in response and response["result"].get("isError")
        )
        assert has_error, f"Expected error response, got: {response}"
