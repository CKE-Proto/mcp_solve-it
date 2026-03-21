"""Unit tests for mcp_chassis.security.validation module."""

import pytest

from mcp_chassis.errors import ValidationError
from mcp_chassis.security.validation import (
    ValidationLimits,
    ValidationResult,
    raise_if_invalid,
    validate_tool_input,
)

DEFAULT_LIMITS = ValidationLimits(
    max_string_length=100,
    max_array_length=10,
    max_object_depth=5,
)


class TestValidateToolInputBasic:
    """Basic type validation tests."""

    def test_valid_string_field(self) -> None:
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        result = validate_tool_input({"name": "Alice"}, schema, DEFAULT_LIMITS)
        assert result.valid

    def test_missing_required_field(self) -> None:
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        result = validate_tool_input({}, schema, DEFAULT_LIMITS)
        assert not result.valid
        assert any("name" in e for e in result.errors)

    def test_wrong_type_string_expected_int(self) -> None:
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
        }
        result = validate_tool_input({"count": "five"}, schema, DEFAULT_LIMITS)
        assert not result.valid

    def test_integer_type_valid(self) -> None:
        schema = {"type": "object", "properties": {"n": {"type": "integer"}}}
        result = validate_tool_input({"n": 42}, schema, DEFAULT_LIMITS)
        assert result.valid

    def test_number_type_accepts_float(self) -> None:
        schema = {"type": "object", "properties": {"x": {"type": "number"}}}
        result = validate_tool_input({"x": 3.14}, schema, DEFAULT_LIMITS)
        assert result.valid

    def test_number_type_accepts_int(self) -> None:
        schema = {"type": "object", "properties": {"x": {"type": "number"}}}
        result = validate_tool_input({"x": 5}, schema, DEFAULT_LIMITS)
        assert result.valid

    def test_boolean_type(self) -> None:
        schema = {"type": "object", "properties": {"flag": {"type": "boolean"}}}
        result = validate_tool_input({"flag": True}, schema, DEFAULT_LIMITS)
        assert result.valid

    def test_boolean_not_accepted_as_integer(self) -> None:
        schema = {"type": "object", "properties": {"n": {"type": "integer"}}}
        result = validate_tool_input({"n": True}, schema, DEFAULT_LIMITS)
        assert not result.valid

    def test_null_type(self) -> None:
        schema = {"type": "object", "properties": {"v": {"type": "null"}}}
        result = validate_tool_input({"v": None}, schema, DEFAULT_LIMITS)
        assert result.valid

    def test_array_type(self) -> None:
        schema = {"type": "object", "properties": {"items": {"type": "array"}}}
        result = validate_tool_input({"items": [1, 2, 3]}, schema, DEFAULT_LIMITS)
        assert result.valid

    def test_empty_schema(self) -> None:
        result = validate_tool_input({"anything": 42}, {}, DEFAULT_LIMITS)
        assert result.valid


class TestStringLengthValidation:
    """Tests for string length limits."""

    def test_string_within_limit(self) -> None:
        schema = {"type": "object", "properties": {"s": {"type": "string"}}}
        result = validate_tool_input({"s": "a" * 50}, schema, DEFAULT_LIMITS)
        assert result.valid

    def test_string_exceeds_limit(self) -> None:
        schema = {"type": "object", "properties": {"s": {"type": "string"}}}
        result = validate_tool_input({"s": "a" * 200}, schema, DEFAULT_LIMITS)
        assert not result.valid
        assert any("string length" in e for e in result.errors)

    def test_schema_max_length(self) -> None:
        schema = {
            "type": "object",
            "properties": {"s": {"type": "string", "maxLength": 5}},
        }
        result = validate_tool_input({"s": "toolong"}, schema, DEFAULT_LIMITS)
        assert not result.valid

    def test_schema_min_length(self) -> None:
        schema = {
            "type": "object",
            "properties": {"s": {"type": "string", "minLength": 5}},
        }
        result = validate_tool_input({"s": "hi"}, schema, DEFAULT_LIMITS)
        assert not result.valid


