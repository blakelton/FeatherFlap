import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

import featherflap.server.routes as routes
from featherflap.hardware import PIRUnavailable, RGBLedUnavailable
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
