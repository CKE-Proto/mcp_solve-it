"""Tests for SOLVE-IT tool registrations."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from mcp_chassis.config import ServerConfig
from mcp_chassis.context import HandlerContext
from mcp_chassis.extensions.solveit_init import SolveItAppConfig

_SOLVEIT_PATH = str(
    (Path(__file__).resolve().parents[3] / "solve-it" / "solve-it-main").resolve()
)


def _make_context() -> HandlerContext:
    return HandlerContext(
        request_id="test-req",
        correlation_id="test-corr",
        server_config=ServerConfig(),
    )


def _make_server(
    app_config: dict | None = None,
    kb: Any = None,
    kb_error: str | None = None,
) -> MagicMock:
    server = MagicMock()
    server._config = MagicMock()
    raw_app = app_config or {}
    server._config.app = raw_app
    server._app_config = SolveItAppConfig.from_raw(raw_app)
    server._kb = kb
    server._kb_error = kb_error
    server._registered_tools = {}

    def mock_register_tool(name, description, input_schema, handler, **kwargs):
        server._registered_tools[name] = {
            "description": description,
            "input_schema": input_schema,
            "handler": handler,
        }

    server.register_tool = mock_register_tool
    return server


def _load_kb():
    if _SOLVEIT_PATH not in sys.path:
        sys.path.insert(0, _SOLVEIT_PATH)
    from solve_it_library import KnowledgeBase
    return KnowledgeBase(base_path=_SOLVEIT_PATH)


class TestStatusToolRegistration:
    def test_status_registered_when_kb_loaded(self) -> None:
        from mcp_chassis.extensions.tools.solveit_tools import register
        kb = _load_kb()
        server = _make_server(kb=kb)
        register(server)
        assert "solveit_status" in server._registered_tools

    def test_status_registered_when_kb_failed(self) -> None:
        from mcp_chassis.extensions.tools.solveit_tools import register
        server = _make_server(kb=None, kb_error="Test error")
        register(server)
        assert "solveit_status" in server._registered_tools

    @pytest.mark.asyncio
    async def test_status_returns_ok_when_kb_loaded(self) -> None:
        from mcp_chassis.extensions.tools.solveit_tools import register
        kb = _load_kb()
        server = _make_server(kb=kb)
        register(server)
        handler = server._registered_tools["solveit_status"]["handler"]
        result = json.loads(await handler({}, _make_context()))
        assert result["status"] == "ok"
        assert result["techniques"] > 0
        assert result["weaknesses"] > 0
        assert result["mitigations"] > 0
        assert result["citations"] > 0

    @pytest.mark.asyncio
    async def test_status_returns_error_when_kb_failed(self) -> None:
        from mcp_chassis.extensions.tools.solveit_tools import register
        server = _make_server(kb=None, kb_error="Path not found")
        register(server)
        handler = server._registered_tools["solveit_status"]["handler"]
        result = json.loads(await handler({}, _make_context()))
        assert result["status"] == "error"
        assert "Path not found" in result["error"]


class TestBatchToolRegistration:
    @pytest.fixture()
    def server_with_kb(self) -> MagicMock:
        from mcp_chassis.extensions.tools.solveit_tools import register
        kb = _load_kb()
        server = _make_server(kb=kb)
        register(server)
        return server

    @pytest.mark.parametrize("tool_name", [
        "solveit_get_technique",
        "solveit_get_weakness",
        "solveit_get_mitigation",
        "solveit_list_techniques",
        "solveit_list_weaknesses",
        "solveit_list_mitigations",
        "solveit_list_objectives",
        "solveit_get_techniques_for_objective",
    ])
    def test_batch_tool_registered(self, server_with_kb: MagicMock, tool_name: str) -> None:
        assert tool_name in server_with_kb._registered_tools

    @pytest.mark.asyncio
    async def test_get_technique_returns_data(self, server_with_kb: MagicMock) -> None:
        handler = server_with_kb._registered_tools["solveit_get_technique"]["handler"]
        result = json.loads(await handler({"technique_id": "DFT-1001"}, _make_context()))
        assert result["id"] == "DFT-1001"
        assert "name" in result
        assert isinstance(result["references"], list)

    @pytest.mark.asyncio
    async def test_get_technique_not_found(self, server_with_kb: MagicMock) -> None:
        handler = server_with_kb._registered_tools["solveit_get_technique"]["handler"]
        result = json.loads(await handler({"technique_id": "DFT-9999"}, _make_context()))
        assert result["error"] == "not_found"

    @pytest.mark.asyncio
    async def test_list_techniques_returns_list(self, server_with_kb: MagicMock) -> None:
        handler = server_with_kb._registered_tools["solveit_list_techniques"]["handler"]
        result = json.loads(await handler({}, _make_context()))
        assert isinstance(result, list)
        assert len(result) > 0
        assert "id" in result[0]
        assert "name" in result[0]

    @pytest.mark.asyncio
    async def test_list_objectives_returns_list(self, server_with_kb: MagicMock) -> None:
        handler = server_with_kb._registered_tools["solveit_list_objectives"]["handler"]
        result = json.loads(await handler({}, _make_context()))
        assert isinstance(result, list)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_get_weakness_returns_data(self, server_with_kb: MagicMock) -> None:
        handler = server_with_kb._registered_tools["solveit_get_weakness"]["handler"]
        result = json.loads(await handler({"weakness_id": "DFW-1001"}, _make_context()))
        assert result["id"] == "DFW-1001"
        assert "name" in result
        assert isinstance(result["categories"], list)
        assert isinstance(result["references"], list)

    @pytest.mark.asyncio
    async def test_get_weakness_categories_contain_valid_astm_codes(self, server_with_kb: MagicMock) -> None:
        handler = server_with_kb._registered_tools["solveit_get_weakness"]["handler"]
        result = json.loads(await handler({"weakness_id": "DFW-1003"}, _make_context()))
        assert len(result["categories"]) > 0
        assert all(cat.startswith("ASTM_") for cat in result["categories"])


class TestRelationshipTools:
    @pytest.fixture()
    def server_with_kb(self) -> MagicMock:
        from mcp_chassis.extensions.tools.solveit_tools import register
        kb = _load_kb()
        server = _make_server(kb=kb)
        register(server)
        return server

    @pytest.mark.parametrize("tool_name", [
        "solveit_get_weaknesses_for_technique",
        "solveit_get_mitigations_for_weakness",
        "solveit_get_techniques_for_weakness",
        "solveit_get_weaknesses_for_mitigation",
        "solveit_get_techniques_for_mitigation",
    ])
    def test_relationship_tool_registered(self, server_with_kb: MagicMock, tool_name: str) -> None:
        assert tool_name in server_with_kb._registered_tools

    @pytest.mark.asyncio
    async def test_weaknesses_for_technique_valid_id(self, server_with_kb: MagicMock) -> None:
        handler = server_with_kb._registered_tools["solveit_get_weaknesses_for_technique"]["handler"]
        result = json.loads(await handler({"technique_id": "DFT-1001"}, _make_context()))
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_weaknesses_for_technique_invalid_id(self, server_with_kb: MagicMock) -> None:
        handler = server_with_kb._registered_tools["solveit_get_weaknesses_for_technique"]["handler"]
        result = json.loads(await handler({"technique_id": "DFT-9999"}, _make_context()))
        assert result["error"] == "not_found"
        assert result["id"] == "DFT-9999"

    @pytest.mark.asyncio
    async def test_mitigations_for_weakness_valid_id(self, server_with_kb: MagicMock) -> None:
        handler = server_with_kb._registered_tools["solveit_get_mitigations_for_weakness"]["handler"]
        result = json.loads(await handler({"weakness_id": "DFW-1001"}, _make_context()))
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_techniques_for_weakness_invalid_id(self, server_with_kb: MagicMock) -> None:
        handler = server_with_kb._registered_tools["solveit_get_techniques_for_weakness"]["handler"]
        result = json.loads(await handler({"weakness_id": "DFW-9999"}, _make_context()))
        assert result["error"] == "not_found"

    @pytest.mark.asyncio
    async def test_weaknesses_for_mitigation_invalid_id(self, server_with_kb: MagicMock) -> None:
        handler = server_with_kb._registered_tools["solveit_get_weaknesses_for_mitigation"]["handler"]
        result = json.loads(await handler({"mitigation_id": "DFM-9999"}, _make_context()))
        assert result["error"] == "not_found"

    @pytest.mark.asyncio
    async def test_techniques_for_mitigation_invalid_id(self, server_with_kb: MagicMock) -> None:
        handler = server_with_kb._registered_tools["solveit_get_techniques_for_mitigation"]["handler"]
        result = json.loads(await handler({"mitigation_id": "DFM-9999"}, _make_context()))
        assert result["error"] == "not_found"


class TestSearchTool:
    def test_search_registered(self) -> None:
        from mcp_chassis.extensions.tools.solveit_tools import register
        kb = _load_kb()
        server = _make_server(kb=kb)
        register(server)
        assert "solveit_search" in server._registered_tools

    @pytest.mark.asyncio
    async def test_search_returns_results(self) -> None:
        from mcp_chassis.extensions.tools.solveit_tools import register
        kb = _load_kb()
        server = _make_server(kb=kb)
        register(server)
        handler = server._registered_tools["solveit_search"]["handler"]
        result = json.loads(await handler({"keywords": "disk image"}, _make_context()))
        assert "techniques" in result
        assert "weaknesses" in result
        assert "mitigations" in result

    @pytest.mark.asyncio
    async def test_search_empty_results(self) -> None:
        from mcp_chassis.extensions.tools.solveit_tools import register
        kb = _load_kb()
        server = _make_server(kb=kb)
        register(server)
        handler = server._registered_tools["solveit_search"]["handler"]
        result = json.loads(await handler({"keywords": "xyznonexistent123"}, _make_context()))
        assert result["techniques"] == []
        assert result["weaknesses"] == []
        assert result["mitigations"] == []

    def test_search_schema_includes_all_params_by_default(self) -> None:
        from mcp_chassis.extensions.tools.solveit_tools import register
        kb = _load_kb()
        search_config = {
            "enable_item_types_filter": True,
            "enable_substring_match": True,
            "enable_search_logic": True,
        }
        server = _make_server(app_config={"search": search_config}, kb=kb)
        register(server)
        schema = server._registered_tools["solveit_search"]["input_schema"]
        props = schema["properties"]
        assert "keywords" in props
        assert "item_types" in props
        assert "substring_match" in props
        assert "search_logic" in props

    def test_search_schema_excludes_disabled_params(self) -> None:
        from mcp_chassis.extensions.tools.solveit_tools import register
        kb = _load_kb()
        search_config = {
            "enable_item_types_filter": False,
            "enable_substring_match": False,
            "enable_search_logic": False,
        }
        server = _make_server(app_config={"search": search_config}, kb=kb)
        register(server)
        schema = server._registered_tools["solveit_search"]["input_schema"]
        props = schema["properties"]
        assert "keywords" in props
        assert "item_types" not in props
        assert "substring_match" not in props
        assert "search_logic" not in props

    @pytest.mark.asyncio
    async def test_search_invalid_search_logic(self) -> None:
        from mcp_chassis.extensions.tools.solveit_tools import register
        kb = _load_kb()
        search_config = {"enable_search_logic": True}
        server = _make_server(app_config={"search": search_config}, kb=kb)
        register(server)
        handler = server._registered_tools["solveit_search"]["handler"]
        result = json.loads(await handler({"keywords": "test", "search_logic": "INVALID"}, _make_context()))
        assert "error" in result


class TestFullDetailTools:
    def test_full_detail_tools_disabled_by_default(self) -> None:
        from mcp_chassis.extensions.tools.solveit_tools import register
        kb = _load_kb()
        server = _make_server(kb=kb)
        register(server)
        assert "solveit_list_techniques_full_detail" not in server._registered_tools

    def test_full_detail_tools_enabled(self) -> None:
        from mcp_chassis.extensions.tools.solveit_tools import register
        kb = _load_kb()
        server = _make_server(app_config={"enable_full_detail_tools": True}, kb=kb)
        register(server)
        assert "solveit_list_techniques_full_detail" in server._registered_tools
        assert "solveit_list_weaknesses_full_detail" in server._registered_tools
        assert "solveit_list_mitigations_full_detail" in server._registered_tools

    def test_full_detail_description_contains_warning(self) -> None:
        from mcp_chassis.extensions.tools.solveit_tools import register
        kb = _load_kb()
        server = _make_server(app_config={"enable_full_detail_tools": True}, kb=kb)
        register(server)
        desc = server._registered_tools["solveit_list_techniques_full_detail"]["description"]
        assert "WARNING" in desc

    @pytest.mark.asyncio
    async def test_full_detail_returns_data(self) -> None:
        from mcp_chassis.extensions.tools.solveit_tools import register
        kb = _load_kb()
        server = _make_server(app_config={"enable_full_detail_tools": True}, kb=kb)
        register(server)
        handler = server._registered_tools["solveit_list_techniques_full_detail"]["handler"]
        result = json.loads(await handler({}, _make_context()))
        assert isinstance(result, list)
        assert len(result) > 0
        assert "description" in result[0]


class TestExtensionInfoTool:
    def test_extension_tool_registered(self) -> None:
        from mcp_chassis.extensions.tools.solveit_tools import register
        kb = _load_kb()
        server = _make_server(kb=kb)
        register(server)
        assert "solveit_list_loaded_extensions" in server._registered_tools

    @pytest.mark.asyncio
    async def test_extension_tool_returns_list(self) -> None:
        from mcp_chassis.extensions.tools.solveit_tools import register
        kb = _load_kb()
        server = _make_server(kb=kb)
        register(server)
        handler = server._registered_tools["solveit_list_loaded_extensions"]["handler"]
        result = json.loads(await handler({}, _make_context()))
        assert isinstance(result, list)


def _make_mock_kb() -> MagicMock:
    """Create a MagicMock KB with citation data for citation tool tests.

    Returns:
        A MagicMock that satisfies the KnowledgeBase interface for citations
        and enough of the remaining interface for ``register()`` to complete.
        MagicMock auto-stubs batch, relationship, and search methods so
        ``register()`` can wire up all tool categories without errors.
    """
    kb = MagicMock()
    kb.citations = {
        "DFCite-1001": {"bibtex": "@article{...", "plaintext": "Author (2024)"},
        "DFCite-1002": {"bibtex": "@book{...", "plaintext": None},
    }
    kb.get_citation.side_effect = lambda cid: kb.citations.get(cid)
    kb.has_extensions.return_value = False
    return kb


class TestCitationTools:
    @pytest.fixture()
    def server_with_kb(self) -> MagicMock:
        from mcp_chassis.extensions.tools.solveit_tools import register
        kb = _make_mock_kb()
        server = _make_server(kb=kb)
        register(server)
        return server

    def test_get_citation_registered(self, server_with_kb: MagicMock) -> None:
        assert "solveit_get_citation" in server_with_kb._registered_tools

    def test_list_citations_registered(self, server_with_kb: MagicMock) -> None:
        assert "solveit_list_citations" in server_with_kb._registered_tools

    @pytest.mark.asyncio
    async def test_get_citation_returns_data(self, server_with_kb: MagicMock) -> None:
        handler = server_with_kb._registered_tools["solveit_get_citation"]["handler"]
        result = json.loads(await handler({"citation_id": "DFCite-1001"}, _make_context()))
        assert result["id"] == "DFCite-1001"
        assert "bibtex" in result or "plaintext" in result

    @pytest.mark.asyncio
    async def test_get_citation_not_found(self, server_with_kb: MagicMock) -> None:
        handler = server_with_kb._registered_tools["solveit_get_citation"]["handler"]
        result = json.loads(await handler({"citation_id": "DFCite-9999"}, _make_context()))
        assert result["error"] == "not_found"
        assert result["id"] == "DFCite-9999"

    @pytest.mark.asyncio
    async def test_list_citations_returns_list(self, server_with_kb: MagicMock) -> None:
        handler = server_with_kb._registered_tools["solveit_list_citations"]["handler"]
        result = json.loads(await handler({}, _make_context()))
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(item["id"].startswith("DFCite-") for item in result)


class TestAllToolsRegistered:
    _ALL_DEFAULT_TOOLS = [
        "solveit_status",
        "solveit_get_technique",
        "solveit_get_weakness",
        "solveit_get_mitigation",
        "solveit_list_techniques",
        "solveit_list_weaknesses",
        "solveit_list_mitigations",
        "solveit_list_objectives",
        "solveit_get_techniques_for_objective",
        "solveit_get_weaknesses_for_technique",
        "solveit_get_mitigations_for_weakness",
        "solveit_get_techniques_for_weakness",
        "solveit_get_weaknesses_for_mitigation",
        "solveit_get_techniques_for_mitigation",
        "solveit_search",
        "solveit_list_loaded_extensions",
        "solveit_get_citation",
        "solveit_list_citations",
    ]

    _FULL_DETAIL_TOOLS = [
        "solveit_list_techniques_full_detail",
        "solveit_list_weaknesses_full_detail",
        "solveit_list_mitigations_full_detail",
    ]

    def test_default_config_registers_18_tools(self) -> None:
        from mcp_chassis.extensions.tools.solveit_tools import register
        kb = _load_kb()
        server = _make_server(kb=kb)
        register(server)
        for tool in self._ALL_DEFAULT_TOOLS:
            assert tool in server._registered_tools, f"Missing: {tool}"
        for tool in self._FULL_DETAIL_TOOLS:
            assert tool not in server._registered_tools, f"Should not be registered: {tool}"
        assert len(server._registered_tools) == 18

    def test_full_detail_enabled_registers_21_tools(self) -> None:
        from mcp_chassis.extensions.tools.solveit_tools import register
        kb = _load_kb()
        server = _make_server(app_config={"enable_full_detail_tools": True}, kb=kb)
        register(server)
        all_tools = self._ALL_DEFAULT_TOOLS + self._FULL_DETAIL_TOOLS
        for tool in all_tools:
            assert tool in server._registered_tools, f"Missing: {tool}"
        assert len(server._registered_tools) == 21

    def test_kb_failure_registers_only_status(self) -> None:
        from mcp_chassis.extensions.tools.solveit_tools import register
        server = _make_server(kb=None, kb_error="Test failure")
        register(server)
        assert list(server._registered_tools.keys()) == ["solveit_status"]