class TestArrayValidation:
    """Tests for array validation."""

    def test_array_within_limit(self) -> None:
        schema = {"type": "object", "properties": {"a": {"type": "array"}}}
        result = validate_tool_input({"a": [1, 2, 3]}, schema, DEFAULT_LIMITS)
        assert result.valid

    def test_array_exceeds_limit(self) -> None:
        schema = {"type": "object", "properties": {"a": {"type": "array"}}}
        result = validate_tool_input({"a": list(range(20))}, schema, DEFAULT_LIMITS)
        assert not result.valid

    def test_array_items_type_check(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "a": {
                    "type": "array",
                    "items": {"type": "string"},
                }
            },
        }
        result = validate_tool_input({"a": ["ok", 42]}, schema, DEFAULT_LIMITS)
        assert not result.valid

    def test_schema_max_items(self) -> None:
        schema = {
            "type": "object",
            "properties": {"a": {"type": "array", "maxItems": 2}},
        }
        result = validate_tool_input({"a": [1, 2, 3]}, schema, DEFAULT_LIMITS)
        assert not result.valid


class TestNestingDepth:
    """Tests for nesting depth limits."""

    def test_shallow_nesting_ok(self) -> None:
        schema = {"type": "object"}
        result = validate_tool_input({"a": {"b": 1}}, schema, DEFAULT_LIMITS)
        assert result.valid

    def test_exceeds_depth_limit(self) -> None:
        # Create a deeply nested structure via schema-defined properties
        # DEFAULT_LIMITS has max_object_depth=5; build deeper than that
        schema: dict = {"type": "object"}
        nested_schema = schema
        data: dict = {}
        nested_data = data
        for _ in range(7):
            nested_schema["properties"] = {"x": {"type": "object"}}
            nested_schema["required"] = ["x"]
            nested_schema = nested_schema["properties"]["x"]
            nested_data["x"] = {}
            nested_data = nested_data["x"]
        result = validate_tool_input(data, schema, DEFAULT_LIMITS)
        assert not result.valid


class TestAdditionalProperties:
    """Tests for additionalProperties validation."""

    def test_extra_keys_rejected_when_false(self) -> None:
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "additionalProperties": False,
        }
        result = validate_tool_input({"name": "Alice", "admin": True}, schema, DEFAULT_LIMITS)
        assert not result.valid
        assert any("unexpected property 'admin'" in e for e in result.errors)

    def test_multiple_extra_keys_all_reported(self) -> None:
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "additionalProperties": False,
        }
        result = validate_tool_input(
            {"name": "Alice", "admin": True, "debug": True}, schema, DEFAULT_LIMITS
        )
        assert not result.valid
        assert any("admin" in e for e in result.errors)
        assert any("debug" in e for e in result.errors)

    def test_no_extra_keys_passes(self) -> None:
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "additionalProperties": False,
        }
        result = validate_tool_input({"name": "Alice"}, schema, DEFAULT_LIMITS)
        assert result.valid

    def test_extra_keys_allowed_when_not_set(self) -> None:
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
        }
        result = validate_tool_input({"name": "Alice", "extra": 42}, schema, DEFAULT_LIMITS)
        assert result.valid

    def test_extra_keys_allowed_when_true(self) -> None:
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "additionalProperties": True,
        }
        result = validate_tool_input({"name": "Alice", "extra": 42}, schema, DEFAULT_LIMITS)
        assert result.valid


class TestRaiseIfInvalid:
    """Tests for raise_if_invalid convenience function."""

    def test_raises_on_invalid(self) -> None:
        schema = {"type": "object", "required": ["name"]}
        with pytest.raises(ValidationError):
            raise_if_invalid({}, schema, DEFAULT_LIMITS)

    def test_does_not_raise_on_valid(self) -> None:
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        raise_if_invalid({"name": "Alice"}, schema, DEFAULT_LIMITS)  # No exception

    def test_error_contains_details(self) -> None:
        schema = {"type": "object", "required": ["name"]}
        with pytest.raises(ValidationError) as exc_info:
            raise_if_invalid({}, schema, DEFAULT_LIMITS)
        assert "name" in str(exc_info.value)


