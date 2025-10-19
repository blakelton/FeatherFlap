import pytest

pytest.importorskip("pydantic")

from featherflap.config import AppSettings


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("17", [17]),
        ("17,27", [17, 27]),
        ("17 27", [17, 27]),
        ("[17, 27]", [17, 27]),
        ('["17", "0x1B"]', [17, 27]),
    ],
)
def test_pir_pins_parsing_from_environment(monkeypatch: pytest.MonkeyPatch, value: str, expected: list[int]) -> None:
    monkeypatch.setenv("FEATHERFLAP_PIR_PINS", value)
    settings = AppSettings()
    assert settings.pir_pins == expected


def test_pir_pins_parsing_accepts_direct_override() -> None:
    settings = AppSettings(pir_pins="0x11")
    assert settings.pir_pins == [17]
