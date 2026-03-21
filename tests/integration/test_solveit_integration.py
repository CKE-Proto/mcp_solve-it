"""Integration tests for SOLVE-IT MCP tools.

These tests start the full MCP server as a subprocess and communicate
via JSON-RPC over stdio.
"""

from __future__ import annotations

import json

import pytest


@pytest.mark.asyncio
class TestSolveItTools:
    """Test SOLVE-IT tools via the full MCP protocol."""

    async def test_tools_list_includes_solveit(self, mcp_client) -> None:
        """tools/list should include SOLVE-IT tools."""
        response = await mcp_client.send_request("tools/list")
        assert "result" in response, f"Expected result, got: {response}"
        tool_names = [t["name"] for t in response["result"]["tools"]]
        assert "solveit_status" in tool_names
        assert "solveit_get_technique" in tool_names
        assert "solveit_search" in tool_names

    async def test_solveit_status(self, mcp_client) -> None:
        """solveit_status should return OK with item counts."""
        response = await mcp_client.send_request(
            "tools/call",
            {"name": "solveit_status", "arguments": {}},
        )
        assert "result" in response
        data = json.loads(response["result"]["content"][0]["text"])
        assert data["status"] == "ok"
        assert data["techniques"] > 0

    async def test_get_technique(self, mcp_client) -> None:
        """solveit_get_technique should return technique data."""
        response = await mcp_client.send_request(
            "tools/call",
            {"name": "solveit_get_technique", "arguments": {"technique_id": "DFT-1001"}},
        )
        assert "result" in response
        data = json.loads(response["result"]["content"][0]["text"])
        assert data["id"] == "DFT-1001"

    async def test_get_technique_not_found(self, mcp_client) -> None:
        """solveit_get_technique should return error for invalid ID."""
        response = await mcp_client.send_request(
            "tools/call",
            {"name": "solveit_get_technique", "arguments": {"technique_id": "DFT-9999"}},
        )
        assert "result" in response
        data = json.loads(response["result"]["content"][0]["text"])
        assert data["error"] == "not_found"

    async def test_list_techniques(self, mcp_client) -> None:
        """solveit_list_techniques should return id+name summaries."""
        response = await mcp_client.send_request(
            "tools/call",
            {"name": "solveit_list_techniques", "arguments": {}},
        )
        assert "result" in response
        data = json.loads(response["result"]["content"][0]["text"])
        assert isinstance(data, list)
        assert len(data) > 0
        assert "id" in data[0] and "name" in data[0]

    async def test_search(self, mcp_client) -> None:
        """solveit_search should return results grouped by type."""
        response = await mcp_client.send_request(
            "tools/call",
            {"name": "solveit_search", "arguments": {"keywords": "disk image"}},
        )
        assert "result" in response
        data = json.loads(response["result"]["content"][0]["text"])
        assert "techniques" in data
        assert "weaknesses" in data
        assert "mitigations" in data

    async def test_relationship_tool_valid(self, mcp_client) -> None:
        """Relationship tool should return list for valid ID."""
        response = await mcp_client.send_request(
            "tools/call",
            {
                "name": "solveit_get_weaknesses_for_technique",
                "arguments": {"technique_id": "DFT-1001"},
            },
        )
        assert "result" in response
        data = json.loads(response["result"]["content"][0]["text"])
        assert isinstance(data, list)

    async def test_relationship_tool_invalid_id(self, mcp_client) -> None:
        """Relationship tool should return not_found for invalid ID."""
        response = await mcp_client.send_request(
            "tools/call",
            {
                "name": "solveit_get_weaknesses_for_technique",
                "arguments": {"technique_id": "DFT-9999"},
            },
        )
        assert "result" in response
        data = json.loads(response["result"]["content"][0]["text"])
        assert data["error"] == "not_found"

    async def test_list_objectives(self, mcp_client) -> None:
        """solveit_list_objectives should return objective list."""
        response = await mcp_client.send_request(
            "tools/call",
            {"name": "solveit_list_objectives", "arguments": {}},
        )
        assert "result" in response
        data = json.loads(response["result"]["content"][0]["text"])
        assert isinstance(data, list)
        assert len(data) > 0

    async def test_full_detail_tools_not_listed_by_default(self, mcp_client) -> None:
        """Full-detail tools should not appear when disabled."""
        response = await mcp_client.send_request("tools/list")
        tool_names = [t["name"] for t in response["result"]["tools"]]
        assert "solveit_list_techniques_full_detail" not in tool_names

    async def test_list_loaded_extensions(self, mcp_client) -> None:
        """solveit_list_loaded_extensions should return a list."""
        response = await mcp_client.send_request(
            "tools/call",
            {"name": "solveit_list_loaded_extensions", "arguments": {}},
        )
        assert "result" in response
        data = json.loads(response["result"]["content"][0]["text"])
        assert isinstance(data, list)
