"""Input validation for MCP tool arguments.

Validates tool arguments against JSON schema definitions using only the
Python standard library. No jsonschema library is used.

Validates: required fields, basic types, string length, array length,
and nesting depth.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from mcp_chassis.errors import ValidationError

logger = logging.getLogger(__name__)

# Mapping from JSON schema type strings to Python types
_TYPE_MAP: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
    "null": (type(None),),
}


@dataclass(frozen=True)
class ValidationLimits:
    """Structural limits for input validation.

    Attributes:
        max_string_length: Maximum characters in any string value.
        max_array_length: Maximum elements in any array.
        max_object_depth: Maximum nesting depth of objects/arrays.
    """

    max_string_length: int = 10_000
    max_array_length: int = 100
    max_object_depth: int = 10


@dataclass
class ValidationResult:
    """Result of a validation check.

    Attributes:
        valid: True if validation passed.
        errors: List of error messages if validation failed.
    """

    valid: bool
    errors: list[str]

    @classmethod
    def ok(cls) -> ValidationResult:
        """Return a successful validation result.

        Returns:
            ValidationResult with valid=True.
        """
        return cls(valid=True, errors=[])

    @classmethod
    def fail(cls, errors: list[str]) -> ValidationResult:
        """Return a failed validation result.

        Args:
            errors: List of validation error messages.

        Returns:
            ValidationResult with valid=False.
        """
        return cls(valid=False, errors=errors)


def validate_tool_input(
    arguments: dict[str, Any],
    schema: dict[str, Any],
    limits: ValidationLimits,
) -> ValidationResult:
    """Validate tool arguments against a JSON schema and structural limits.

    Validates required fields, basic types (string/integer/number/boolean/
    array/object/null), string length, array length, and nesting depth.
    Validates enum constraints. Does NOT validate format specifiers or patterns.

    Args:
        arguments: The tool arguments dict to validate.
        schema: JSON schema dict with 'type', 'properties', 'required' keys.
        limits: Structural limits for validation.

    Returns:
        ValidationResult with valid=True or valid=False plus error list.
    """
    errors: list[str] = []
    _validate_value(arguments, schema, limits, path="arguments", depth=0, errors=errors)
    if errors:
        return ValidationResult.fail(errors)
    return ValidationResult.ok()


def _validate_value(
    value: Any,
    schema: dict[str, Any],
    limits: ValidationLimits,
    path: str,
    depth: int,
    errors: list[str],
) -> None:
    """Recursively validate a value against a schema fragment.

    Args:
        value: The value to validate.
        schema: Schema fragment for this value.
        limits: Structural limits.
        path: JSON path string for error messages.
        depth: Current nesting depth.
        errors: Accumulator for error messages.
    """
    if depth > limits.max_object_depth:
        errors.append(f"{path}: exceeds maximum nesting depth of {limits.max_object_depth}")
        return

    schema_type = schema.get("type")
    if schema_type:
        error_count_before = len(errors)
        _check_type(value, schema_type, path, errors)
        if len(errors) > error_count_before:
            return

    # Enum constraint — applies to any type
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and value not in enum_values:
        errors.append(f"{path}: value {value!r} not in enum {enum_values!r}")

    if isinstance(value, str):
        _validate_string(value, schema, limits, path, errors)
    elif isinstance(value, list):
        _validate_array(value, schema, limits, path, depth, errors)
    elif isinstance(value, dict):
        _validate_object(value, schema, limits, path, depth, errors)


def _check_type(
    value: Any, schema_type: str | list[str], path: str, errors: list[str]
) -> None:
    """Check that value matches the expected JSON schema type(s).

    Args:
        value: Value to check.
        schema_type: A type string or list of type strings.
        path: JSON path for error messages.
        errors: Accumulator for error messages.
    """
    if isinstance(schema_type, list):
        types = schema_type
    else:
        types = [schema_type]

    allowed: tuple[type, ...] = ()
    for t in types:
        allowed += _TYPE_MAP.get(t, ())

    # bool is a subclass of int in Python; must check bool before int
    if "boolean" not in types and isinstance(value, bool):
        errors.append(f"{path}: expected type {types}, got boolean")
        return

    if not isinstance(value, allowed):
        actual = type(value).__name__
        errors.append(f"{path}: expected type {types}, got {actual}")


def _get_int_limit(schema: dict[str, Any], key: str) -> int | None:
    """Return a schema limit value as an int, or None if missing or non-integer.

    Args:
        schema: Schema fragment.
        key: Key name (e.g., 'maxLength', 'minItems').

    Returns:
        The integer value, or None if the key is absent or not a valid integer.
    """
    val = schema.get(key)
    if val is None:
        return None
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    return None


def _validate_string(
    value: str,
    schema: dict[str, Any],
    limits: ValidationLimits,
    path: str,
    errors: list[str],
) -> None:
    """Validate string length constraints.

    Args:
        value: String value to validate.
        schema: Schema fragment (may contain maxLength, minLength).
        limits: Structural limits.
        path: JSON path for error messages.
        errors: Accumulator.
    """
    if len(value) > limits.max_string_length:
        errors.append(
            f"{path}: string length {len(value)} exceeds limit {limits.max_string_length}"
        )
    max_len = _get_int_limit(schema, "maxLength")
    if max_len is not None and len(value) > max_len:
        errors.append(
            f"{path}: string length {len(value)} exceeds maxLength {max_len}"
        )
    min_len = _get_int_limit(schema, "minLength")
    if min_len is not None and len(value) < min_len:
        errors.append(
            f"{path}: string length {len(value)} below minLength {min_len}"
        )


def _validate_array(
    value: list[Any],
    schema: dict[str, Any],
    limits: ValidationLimits,
    path: str,
    depth: int,
    errors: list[str],
) -> None:
    """Validate array length and recursively validate items.

    Args:
        value: Array value to validate.
        schema: Schema fragment (may contain items, maxItems, minItems).
        limits: Structural limits.
        path: JSON path for error messages.
        depth: Current nesting depth.
        errors: Accumulator.
    """
    if len(value) > limits.max_array_length:
        errors.append(
            f"{path}: array length {len(value)} exceeds limit {limits.max_array_length}"
        )
        return

    max_items = _get_int_limit(schema, "maxItems")
    if max_items is not None and len(value) > max_items:
        errors.append(
            f"{path}: array length {len(value)} exceeds maxItems {max_items}"
        )
    min_items = _get_int_limit(schema, "minItems")
    if min_items is not None and len(value) < min_items:
        errors.append(
            f"{path}: array length {len(value)} below minItems {min_items}"
        )

    items_schema = schema.get("items", {})
    for i, item in enumerate(value):
        _validate_value(item, items_schema, limits, f"{path}[{i}]", depth + 1, errors)


def _validate_object(
    value: dict[str, Any],
    schema: dict[str, Any],
    limits: ValidationLimits,
    path: str,
    depth: int,
    errors: list[str],
) -> None:
    """Validate required fields and recursively validate properties.

    Args:
        value: Object dict to validate.
        schema: Schema fragment (may contain required, properties).
        limits: Structural limits.
        path: JSON path for error messages.
        depth: Current nesting depth.
        errors: Accumulator.
    """
    required = schema.get("required", [])
    for req_field in required:
        if req_field not in value:
            errors.append(f"{path}: missing required field '{req_field}'")

    properties = schema.get("properties", {})

    if schema.get("additionalProperties") is False:
        allowed_keys = set(properties.keys())
        extra_keys = set(value.keys()) - allowed_keys
        for key in sorted(extra_keys):
            errors.append(f"{path}: unexpected property '{key}'")

    for prop_name, prop_schema in properties.items():
        if prop_name in value:
            _validate_value(
                value[prop_name],
                prop_schema,
                limits,
                f"{path}.{prop_name}",
                depth + 1,
                errors,
            )


def raise_if_invalid(
    arguments: dict[str, Any],
    schema: dict[str, Any],
    limits: ValidationLimits,
) -> None:
    """Validate and raise ValidationError on failure.

    Convenience wrapper around validate_tool_input for use in middleware.

    Args:
        arguments: Tool arguments to validate.
        schema: JSON schema for validation.
        limits: Structural limits.

    Raises:
        ValidationError: If validation fails, with all error messages joined.
    """
    result = validate_tool_input(arguments, schema, limits)
    if not result.valid:
        message = "Input validation failed: " + "; ".join(result.errors)
        raise ValidationError(message)
