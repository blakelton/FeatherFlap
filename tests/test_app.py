from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

import featherflap.server.routes as routes
from featherflap.hardware import PIRUnavailable, RGBLedUnavailable, PicameraUnavailable
from featherflap.server.app import create_application


@pytest.fixture()
def client() -> TestClient:
    app = create_application()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def immediate_to_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    async def immediate(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(routes.asyncio, "to_thread", immediate)


def test_create_application() -> None:
    app = create_application()
    assert app.title == "FeatherFlap Diagnostics API"
    paths = {route.path for route in app.routes}
    assert "/" in paths


def test_pir_status_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_read_pir_states(pins):
        return {int(pins[0]): 1, int(pins[1]): 0} if pins else {}

    monkeypatch.setattr(routes, "read_pir_states", fake_read_pir_states)
    response = client.get("/api/status/pir")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["states"] == {"17": 1, "27": 0}


def test_pir_status_unavailable(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_unavailable(_pins):
        raise PIRUnavailable("Sensors unavailable")

    monkeypatch.setattr(routes, "read_pir_states", raise_unavailable)
    response = client.get("/api/status/pir")
    assert response.status_code == 503
    assert response.json()["detail"] == "Sensors unavailable"


def test_rgb_led_color_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_set_rgb_led_color(pins, red, green, blue, hold_seconds):
        captured["pins"] = tuple(pins)
        captured["values"] = (red, green, blue, hold_seconds)

    monkeypatch.setattr(routes, "set_rgb_led_color", fake_set_rgb_led_color)
    response = client.post(
        "/api/tests/rgb-led/color",
        json={"red": 12, "green": 34, "blue": 56, "hold_seconds": 0.5},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["status"] == "ok"
    assert payload["result"]["summary"] == "RGB LED set to #0C2238."
    assert captured["pins"] == (24, 23, 18)
    assert captured["values"] == (12, 34, 56, 0.5)


def test_rgb_led_color_unavailable(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_unavailable(*_args, **_kwargs):
        raise RGBLedUnavailable("LED hardware not ready")

    monkeypatch.setattr(routes, "set_rgb_led_color", raise_unavailable)
    response = client.post("/api/tests/rgb-led/color", json={"red": 0, "green": 0, "blue": 0})
    assert response.status_code == 503
    assert response.json()["detail"] == "LED hardware not ready"


def test_camera_frame_csi_success(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes, "capture_picamera_jpeg", lambda *args, **kwargs: b"frame")
    response = client.get("/api/camera/frame?source=csi")
    assert response.status_code == 200
    assert response.content == b"frame"


def test_camera_frame_csi_unavailable(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_unavailable(*_args, **_kwargs):
        raise PicameraUnavailable("CSI camera missing")

    monkeypatch.setattr(routes, "capture_picamera_jpeg", raise_unavailable)
    response = client.get("/api/camera/frame?source=csi")
    assert response.status_code == 503
    assert response.json()["detail"] == "CSI camera missing"


def test_read_configuration_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        temperature_unit=routes.TemperatureUnit.CELSIUS,
        pir_pins=[17, 27],
        motion_poll_interval_seconds=0.5,
        camera_device=1,
        camera_record_width=800,
        camera_record_height=600,
        camera_record_fps=20.0,
        recordings_path=Path("recordings"),
        recording_max_seconds=45,
        recording_min_gap_seconds=60,
    )
    monkeypatch.setattr(routes, "get_settings", lambda: settings)
    response = client.get("/api/config")
    assert response.status_code == 200
    payload = response.json()
    assert payload["temperature"]["unit"] == "celsius"
    assert payload["pir"]["pins"] == [17, 27]
    assert payload["camera"]["device"] == 1
    assert payload["recording"]["max_seconds"] == 45


def test_update_configuration_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_update(settings_dict):
        captured.update(settings_dict)
        return SimpleNamespace(
            temperature_unit=settings_dict["temperature_unit"],
            pir_pins=settings_dict["pir_pins"],
            motion_poll_interval_seconds=settings_dict["motion_poll_interval_seconds"],
            camera_device=settings_dict["camera_device"],
            camera_record_width=settings_dict["camera_record_width"],
            camera_record_height=settings_dict["camera_record_height"],
            camera_record_fps=settings_dict["camera_record_fps"],
            recordings_path=Path(settings_dict["recordings_path"]),
            recording_max_seconds=settings_dict["recording_max_seconds"],
            recording_min_gap_seconds=settings_dict["recording_min_gap_seconds"],
        )

    monkeypatch.setattr(routes, "update_settings", fake_update)
    payload = {
        "temperature": {"unit": "fahrenheit"},
        "pir": {"pins": [5, 6], "motion_poll_interval_seconds": 0.75},
        "camera": {"device": 2, "record_width": 1024, "record_height": 768, "record_fps": 25},
        "recording": {"path": "/tmp/rec", "max_seconds": 60, "min_gap_seconds": 10},
    }
    response = client.put("/api/config", json=payload)
    assert response.status_code == 200
    assert captured["temperature_unit"] == routes.TemperatureUnit.FAHRENHEIT
    assert captured["pir_pins"] == [5, 6]
    assert captured["recordings_path"] == "/tmp/rec"
    assert response.json()["message"] == "Settings updated."


def test_system_status_endpoint(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    expected = {
        "timestamp": "2024-01-01T00:00:00+00:00",
        "load": {"1m": 0.1, "5m": 0.2, "15m": 0.3},
        "cpu_percent": 42.0,
        "cpu_count": 4,
        "memory": {"total_bytes": 1024.0, "available_bytes": 512.0, "used_bytes": 512.0, "percent_used": 50.0},
        "storage": {"path": "/tmp", "total_bytes": 2048.0, "used_bytes": 1024.0, "free_bytes": 1024.0},
        "temperature": {"celsius": 40.0, "preferred": {"unit": "celsius", "value": 40.0}},
    }
    monkeypatch.setattr(routes, "_collect_system_status", lambda _settings: expected)
    response = client.get("/api/status/system")
    assert response.status_code == 200
    assert response.json() == expected
