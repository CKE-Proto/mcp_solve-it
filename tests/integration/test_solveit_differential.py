"""Differential tests for SOLVE-IT MCP tools.

These tests load the SOLVE-IT KnowledgeBase directly and compare its output
against what the MCP server returns for the same queries. This catches
serialization bugs, data transformation errors, and ensures the MCP layer
is a faithful pass-through of the underlying library.

Each test:
1. Queries the KB library directly to establish ground truth
2. Queries the MCP server for the same data
3. Asserts the results match
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

# ── Load the KB directly for ground-truth comparison ────────────────────

_SOLVEIT_PATH = str(
    (Path(__file__).resolve().parents[2].parent / "solve-it" / "solve-it-main").resolve()
)

if _SOLVEIT_PATH not in sys.path:
    sys.path.insert(0, _SOLVEIT_PATH)

from solve_it_library import KnowledgeBase  # noqa: E402

_kb = KnowledgeBase(base_path=_SOLVEIT_PATH)


# ── Helpers ─────────────────────────────────────────────────────────────

async def _call_tool(mcp_client: Any, tool_name: str, arguments: dict[str, Any]) -> Any:
    """Call an MCP tool and return the parsed JSON result."""
    response = await mcp_client.send_request(
        "tools/call",
        {"name": tool_name, "arguments": arguments},
    )
    assert "result" in response, f"Expected result, got: {response}"
    return json.loads(response["result"]["content"][0]["text"])


# ── Differential: Technique Lookup ──────────────────────────────────────

@pytest.mark.asyncio
class TestDifferentialTechniqueLookup:
    """Verify MCP technique lookups match the KB library."""

    async def test_technique_fields_match(self, mcp_client: Any) -> None:
        """Every field in a technique should match between KB and MCP."""
        kb_technique = _kb.get_technique("DFT-1001")
        mcp_technique = await _call_tool(
            mcp_client, "solveit_get_technique", {"technique_id": "DFT-1001"}
        )
        assert kb_technique is not None
        for key in kb_technique:
            assert key in mcp_technique, f"Missing key '{key}' in MCP response"
            assert mcp_technique[key] == kb_technique[key], (
                f"Mismatch for key '{key}': KB={kb_technique[key]!r}, MCP={mcp_technique[key]!r}"
            )

    async def test_multiple_techniques_match(self, mcp_client: Any) -> None:
        """Spot-check several techniques across the ID range."""
        sample_ids = ["DFT-1001", "DFT-1010", "DFT-1050", "DFT-1100"]
        for t_id in sample_ids:
            kb_val = _kb.get_technique(t_id)
            if kb_val is None:
                continue  # ID doesn't exist, skip
            mcp_val = await _call_tool(
                mcp_client, "solveit_get_technique", {"technique_id": t_id}
            )
            assert mcp_val["id"] == kb_val["id"]
            assert mcp_val["name"] == kb_val["name"]
            assert mcp_val["description"] == kb_val["description"]


# ── Differential: Weakness Lookup ───────────────────────────────────────

@pytest.mark.asyncio
class TestDifferentialWeaknessLookup:
    """Verify MCP weakness lookups match the KB library."""

    async def test_weakness_fields_match(self, mcp_client: Any) -> None:
        """Every field in a weakness should match between KB and MCP."""
        kb_weakness = _kb.get_weakness("DFW-1002")
        mcp_weakness = await _call_tool(
            mcp_client, "solveit_get_weakness", {"weakness_id": "DFW-1002"}
        )
        assert kb_weakness is not None
        for key in kb_weakness:
            assert key in mcp_weakness, f"Missing key '{key}' in MCP response"
            assert mcp_weakness[key] == kb_weakness[key], (
                f"Mismatch for key '{key}': KB={kb_weakness[key]!r}, MCP={mcp_weakness[key]!r}"
            )


# ── Differential: Mitigation Lookup ─────────────────────────────────────

@pytest.mark.asyncio
class TestDifferentialMitigationLookup:
    """Verify MCP mitigation lookups match the KB library."""

    async def test_mitigation_fields_match(self, mcp_client: Any) -> None:
        """Every field in a mitigation should match between KB and MCP."""
        kb_mitigation = _kb.get_mitigation("DFM-1001")
        mcp_mitigation = await _call_tool(
            mcp_client, "solveit_get_mitigation", {"mitigation_id": "DFM-1001"}
        )
        assert kb_mitigation is not None
        for key in kb_mitigation:
            assert key in mcp_mitigation, f"Missing key '{key}' in MCP response"
            assert mcp_mitigation[key] == kb_mitigation[key], (
                f"Mismatch for key '{key}': KB={kb_mitigation[key]!r}, MCP={mcp_mitigation[key]!r}"
            )


# ── Differential: Summary Listings ──────────────────────────────────────

@pytest.mark.asyncio
class TestDifferentialListings:
    """Verify MCP listing tools return the same items as the KB."""

    async def test_technique_listing_count_matches(self, mcp_client: Any) -> None:
        """MCP list should return the same number of techniques as the KB."""
        kb_list = _kb.get_all_techniques_with_name_and_id()
        mcp_list = await _call_tool(mcp_client, "solveit_list_techniques", {})
        assert len(mcp_list) == len(kb_list), (
            f"Count mismatch: KB={len(kb_list)}, MCP={len(mcp_list)}"
        )

    async def test_technique_listing_ids_match(self, mcp_client: Any) -> None:
        """Every technique ID from the KB should appear in the MCP list."""
        kb_list = _kb.get_all_techniques_with_name_and_id()
        mcp_list = await _call_tool(mcp_client, "solveit_list_techniques", {})
        kb_ids = {item["id"] for item in kb_list}
        mcp_ids = {item["id"] for item in mcp_list}
        assert kb_ids == mcp_ids, f"ID difference: {kb_ids.symmetric_difference(mcp_ids)}"

    async def test_technique_listing_names_match(self, mcp_client: Any) -> None:
        """Every technique name should match between KB and MCP listings."""
        kb_list = _kb.get_all_techniques_with_name_and_id()
        mcp_list = await _call_tool(mcp_client, "solveit_list_techniques", {})
        kb_by_id = {item["id"]: item["name"] for item in kb_list}
        mcp_by_id = {item["id"]: item["name"] for item in mcp_list}
        for t_id in kb_by_id:
            assert mcp_by_id[t_id] == kb_by_id[t_id], (
                f"{t_id}: KB name={kb_by_id[t_id]!r}, MCP name={mcp_by_id[t_id]!r}"
            )

    async def test_weakness_listing_count_matches(self, mcp_client: Any) -> None:
        """MCP list should return the same number of weaknesses as the KB."""
        kb_list = _kb.get_all_weaknesses_with_name_and_id()
        mcp_list = await _call_tool(mcp_client, "solveit_list_weaknesses", {})
        assert len(mcp_list) == len(kb_list)

    async def test_weakness_listing_ids_match(self, mcp_client: Any) -> None:
        """Every weakness ID from the KB should appear in the MCP list."""
        kb_list = _kb.get_all_weaknesses_with_name_and_id()
        mcp_list = await _call_tool(mcp_client, "solveit_list_weaknesses", {})
        kb_ids = {item["id"] for item in kb_list}
        mcp_ids = {item["id"] for item in mcp_list}
        assert kb_ids == mcp_ids

    async def test_mitigation_listing_count_matches(self, mcp_client: Any) -> None:
        """MCP list should return the same number of mitigations as the KB."""
        kb_list = _kb.get_all_mitigations_with_name_and_id()
        mcp_list = await _call_tool(mcp_client, "solveit_list_mitigations", {})
        assert len(mcp_list) == len(kb_list)

    async def test_mitigation_listing_ids_match(self, mcp_client: Any) -> None:
        """Every mitigation ID from the KB should appear in the MCP list."""
        kb_list = _kb.get_all_mitigations_with_name_and_id()
        mcp_list = await _call_tool(mcp_client, "solveit_list_mitigations", {})
        kb_ids = {item["id"] for item in kb_list}
        mcp_ids = {item["id"] for item in mcp_list}
        assert kb_ids == mcp_ids


# ── Differential: Relationships ─────────────────────────────────────────

@pytest.mark.asyncio
class TestDifferentialRelationships:
    """Verify MCP relationship tools return the same data as the KB."""

    async def test_weaknesses_for_technique_match(self, mcp_client: Any) -> None:
        """DFT-1001 should return the same weaknesses via MCP as via KB."""
        kb_result = _kb.get_weaknesses_for_technique("DFT-1001")
        mcp_result = await _call_tool(
            mcp_client,
            "solveit_get_weaknesses_for_technique",
            {"technique_id": "DFT-1001"},
        )
        kb_ids = sorted(w["id"] for w in kb_result)
        mcp_ids = sorted(w["id"] for w in mcp_result)
        assert mcp_ids == kb_ids, f"KB={kb_ids}, MCP={mcp_ids}"
        # Known ground truth: DFT-1001 has weaknesses DFW-1001, DFW-1002, DFW-1003
        assert set(kb_ids) == {"DFW-1001", "DFW-1002", "DFW-1003"}

    async def test_mitigations_for_weakness_match(self, mcp_client: Any) -> None:
        """DFW-1002 should return the same mitigations via MCP as via KB."""
        kb_result = _kb.get_mitigations_for_weakness("DFW-1002")
        mcp_result = await _call_tool(
            mcp_client,
            "solveit_get_mitigations_for_weakness",
            {"weakness_id": "DFW-1002"},
        )
        kb_ids = sorted(m["id"] for m in kb_result)
        mcp_ids = sorted(m["id"] for m in mcp_result)
        assert mcp_ids == kb_ids
        # Known ground truth: DFW-1002 has mitigations DFM-1007, DFM-1008
        assert set(kb_ids) == {"DFM-1007", "DFM-1008"}

    async def test_techniques_for_weakness_match(self, mcp_client: Any) -> None:
        """DFW-1002 should return the same techniques via MCP as via KB (reverse lookup)."""
        kb_result = _kb.get_techniques_for_weakness("DFW-1002")
        mcp_result = await _call_tool(
            mcp_client,
            "solveit_get_techniques_for_weakness",
            {"weakness_id": "DFW-1002"},
        )
        kb_ids = sorted(t["id"] for t in kb_result)
        mcp_ids = sorted(t["id"] for t in mcp_result)
        assert mcp_ids == kb_ids
        # Known ground truth: DFW-1002 is associated with DFT-1001
        assert kb_ids == ["DFT-1001"]

    async def test_weaknesses_for_mitigation_match(self, mcp_client: Any) -> None:
        """DFM-1001 should return the same weaknesses via MCP as via KB."""
        kb_result = _kb.get_weaknesses_for_mitigation("DFM-1001")
        mcp_result = await _call_tool(
            mcp_client,
            "solveit_get_weaknesses_for_mitigation",
            {"mitigation_id": "DFM-1001"},
        )
        kb_ids = sorted(w["id"] for w in kb_result)
        mcp_ids = sorted(w["id"] for w in mcp_result)
        assert mcp_ids == kb_ids
        # Known ground truth: DFM-1001 addresses DFW-1003
        assert kb_ids == ["DFW-1003"]

    async def test_techniques_for_mitigation_match(self, mcp_client: Any) -> None:
        """DFM-1001 should return the same techniques via MCP as via KB."""
        kb_result = _kb.get_techniques_for_mitigation("DFM-1001")
        mcp_result = await _call_tool(
            mcp_client,
            "solveit_get_techniques_for_mitigation",
            {"mitigation_id": "DFM-1001"},
        )
        kb_ids = sorted(t["id"] for t in kb_result)
        mcp_ids = sorted(t["id"] for t in mcp_result)
        assert mcp_ids == kb_ids
        # Known ground truth: DFM-1001 is reachable from DFT-1001
        assert kb_ids == ["DFT-1001"]


# ── Differential: Search ────────────────────────────────────────────────

@pytest.mark.asyncio
class TestDifferentialSearch:
    """Verify MCP search returns the same results as the KB library."""

    async def test_search_result_counts_match(self, mcp_client: Any) -> None:
        """Search for 'disk image' should return same counts via MCP and KB."""
        kb_result = _kb.search("disk image")
        mcp_result = await _call_tool(
            mcp_client, "solveit_search", {"keywords": "disk image"}
        )
        assert len(mcp_result["techniques"]) == len(kb_result["techniques"]), (
            f"Technique count: KB={len(kb_result['techniques'])}, "
            f"MCP={len(mcp_result['techniques'])}"
        )
        assert len(mcp_result["weaknesses"]) == len(kb_result["weaknesses"])
        assert len(mcp_result["mitigations"]) == len(kb_result["mitigations"])

    async def test_search_result_ids_match(self, mcp_client: Any) -> None:
        """Search results should contain the same IDs via MCP and KB."""
        kb_result = _kb.search("disk image")
        mcp_result = await _call_tool(
            mcp_client, "solveit_search", {"keywords": "disk image"}
        )
        for item_type in ("techniques", "weaknesses", "mitigations"):
            kb_ids = {item["id"] for item in kb_result[item_type]}
            mcp_ids = {item["id"] for item in mcp_result[item_type]}
            assert mcp_ids == kb_ids, (
                f"{item_type} ID mismatch: "
                f"KB-only={kb_ids - mcp_ids}, MCP-only={mcp_ids - kb_ids}"
            )

    async def test_search_with_item_type_filter(self, mcp_client: Any) -> None:
        """Search filtered to 'techniques' should match KB filtered search."""
        kb_result = _kb.search("hash", item_types=["techniques"])
        mcp_result = await _call_tool(
            mcp_client,
            "solveit_search",
            {"keywords": "hash", "item_types": ["techniques"]},
        )
        kb_ids = {item["id"] for item in kb_result["techniques"]}
        mcp_ids = {item["id"] for item in mcp_result["techniques"]}
        assert mcp_ids == kb_ids
        # Filtered search should not return other types
        assert mcp_result["weaknesses"] == []
        assert mcp_result["mitigations"] == []

    async def test_search_or_logic_matches(self, mcp_client: Any) -> None:
        """OR search should return same results via MCP and KB."""
        kb_result = _kb.search("disk image", search_logic="OR")
        mcp_result = await _call_tool(
            mcp_client,
            "solveit_search",
            {"keywords": "disk image", "search_logic": "OR"},
        )
        for item_type in ("techniques", "weaknesses", "mitigations"):
            kb_ids = {item["id"] for item in kb_result[item_type]}
            mcp_ids = {item["id"] for item in mcp_result[item_type]}
            assert mcp_ids == kb_ids, f"{item_type} OR-search mismatch"


# ── Differential: Objectives ────────────────────────────────────────────

@pytest.mark.asyncio
class TestDifferentialObjectives:
    """Verify MCP objective tools return the same data as the KB."""

    async def test_objective_count_matches(self, mcp_client: Any) -> None:
        """MCP should list the same number of objectives as the KB."""
        kb_objectives = _kb.list_objectives()
        mcp_objectives = await _call_tool(
            mcp_client, "solveit_list_objectives", {}
        )
        assert len(mcp_objectives) == len(kb_objectives)

    async def test_objective_names_match(self, mcp_client: Any) -> None:
        """Every objective name from the KB should appear in the MCP list."""
        kb_objectives = _kb.list_objectives()
        mcp_objectives = await _call_tool(
            mcp_client, "solveit_list_objectives", {}
        )
        kb_names = {o["name"] for o in kb_objectives}
        mcp_names = {o["name"] for o in mcp_objectives}
        assert mcp_names == kb_names

    async def test_techniques_for_objective_match(self, mcp_client: Any) -> None:
        """Techniques for a known objective should match between KB and MCP."""
        obj_name = "Find potential digital evidence sources"
        kb_techniques = _kb.get_techniques_for_objective(obj_name)
        mcp_techniques = await _call_tool(
            mcp_client,
            "solveit_get_techniques_for_objective",
            {"objective_name": obj_name},
        )
        kb_ids = sorted(t["id"] for t in kb_techniques)
        mcp_ids = sorted(t["id"] for t in mcp_techniques)
        assert mcp_ids == kb_ids
        # Known ground truth: this objective has 5 techniques
        assert len(kb_ids) == 5


# ── Differential: Status Counts ─────────────────────────────────────────

@pytest.mark.asyncio
class TestDifferentialStatus:
    """Verify solveit_status counts match the actual KB."""

    async def test_status_technique_count_matches(self, mcp_client: Any) -> None:
        """Status tool technique count should match KB."""
        mcp_status = await _call_tool(mcp_client, "solveit_status", {})
        assert mcp_status["techniques"] == len(_kb.list_techniques())

    async def test_status_weakness_count_matches(self, mcp_client: Any) -> None:
        """Status tool weakness count should match KB."""
        mcp_status = await _call_tool(mcp_client, "solveit_status", {})
        assert mcp_status["weaknesses"] == len(_kb.list_weaknesses())

    async def test_status_mitigation_count_matches(self, mcp_client: Any) -> None:
        """Status tool mitigation count should match KB."""
        mcp_status = await _call_tool(mcp_client, "solveit_status", {})
        assert mcp_status["mitigations"] == len(_kb.list_mitigations())
