"""
JSON path assertion helpers for FHIR to SPHN mapping tests.
"""

from typing import Any, Optional, Union


def get_path(obj: dict, path: str) -> Any:
    """
    Navigate a nested dict/list structure using dot notation.

    Examples:
        get_path(result, "content.Birth[0].hasDate")
        get_path(result, "content.AdministrativeSex[0].hasCode.termid")

    Supports:
        - Dot notation for nested objects: "content.Birth"
        - Array indexing: "Birth[0]", "Birth[*]" (all elements)
        - Combined: "content.Birth[0].hasDate.hasYear"

    Returns None if path doesn't exist.
    """
    if obj is None:
        return None

    parts = _parse_path(path)
    current = obj

    for part in parts:
        if current is None:
            return None

        if isinstance(part, str):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        elif isinstance(part, int):
            if isinstance(current, list) and 0 <= part < len(current):
                current = current[part]
            else:
                return None
        elif part == "*":
            if isinstance(current, list):
                return current
            else:
                return None

    return current


def _parse_path(path: str) -> list:
    """Parse a path string into a list of keys and indices."""
    parts = []
    current = ""
    i = 0

    while i < len(path):
        char = path[i]

        if char == ".":
            if current:
                parts.append(current)
                current = ""
        elif char == "[":
            if current:
                parts.append(current)
                current = ""
            # Find matching ]
            j = path.index("]", i)
            index_str = path[i + 1 : j]
            if index_str == "*":
                parts.append("*")
            else:
                parts.append(int(index_str))
            i = j
        else:
            current += char

        i += 1

    if current:
        parts.append(current)

    return parts


def assert_path_exists(result: dict, path: str) -> Any:
    """Assert that a path exists in the result and return its value."""
    value = get_path(result, path)
    assert value is not None, f"Path '{path}' does not exist in result"
    return value


def assert_path_equals(result: dict, path: str, expected: Any) -> None:
    """Assert that the value at path equals the expected value."""
    actual = get_path(result, path)
    assert actual == expected, f"Path '{path}': expected {expected!r}, got {actual!r}"


def assert_path_contains(result: dict, path: str, expected: Any) -> None:
    """Assert that the value at path contains the expected value (for strings/lists)."""
    actual = get_path(result, path)
    assert actual is not None, f"Path '{path}' does not exist"
    assert expected in actual, f"Path '{path}': expected {expected!r} to be in {actual!r}"


def assert_code_mapped(
    result: dict,
    path: str,
    expected_termid: str,
    expected_iri_suffix: Optional[str] = None,
) -> None:
    """
    Assert that a Code at path has the expected termid and optionally iri suffix.

    The path should point to a Code object with 'termid' and 'iri' properties.

    Example:
        assert_code_mapped(result, "content.AdministrativeSex[0].hasCode", "248153007", "/248153007")
    """
    code = get_path(result, path)
    assert code is not None, f"Code at '{path}' does not exist"

    actual_termid = code.get("termid")
    assert actual_termid == expected_termid, (
        f"Code termid at '{path}': expected {expected_termid!r}, got {actual_termid!r}"
    )

    if expected_iri_suffix is not None:
        actual_iri = code.get("iri")
        assert actual_iri is not None, f"Code iri at '{path}' is None"
        assert actual_iri.endswith(expected_iri_suffix), (
            f"Code iri at '{path}': expected to end with {expected_iri_suffix!r}, got {actual_iri!r}"
        )


def assert_quantity_mapped(
    result: dict,
    path: str,
    expected_value: Union[int, float],
    expected_unit_code: Optional[str] = None,
) -> None:
    """
    Assert that a Quantity at path has the expected value and optionally unit code.

    Example:
        assert_quantity_mapped(result, "content.BodyTemperatureMeasurement[0].hasResult.hasQuantity", 37.5, "Cel")
    """
    quantity = get_path(result, path)
    assert quantity is not None, f"Quantity at '{path}' does not exist"

    actual_value = quantity.get("hasValue")
    assert actual_value == expected_value, (
        f"Quantity value at '{path}': expected {expected_value!r}, got {actual_value!r}"
    )

    if expected_unit_code is not None:
        unit = quantity.get("hasUnit")
        assert unit is not None, f"Quantity hasUnit at '{path}' is None"
        unit_code = get_path(unit, "hasCode.termid")
        assert unit_code == expected_unit_code, (
            f"Quantity unit code at '{path}': expected {expected_unit_code!r}, got {unit_code!r}"
        )


def assert_list_length(result: dict, path: str, expected_length: int) -> None:
    """Assert that the list at path has the expected length."""
    value = get_path(result, path)
    assert value is not None, f"Path '{path}' does not exist"
    assert isinstance(value, list), f"Path '{path}' is not a list: {type(value)}"
    assert len(value) == expected_length, (
        f"List at '{path}': expected length {expected_length}, got {len(value)}"
    )


def assert_reference(result: dict, path: str, expected_reference: str) -> None:
    """Assert that a Reference at path has the expected reference value."""
    ref = get_path(result, path)
    assert ref is not None, f"Reference at '{path}' does not exist"

    actual_ref = ref.get("reference") if isinstance(ref, dict) else ref
    assert actual_ref == expected_reference, (
        f"Reference at '{path}': expected {expected_reference!r}, got {actual_ref!r}"
    )


def find_in_list(
    result: dict,
    list_path: str,
    match_path: str,
    match_value: Any,
) -> Optional[dict]:
    """
    Find an item in a list where a nested path equals a value.

    Example:
        item = find_in_list(result, "content.LabTestEvent", "hasLabTest.hasCode.termid", "2093-3")

    Returns the matching item or None.
    """
    items = get_path(result, list_path)
    if not isinstance(items, list):
        return None

    for item in items:
        if get_path(item, match_path) == match_value:
            return item

    return None
