import pytest

pytest.importorskip("fastapi")

from featherflap.server.app import create_application


def test_create_application() -> None:
    app = create_application()
    assert app.title == "FeatherFlap Diagnostics API"
    # Ensure the dashboard route is registered
    paths = {route.path for route in app.routes}
    assert "/" in paths
