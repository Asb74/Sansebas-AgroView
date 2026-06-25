from decimal import Decimal

import pytest

from utils.number_utils import to_float_safe


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, 0.0),
        ("", 0.0),
        (123, 123.0),
        (123.45, 123.45),
        (Decimal("123.45"), 123.45),
        ("123", 123.0),
        ("123.45", 123.45),
        ("123,45", 123.45),
        ("1.234,56", 1234.56),
        ("1,234.56", 1234.56),
    ],
)
def test_to_float_safe_accepts_supported_formats(value, expected):
    assert to_float_safe(value) == expected


def test_to_float_safe_returns_default_for_invalid_values(caplog):
    caplog.set_level("DEBUG", logger="utils.number_utils")
    assert to_float_safe("no-numero", default=-1.5) == -1.5
    assert "No se pudo convertir a float" in caplog.text
