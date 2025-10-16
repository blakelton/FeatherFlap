"""API routes for the FeatherFlap hardware diagnostics server."""

from __future__ import annotations

import asyncio
import os
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from starlette.concurrency import iterate_in_threadpool

from ..config import DEFAULT_CAMERA_DEVICE_INDEX, DEFAULT_UPTIME_I2C_ADDRESSES, get_settings
from ..hardware import (
    CameraUnavailable,
    HardwareStatus,
    HardwareTestRegistry,
    capture_jpeg_frame,
    mjpeg_stream,
    read_environment,
    read_ups,
)
from ..hardware.i2c import SMBusNotAvailable
from ..logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

STATUS_PRIORITY = {
    HardwareStatus.ERROR.value: 3,
    HardwareStatus.WARNING.value: 2,
    HardwareStatus.SKIPPED.value: 1,
    HardwareStatus.OK.value: 0,
}

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>FeatherFlap Hardware Diagnostics</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root {
      color-scheme: light dark;
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    }
    body {
      margin: 0 auto;
      padding: 1.5rem;
      max-width: 960px;
    }
    h1, h2 {
      margin-top: 0;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
    }
    .card {
      border: 1px solid rgba(0,0,0,0.1);
      border-radius: 8px;
      padding: 1rem;
      background: rgba(255,255,255,0.05);
    }
    button {
      margin-top: 0.5rem;
      padding: 0.5rem 1rem;
      border-radius: 4px;
      border: 1px solid transparent;
      font-weight: 600;
      cursor: pointer;
    }
    .status {
      font-weight: 700;
      margin-top: 0.75rem;
    }
    .status.ok { color: #1a7f37; }
    .status.warning { color: #9f580a; }
    .status.error { color: #b42318; }
    .status.skipped { color: #4a5568; }
    pre {
      background: rgba(0,0,0,0.05);
      padding: 0.75rem;
      overflow-x: auto;
      font-size: 0.85rem;
      border-radius: 6px;
    }
  </style>
</head>
<body>
  <header>
    <h1>FeatherFlap Hardware Diagnostics</h1>
    <p>Run checks against the Raspberry Pi Zero 2 W hardware stack. Use the buttons below to execute individual diagnostics or all tests at once.</p>
    <button id="run-all">Run full suite</button>
  </header>
  <section>
    <h2>Available Diagnostics</h2>
    <div id="cards" class="grid" role="list"></div>
  </section>
  <script type="text/javascript">
    const cardsDiv = document.getElementById("cards");
    const runAllButton = document.getElementById("run-all");

    function createCard(test) {
      const card = document.createElement("article");
      card.className = "card";
      card.id = `card-${test.id}`;
      card.innerHTML = `
        <h3>${test.name}</h3>
        <p>${test.description}</p>
        <button data-test="${test.id}" aria-label="Run ${test.name} diagnostic">Run test</button>
        <div class="status" id="status-${test.id}"></div>
        <pre id="details-${test.id}" hidden></pre>
      `;
      return card;
    }

    function renderStatus(testId, result) {
      const statusEl = document.getElementById(`status-${testId}`);
      const detailsEl = document.getElementById(`details-${testId}`);
      statusEl.className = `status ${result.status}`;
      statusEl.textContent = `${result.status.toUpperCase()}: ${result.summary}`;

      if (result.details && Object.keys(result.details).length > 0) {
        detailsEl.hidden = false;
        detailsEl.textContent = JSON.stringify(result.details, null, 2);
      } else {
        detailsEl.hidden = true;
        detailsEl.textContent = "";
      }
    }

    async function fetchTests() {
      const response = await fetch("/api/tests");
      const tests = await response.json();
      tests.forEach(test => cardsDiv.appendChild(createCard(test)));
    }

    async function runTest(testId) {
      const response = await fetch(`/api/tests/${testId}`, { method: "POST" });
      if (!response.ok) {
        renderStatus(testId, { status: "error", summary: `Request failed: ${response.status}`, details: {} });
        return;
      }
      const payload = await response.json();
      renderStatus(testId, payload.result);
    }

    async function runAll() {
      runAllButton.disabled = true;
      runAllButton.textContent = "Running...";
      try {
        const response = await fetch("/api/tests/run-all", { method: "POST" });
        const payload = await response.json();
        payload.results.forEach(result => renderStatus(result.id, result));
        alert(`Full suite finished. Overall status: ${payload.overall_status.toUpperCase()}`);
      } catch (error) {
        alert("Failed to run diagnostics: " + error);
      } finally {
        runAllButton.disabled = false;
        runAllButton.textContent = "Run full suite";
      }
    }

    cardsDiv.addEventListener("click", (event) => {
      const target = event.target;
      if (target.tagName === "BUTTON" && target.dataset.test) {
        runTest(target.dataset.test);
      }
    });

    runAllButton.addEventListener("click", runAll);
    fetchTests();
  </script>
</body>
</html>
"""


def get_registry(request: Request) -> HardwareTestRegistry:
    """Retrieve the shared hardware registry from the application state."""

    registry = getattr(request.app.state, "registry", None)
    if registry is None:
        logger.error("Hardware registry not initialised on application state")
        raise RuntimeError("Hardware registry not initialised.")
    logger.debug("Retrieved hardware registry with %d tests", len(registry.tests))
    return registry


def _resolve_ups_addresses(settings) -> List[int]:
    addresses = list(settings.uptime_i2c_addresses or [])
    env_override = os.getenv("UPTIME_I2C_ADDR")
    if env_override:
        try:
            addresses.insert(0, int(env_override, 0))
        except ValueError:
            logger.warning("Ignoring invalid UPTIME_I2C_ADDR override: %s", env_override)
            pass
    if not addresses:
        addresses = list(DEFAULT_UPTIME_I2C_ADDRESSES)
    resolved = list(dict.fromkeys(addresses))
    logger.debug("Resolved UPS addresses: %s", [hex(addr) for addr in resolved])
    return resolved


def _aggregate_status(results: List[Dict[str, str]]) -> str:
    highest = max((STATUS_PRIORITY.get(result["status"], 0) for result in results), default=0)
    for status, score in STATUS_PRIORITY.items():
        if score == highest:
            return status
    return HardwareStatus.OK.value


@router.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    """Serve the HTML dashboard."""

    logger.debug("Serving dashboard HTML")
    return HTMLResponse(content=DASHBOARD_HTML)


@router.get("/api/tests")
async def list_tests(registry: HardwareTestRegistry = Depends(get_registry)) -> List[Dict[str, str]]:
    """Return metadata about available hardware diagnostics."""

    tests = registry.list_tests()
    logger.debug("Listing %d diagnostic tests", len(tests))
    return tests


@router.get("/api/status/environment")
async def environment_status() -> Dict[str, object]:
    """Return a snapshot of the environmental sensors."""

    settings = get_settings()
    logger.debug("Requesting environment snapshot (bus=%s)", settings.i2c_bus_id)
    try:
        snapshot = await asyncio.to_thread(
            read_environment,
            settings.i2c_bus_id,
            settings.aht20_i2c_address,
            settings.bmp280_i2c_address,
        )
    except SMBusNotAvailable as exc:
        logger.warning("SMBus not available for environment snapshot: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("Environment snapshot raised runtime error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if snapshot.errors and not snapshot.results:
        status = HardwareStatus.ERROR.value
    elif snapshot.errors:
        status = HardwareStatus.WARNING.value
    else:
        status = HardwareStatus.OK.value
    logger.info(
        "Environment snapshot completed with status=%s (results=%d errors=%d)",
        status,
        len(snapshot.results),
        len(snapshot.errors),
    )
    return {"status": status, "results": snapshot.results, "errors": snapshot.errors}


@router.get("/api/status/ups")
async def ups_status() -> Dict[str, object]:
    """Return the latest UPS telemetry."""

    settings = get_settings()
    addresses = _resolve_ups_addresses(settings)
    logger.debug("Querying UPS telemetry on bus=%s addresses=%s", settings.i2c_bus_id, [hex(a) for a in addresses])
    try:
        readings = await asyncio.to_thread(read_ups, settings.i2c_bus_id, addresses)
    except SMBusNotAvailable as exc:
        logger.warning("SMBus not available for UPS telemetry: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("UPS telemetry read failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    logger.info("UPS telemetry read succeeded at address %s", readings.to_dict().get("address"))
    return {"status": HardwareStatus.OK.value, "readings": readings.to_dict()}


@router.get("/api/camera/frame")
async def camera_frame() -> Response:
    """Capture a single JPEG frame from the USB camera."""

    settings = get_settings()
    device = settings.camera_device if settings.camera_device is not None else DEFAULT_CAMERA_DEVICE_INDEX
    logger.debug("Capturing single camera frame from device %s", device)
    try:
        frame = await asyncio.to_thread(capture_jpeg_frame, device)
    except CameraUnavailable as exc:
        logger.warning("USB camera unavailable for single frame capture: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    logger.info("Captured %d bytes from USB camera", len(frame))
    return Response(content=frame, media_type="image/jpeg")


@router.get("/api/camera/stream")
async def camera_stream() -> StreamingResponse:
    """Stream MJPEG frames from the USB camera."""

    settings = get_settings()
    device = settings.camera_device if settings.camera_device is not None else DEFAULT_CAMERA_DEVICE_INDEX
    logger.debug("Opening camera stream for device %s", device)
    try:
        generator = mjpeg_stream(device)
    except CameraUnavailable as exc:
        logger.warning("USB camera unavailable for streaming: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    logger.info("USB camera stream initialised for device %s", device)
    return StreamingResponse(
        iterate_in_threadpool(generator),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.post("/api/tests/run-all")
async def run_all_tests(registry: HardwareTestRegistry = Depends(get_registry)) -> Dict[str, object]:
    """Execute the entire diagnostic suite."""

    results = await asyncio.to_thread(registry.run_all)
    payload = [result.to_dict() for result in results]
    logger.info("Executed full diagnostic suite (%d tests)", len(payload))
    return {
        "overall_status": _aggregate_status(payload),
        "results": payload,
    }


@router.post("/api/tests/{test_id}")
async def run_single_test(
    test_id: str,
    registry: HardwareTestRegistry = Depends(get_registry),
) -> Dict[str, object]:
    """Execute a single diagnostic by identifier."""

    try:
        result = await asyncio.to_thread(registry.run_test, test_id)
    except KeyError as exc:
        logger.error("Requested diagnostic does not exist: %s", test_id)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    logger.info("Executed diagnostic '%s' with status %s", test_id, result.status.value)
    return {"result": result.to_dict()}
