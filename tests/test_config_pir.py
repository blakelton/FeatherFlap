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


def test_default_ups_settings() -> None:
    settings = AppSettings()
    assert settings.uptime_i2c_addresses == [0x40]
    assert settings.uptime_shunt_resistance_ohms == pytest.approx(0.01)


def test_sleep_windows_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEATHERFLAP_SLEEP_WINDOWS", '["22:00-06:00", {"start": "13:30", "end": "14:15"}]')
    settings = AppSettings()
    assert settings.sleep_windows == [
        {"start": "22:00", "end": "06:00"},
        {"start": "13:30", "end": "14:15"},
    ]


def test_mode_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEATHERFLAP_MODE", "run")
    settings = AppSettings()
    assert settings.mode.value == "run"