class TestMultipleErrorReporting:
    """Tests that errors in one branch don't suppress errors in other branches."""

    def test_type_error_does_not_suppress_sibling_length_error(self) -> None:
        """A type error on 'name' should not suppress maxLength check on 'bio'."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "integer"},
                "bio": {"type": "string", "maxLength": 5},
            },
        }
        result = validate_tool_input(
            {"name": "not-int", "bio": "way too long"}, schema, DEFAULT_LIMITS
        )
        assert not result.valid
        assert any("name" in e and "integer" in e for e in result.errors)
        assert any("bio" in e and "maxLength" in e for e in result.errors)

    def test_type_error_does_not_suppress_sibling_required_error(self) -> None:
        """A type error on 'a' should not suppress missing required field 'b'."""
        schema = {
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "string"},
            },
            "required": ["a", "b"],
        }
        result = validate_tool_input({"a": "wrong-type"}, schema, DEFAULT_LIMITS)
        assert not result.valid
        assert any("a" in e and "integer" in e for e in result.errors)
        assert any("b" in e and "required" in e for e in result.errors)

    def test_type_error_does_not_suppress_sibling_type_error(self) -> None:
        """Type errors on two different properties should both be reported."""
        schema = {
            "type": "object",
            "properties": {
                "x": {"type": "integer"},
                "y": {"type": "boolean"},
            },
        }
        result = validate_tool_input(
            {"x": "wrong", "y": "also-wrong"}, schema, DEFAULT_LIMITS
        )
        assert not result.valid
        assert any("x" in e for e in result.errors)
        assert any("y" in e for e in result.errors)
        assert len(result.errors) >= 2

    def test_array_item_error_does_not_suppress_sibling_error(self) -> None:
        """An error inside an array should not suppress errors on sibling fields."""
        schema = {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {"type": "integer"}},
                "label": {"type": "string", "maxLength": 3},
            },
        }
        result = validate_tool_input(
            {"items": ["not-int"], "label": "toolong"}, schema, DEFAULT_LIMITS
        )
        assert not result.valid
        assert any("items" in e and "integer" in e for e in result.errors)
        assert any("label" in e and "maxLength" in e for e in result.errors)

    def test_own_type_error_still_short_circuits(self) -> None:
        """A type error on THIS value should still skip deeper checks on it.

        e.g. if 'data' is a string but schema says array, don't try to
        validate array items on the string.
        """
        schema = {
            "type": "object",
            "properties": {
                "data": {"type": "array", "items": {"type": "string"}},
            },
        }
        result = validate_tool_input({"data": "not-an-array"}, schema, DEFAULT_LIMITS)
        assert not result.valid
        # Should have exactly one error: type mismatch on 'data'
        assert len(result.errors) == 1
        assert "data" in result.errors[0]


class TestEnumValidation:
    """Tests for JSON schema enum constraint enforcement."""

    def test_valid_enum_value_passes(self) -> None:
        schema = {
            "type": "object",
            "properties": {"color": {"type": "string", "enum": ["red", "green", "blue"]}},
        }
        result = validate_tool_input({"color": "red"}, schema, DEFAULT_LIMITS)
        assert result.valid

    def test_invalid_enum_value_fails(self) -> None:
        schema = {
            "type": "object",
            "properties": {"color": {"type": "string", "enum": ["red", "green", "blue"]}},
        }
        result = validate_tool_input({"color": "purple"}, schema, DEFAULT_LIMITS)
        assert not result.valid
        assert any("enum" in e.lower() for e in result.errors)

    def test_enum_with_integers(self) -> None:
        schema = {
            "type": "object",
            "properties": {"level": {"type": "integer", "enum": [1, 2, 3]}},
        }
        result = validate_tool_input({"level": 2}, schema, DEFAULT_LIMITS)
        assert result.valid

    def test_enum_with_invalid_integer(self) -> None:
        schema = {
            "type": "object",
            "properties": {"level": {"type": "integer", "enum": [1, 2, 3]}},
        }
        result = validate_tool_input({"level": 99}, schema, DEFAULT_LIMITS)
        assert not result.valid

    def test_enum_with_boolean(self) -> None:
        schema = {
            "type": "object",
            "properties": {"flag": {"type": "boolean", "enum": [True]}},
        }
        result = validate_tool_input({"flag": True}, schema, DEFAULT_LIMITS)
        assert result.valid

    def test_enum_with_null(self) -> None:
        schema = {
            "type": "object",
            "properties": {"val": {"enum": [None, "none"]}},
        }
        result = validate_tool_input({"val": None}, schema, DEFAULT_LIMITS)
        assert result.valid

    def test_enum_error_message_includes_allowed_values(self) -> None:
        schema = {
            "type": "object",
            "properties": {"mode": {"type": "string", "enum": ["AND", "OR"]}},
        }
        result = validate_tool_input({"mode": "XOR"}, schema, DEFAULT_LIMITS)
        assert not result.valid
        assert any("AND" in e and "OR" in e for e in result.errors)

    def test_enum_on_non_list_is_ignored(self) -> None:
        """If enum is not a list (malformed schema), skip the check."""
        schema = {
            "type": "object",
            "properties": {"x": {"type": "string", "enum": "not-a-list"}},
        }
        result = validate_tool_input({"x": "anything"}, schema, DEFAULT_LIMITS)
        assert result.valid


class TestMalformedSchemaLimits:
    """Tests that malformed schema limit values don't crash the validator."""

    def test_non_integer_max_length_does_not_crash(self) -> None:
        schema = {
            "type": "object",
            "properties": {"s": {"type": "string", "maxLength": "bad"}},
        }
        result = validate_tool_input({"s": "hello"}, schema, DEFAULT_LIMITS)
        # Should not crash — should either skip the constraint or report an error
        assert isinstance(result, ValidationResult)

    def test_dict_max_length_does_not_crash(self) -> None:
        schema = {
            "type": "object",
            "properties": {"s": {"type": "string", "maxLength": {}}},
        }
        result = validate_tool_input({"s": "hello"}, schema, DEFAULT_LIMITS)
        assert isinstance(result, ValidationResult)

    def test_non_integer_min_length_does_not_crash(self) -> None:
        schema = {
            "type": "object",
            "properties": {"s": {"type": "string", "minLength": "bad"}},
        }
        result = validate_tool_input({"s": "hello"}, schema, DEFAULT_LIMITS)
        assert isinstance(result, ValidationResult)

    def test_non_integer_max_items_does_not_crash(self) -> None:
        schema = {
            "type": "object",
            "properties": {"a": {"type": "array", "maxItems": "bad"}},
        }
        result = validate_tool_input({"a": [1, 2]}, schema, DEFAULT_LIMITS)
        assert isinstance(result, ValidationResult)

    def test_non_integer_min_items_does_not_crash(self) -> None:
        schema = {
            "type": "object",
            "properties": {"a": {"type": "array", "minItems": []}},
        }
        result = validate_tool_input({"a": [1]}, schema, DEFAULT_LIMITS)
        assert isinstance(result, ValidationResult)


class TestValidationResult:
    """Tests for ValidationResult helper methods."""

    def test_ok_result(self) -> None:
        r = ValidationResult.ok()
        assert r.valid
        assert r.errors == []

    def test_fail_result(self) -> None:
        r = ValidationResult.fail(["error1", "error2"])
        assert not r.valid
        assert len(r.errors) == 2
