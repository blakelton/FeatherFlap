"""API routes for the FeatherFlap hardware diagnostics server."""

from __future__ import annotations

import asyncio
import os
from contextlib import nullcontext
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from starlette.concurrency import iterate_in_threadpool

from pydantic import BaseModel, Field

from ..config import DEFAULT_CAMERA_DEVICE_INDEX, DEFAULT_UPTIME_I2C_ADDRESSES, get_settings
from ..hardware import (
    CameraUnavailable,
    HardwareStatus,
    HardwareTestRegistry,
    HardwareTestResult,
    PIRUnavailable,
    RGBLedUnavailable,
    capture_jpeg_frame,
    mjpeg_stream,
    read_environment,
    read_pir_states,
    read_ups,
    set_rgb_led_color,
)
from ..hardware.i2c import SMBusNotAvailable
from ..logger import get_logger
from ..runtime import CameraBusyError

router = APIRouter()
logger = get_logger(__name__)

STATUS_PRIORITY = {
    HardwareStatus.ERROR.value: 3,
    HardwareStatus.WARNING.value: 2,
    HardwareStatus.SKIPPED.value: 1,
    HardwareStatus.OK.value: 0,
}


class RGBLedColorRequest(BaseModel):
    red: int = Field(0, ge=0, le=255)
    green: int = Field(0, ge=0, le=255)
    blue: int = Field(0, ge=0, le=255)
    hold_seconds: float = Field(1.0, ge=0.0, le=10.0)

    @property
    def hex_code(self) -> str:
        return f"{self.red:02X}{self.green:02X}{self.blue:02X}"


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>FeatherFlap Control Center</title>
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <style>
    :root {
      color-scheme: light dark;
      font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    }
    body {
      margin: 0 auto;
      padding: 1.5rem;
      max-width: 1100px;
      line-height: 1.5;
    }
    .page-header {
      margin-bottom: 1rem;
    }
    .page-header h1 {
      margin: 0 0 0.25rem 0;
    }
    .tabs {
      display: flex;
      gap: 0.5rem;
      margin-bottom: 1rem;
    }
    .tab-button {
      appearance: none;
      border: 1px solid rgba(0,0,0,0.15);
      background: rgba(255,255,255,0.05);
      padding: 0.5rem 1rem;
      border-radius: 999px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s ease;
    }
    .tab-button:hover {
      background: rgba(37,99,235,0.12);
    }
    .tab-button.active {
      background: #2563eb;
      color: #fff;
      border-color: #2563eb;
    }
    .tab-panel {
      display: none;
    }
    .tab-panel.active {
      display: block;
    }
    .grid {
      display: grid;
      gap: 1rem;
    }
    .home-grid {
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    }
    .card {
      border: 1px solid rgba(0,0,0,0.1);
      border-radius: 12px;
      padding: 1rem;
      background: rgba(255,255,255,0.05);
      box-shadow: 0 1px 2px rgba(15,23,42,0.08);
    }
    .card h2 {
      margin-top: 0;
      margin-bottom: 0.5rem;
    }
    .card-header {
      margin-bottom: 0.75rem;
    }
    .camera-controls {
      display: flex;
      gap: 1rem;
      flex-wrap: wrap;
      margin-bottom: 0.75rem;
    }
    .camera-controls label {
      font-weight: 600;
      display: flex;
      align-items: center;
      gap: 0.35rem;
    }
    .camera-viewer {
      position: relative;
      border-radius: 8px;
      overflow: hidden;
      min-height: 220px;
      background: rgba(15,23,42,0.12);
      display: flex;
      align-items: center;
      justify-content: center;
    }
    #camera-stream {
      max-width: 100%;
      width: 100%;
      height: auto;
      display: block;
    }
    #camera-placeholder {
      text-align: center;
      padding: 2rem 1rem;
    }
    .status-table {
      width: 100%;
      border-collapse: collapse;
    }
    .status-table th,
    .status-table td {
      padding: 0.5rem;
      border-bottom: 1px solid rgba(0,0,0,0.1);
      text-align: left;
      vertical-align: top;
    }
    .status-table tbody tr:last-child td,
    .status-table tbody tr:last-child th {
      border-bottom: none;
    }
    .badge {
      display: inline-block;
      padding: 0.25rem 0.65rem;
      border-radius: 999px;
      font-size: 0.85rem;
      font-weight: 600;
      background: rgba(15,23,42,0.12);
    }
    .status-active {
      background: #1a7f37;
      color: #fff;
    }
    .status-idle {
      background: #4a5568;
      color: #fff;
    }
    .status-alert {
      background: #b42318;
      color: #fff;
    }
    .muted {
      color: rgba(15,23,42,0.65);
      font-size: 0.9rem;
      margin-top: 0.5rem;
    }
    .danger {
      color: #b42318;
    }
    .stat-list {
      display: grid;
      gap: 0.4rem;
    }
    .stat-list div {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
    }
    .stat-list dt {
      font-weight: 600;
    }
    .stat-list dd {
      margin: 0;
      font-variant-numeric: tabular-nums;
    }
    form label {
      display: flex;
      flex-direction: column;
      gap: 0.35rem;
      font-weight: 600;
      margin-bottom: 0.75rem;
    }
    form input,
    form button {
      font: inherit;
    }
    form input[type="color"] {
      border: none;
      width: 100%;
      height: 2.5rem;
      padding: 0;
      cursor: pointer;
    }
    form input[type="number"] {
      padding: 0.4rem 0.5rem;
      border-radius: 6px;
      border: 1px solid rgba(0,0,0,0.2);
      background: rgba(255,255,255,0.1);
    }
    form button {
      padding: 0.6rem 1rem;
      border-radius: 8px;
      border: none;
      background: #2563eb;
      color: #fff;
      font-weight: 600;
      cursor: pointer;
    }
    form button:disabled {
      background: #94a3b8;
      cursor: not-allowed;
    }
    .testing-header {
      display: flex;
      flex-wrap: wrap;
      gap: 1rem;
      align-items: center;
      margin-bottom: 1rem;
    }
    .testing-header h2 {
      margin: 0;
    }
    .testing-header button {
      margin-left: auto;
      padding: 0.6rem 1rem;
      border-radius: 8px;
      border: none;
      background: #1a7f37;
      color: #fff;
      font-weight: 600;
      cursor: pointer;
    }
    @media (max-width: 640px) {
      body {
        padding: 1rem;
      }
      .testing-header {
        flex-direction: column;
        align-items: flex-start;
      }
      .testing-header button {
        margin-left: 0;
      }
    }
  </style>
</head>
<body>
  <header class="page-header">
    <h1>FeatherFlap Control Center</h1>
    <p class="muted">Monitor both bird houses, review power data, and run diagnostics.</p>
  </header>
  <nav class="tabs" role="tablist">
    <button class="tab-button active" type="button" data-tab="home">Home</button>
    <button class="tab-button" type="button" data-tab="testing">Diagnostics</button>
  </nav>
  <main>
    <section id="home-tab" class="tab-panel active" role="tabpanel" aria-labelledby="home">
      <article class="card camera-card">
        <div class="card-header">
          <h2>Live Camera</h2>
          <p class="muted">Select a camera to start streaming. Only one feed runs at a time.</p>
        </div>
        <div class="camera-controls">
          <label><input type="radio" name="camera-select" value="off" checked /> Off</label>
          <label><input type="radio" name="camera-select" value="0" /> House 1</label>
          <label><input type="radio" name="camera-select" value="1" /> House 2</label>
        </div>
        <div class="camera-viewer">
          <img id="camera-stream" alt="FeatherFlap camera stream" hidden />
          <div id="camera-placeholder">
            <p class="muted">Camera feed is off.</p>
          </div>
        </div>
        <p id="camera-status" class="muted">Select a camera to start streaming.</p>
      </article>

      <section class="grid home-grid">
        <article class="card">
          <h2>Bird Houses</h2>
          <table class="status-table" aria-describedby="pir-status">
            <thead>
              <tr>
                <th scope="col">House</th>
                <th scope="col">Camera</th>
                <th scope="col">Motion Sensor</th>
              </tr>
            </thead>
            <tbody>
              <tr data-house-row="1">
                <th scope="row">House 1</th>
                <td><span class="camera-state badge status-idle" data-house-camera="1">Standby</span></td>
                <td>
                  <span class="pir-state badge status-idle" data-house-pir="1">Pending</span>
                  <div class="muted pir-pin" data-house-pir-pin="1"></div>
                </td>
              </tr>
              <tr data-house-row="2">
                <th scope="row">House 2</th>
                <td><span class="camera-state badge status-idle" data-house-camera="2">Standby</span></td>
                <td>
                  <span class="pir-state badge status-idle" data-house-pir="2">Pending</span>
                  <div class="muted pir-pin" data-house-pir-pin="2"></div>
                </td>
              </tr>
            </tbody>
          </table>
          <p id="pir-status" class="muted"></p>
        </article>

        <article class="card">
          <h2>Environment</h2>
          <dl class="stat-list">
            <div>
              <dt>Temperature</dt>
              <dd id="environment-temperature">--</dd>
            </div>
            <div>
              <dt>Humidity</dt>
              <dd id="environment-humidity">--</dd>
            </div>
            <div>
              <dt>Pressure</dt>
              <dd id="environment-pressure">--</dd>
            </div>
          </dl>
          <p id="environment-status" class="muted"></p>
        </article>

        <article class="card">
          <h2>Power</h2>
          <dl class="stat-list">
            <div>
              <dt>Bus Voltage</dt>
              <dd id="power-voltage">--</dd>
            </div>
            <div>
              <dt>Current</dt>
              <dd id="power-current">--</dd>
            </div>
            <div>
              <dt>Power</dt>
              <dd id="power-consumption">--</dd>
            </div>
            <div>
              <dt>Flow</dt>
              <dd id="power-flow">--</dd>
            </div>
          </dl>
          <p id="power-status" class="muted"></p>
        </article>

        <article class="card">
          <h2>RGB LED Test</h2>
          <form id="rgb-led-form">
            <label>
              Color
              <input type="color" id="rgb-led-picker" value="#ff0000" />
            </label>
            <label>
              Hold (seconds)
              <input type="number" id="rgb-led-hold" min="0" max="10" step="0.1" value="1" />
            </label>
            <button type="submit">Test Color</button>
          </form>
          <p id="rgb-led-feedback" class="muted"></p>
        </article>
      </section>
    </section>

    <section id="testing-tab" class="tab-panel" role="tabpanel" aria-labelledby="testing">
      <div class="testing-header">
        <div>
          <h2>Diagnostics</h2>
          <p class="muted">Run individual tests or the full hardware suite.</p>
        </div>
        <button id="run-all" type="button">Run full suite</button>
      </div>
      <div id="cards" class="grid" role="list"></div>
    </section>
  </main>

  <script type="text/javascript">
    (function () {
      var tabButtons = Array.prototype.slice.call(document.querySelectorAll(".tab-button"));
      var panels = {
        home: document.getElementById("home-tab"),
        testing: document.getElementById("testing-tab")
      };

      function showTab(id) {
        Object.keys(panels).forEach(function (panelId) {
          var panel = panels[panelId];
          var button = document.querySelector('.tab-button[data-tab="' + panelId + '"]');
          var isActive = panelId === id;
          if (panel) {
            panel.classList.toggle("active", isActive);
          }
          if (button) {
            button.classList.toggle("active", isActive);
          }
        });
      }

      tabButtons.forEach(function (button) {
        button.addEventListener("click", function () {
          showTab(this.dataset.tab || "home");
        });
      });

      var defaultTabButton = null;
      for (var i = 0; i < tabButtons.length; i += 1) {
        if (tabButtons[i].classList.contains("active")) {
          defaultTabButton = tabButtons[i];
          break;
        }
      }
      if (!defaultTabButton) {
        defaultTabButton = tabButtons[0];
      }
      if (defaultTabButton) {
        showTab(defaultTabButton.dataset.tab || "home");
      }

      var cardsDiv = document.getElementById("cards");
      var runAllButton = document.getElementById("run-all");

      function createCard(test) {
        var card = document.createElement("article");
        card.className = "card";
        card.id = "card-" + test.id;
        card.innerHTML = [
          "<h3>" + test.name + "</h3>",
          "<p>" + test.description + "</p>",
          '<button data-test="' + test.id + '" aria-label="Run ' + test.name + ' diagnostic">Run test</button>',
          '<div class="status" id="status-' + test.id + '"></div>',
          '<pre id="details-' + test.id + '" hidden></pre>'
        ].join("");
        return card;
      }

      function renderStatus(testId, result) {
        var statusEl = document.getElementById("status-" + testId);
        var detailsEl = document.getElementById("details-" + testId);
        if (!statusEl || !detailsEl) {
          return;
        }
        statusEl.className = "status " + result.status;
        statusEl.textContent = result.status.toUpperCase() + ": " + result.summary;
        if (result.details && Object.keys(result.details).length > 0) {
          detailsEl.hidden = false;
          detailsEl.textContent = JSON.stringify(result.details, null, 2);
        } else {
          detailsEl.hidden = true;
          detailsEl.textContent = "";
        }
      }

      async function fetchTests() {
        if (!cardsDiv) {
          return;
        }
        try {
          const response = await fetch("/api/tests");
          if (!response.ok) {
            throw new Error("HTTP " + response.status);
          }
          const tests = await response.json();
          tests.forEach(function (test) {
            cardsDiv.appendChild(createCard(test));
          });
        } catch (error) {
          console.error("Failed to load tests:", error);
        }
      }

      async function runTest(testId) {
        try {
          const response = await fetch("/api/tests/" + testId, { method: "POST" });
          if (!response.ok) {
            renderStatus(testId, { status: "error", summary: "Request failed: " + response.status, details: {} });
            return;
          }
          const payload = await response.json();
          renderStatus(testId, payload.result);
        } catch (error) {
          renderStatus(testId, { status: "error", summary: "Request failed: " + error.message, details: {} });
        }
      }

      async function runAll() {
        if (!runAllButton) {
          return;
        }
        runAllButton.disabled = true;
        runAllButton.textContent = "Running...";
        try {
          const response = await fetch("/api/tests/run-all", { method: "POST" });
          if (!response.ok) {
            throw new Error("HTTP " + response.status);
          }
          const payload = await response.json();
          if (payload.results) {
            payload.results.forEach(function (result) {
              renderStatus(result.id, result);
            });
          }
          window.alert("Full suite finished. Overall status: " + (payload.overall_status || "unknown").toUpperCase());
        } catch (error) {
          window.alert("Failed to run diagnostics: " + error.message);
        } finally {
          runAllButton.disabled = false;
          runAllButton.textContent = "Run full suite";
        }
      }

      if (runAllButton) {
        runAllButton.addEventListener("click", runAll);
      }

      if (cardsDiv) {
        cardsDiv.addEventListener("click", function (event) {
          var target = event.target;
          if (target.tagName === "BUTTON" && target.dataset.test) {
            runTest(target.dataset.test);
          }
        });
      }

      fetchTests();

      var cameraRadios = document.querySelectorAll('input[name="camera-select"]');
      var cameraImg = document.getElementById("camera-stream");
      var cameraPlaceholder = document.getElementById("camera-placeholder");
      var cameraStatus = document.getElementById("camera-status");

      var houseRows = [
        {
          order: 0,
          cameraIndex: 0,
          cameraCell: document.querySelector('[data-house-row="1"] .camera-state'),
          pirState: document.querySelector('[data-house-row="1"] .pir-state'),
          pirPinLabel: document.querySelector('[data-house-row="1"] .pir-pin')
        },
        {
          order: 1,
          cameraIndex: 1,
          cameraCell: document.querySelector('[data-house-row="2"] .camera-state'),
          pirState: document.querySelector('[data-house-row="2"] .pir-state'),
          pirPinLabel: document.querySelector('[data-house-row="2"] .pir-pin')
        }
      ];
      var pirStatus = document.getElementById("pir-status");
      var envTemp = document.getElementById("environment-temperature");
      var envHumidity = document.getElementById("environment-humidity");
      var envPressure = document.getElementById("environment-pressure");
      var envStatus = document.getElementById("environment-status");
      var powerVoltage = document.getElementById("power-voltage");
      var powerCurrent = document.getElementById("power-current");
      var powerConsumption = document.getElementById("power-consumption");
      var powerFlow = document.getElementById("power-flow");
      var powerStatus = document.getElementById("power-status");
      var rgbLedForm = document.getElementById("rgb-led-form");
      var rgbLedPicker = document.getElementById("rgb-led-picker");
      var rgbLedHold = document.getElementById("rgb-led-hold");
      var rgbLedFeedback = document.getElementById("rgb-led-feedback");

      var activeCamera = null;
      var latestPirStates = {};
      var pirPinOrder = [];
      var pollTimers = [];

      function setBadge(element, text, stateClass) {
        if (!element) {
          return;
        }
        element.textContent = text;
        element.classList.remove("status-active", "status-idle", "status-alert");
        if (stateClass) {
          element.classList.add(stateClass);
        }
      }

      function updateCameraStatus(text, isError) {
        if (!cameraStatus) {
          return;
        }
        cameraStatus.textContent = text;
        cameraStatus.classList.toggle("danger", !!isError);
      }

      function updateHouseRows() {
        houseRows.forEach(function (house) {
          if (!house || !house.cameraCell) {
            return;
          }
          if (activeCamera === house.cameraIndex) {
            setBadge(house.cameraCell, "Active", "status-active");
          } else {
            setBadge(house.cameraCell, "Standby", "status-idle");
          }
          if (!house.pirState) {
            return;
          }
          var pin = pirPinOrder[house.order];
          if (typeof pin === "undefined") {
            setBadge(house.pirState, "Unavailable", "status-alert");
            if (house.pirPinLabel) {
              house.pirPinLabel.textContent = "";
            }
            return;
          }
          if (house.pirPinLabel) {
            house.pirPinLabel.textContent = "GPIO" + pin;
          }
          if (Object.prototype.hasOwnProperty.call(latestPirStates, pin)) {
            var value = latestPirStates[pin];
            setBadge(house.pirState, value ? "Motion" : "Idle", value ? "status-active" : "status-idle");
          } else {
            setBadge(house.pirState, "Pending", "status-idle");
          }
        });
      }

      function selectCameraRadio(value) {
        cameraRadios.forEach(function (radio) {
          radio.checked = radio.value === value;
        });
      }

      function startCameraStream(device) {
        if (!cameraImg || typeof device !== "number") {
          return;
        }
        activeCamera = device;
        if (cameraPlaceholder) {
          cameraPlaceholder.hidden = true;
        }
        cameraImg.hidden = false;
        cameraImg.src = "/api/camera/stream?device=" + device + "&_=" + Date.now();
        updateCameraStatus("Starting camera " + (device + 1) + "...", false);
        updateHouseRows();
      }

      function stopCameraStream(message, isError) {
        activeCamera = null;
        if (cameraImg) {
          cameraImg.removeAttribute("src");
          cameraImg.hidden = true;
        }
        if (cameraPlaceholder) {
          cameraPlaceholder.hidden = false;
        }
        updateCameraStatus(message || "Camera feed is off.", !!isError);
        updateHouseRows();
      }

      function handleCameraSelection(value) {
        if (value === "off") {
          stopCameraStream("Camera feed is off.", false);
          return;
        }
        var device = parseInt(value, 10);
        if (isNaN(device)) {
          stopCameraStream("Camera feed is off.", false);
          selectCameraRadio("off");
          return;
        }
        startCameraStream(device);
      }

      if (cameraImg) {
        cameraImg.addEventListener("load", function () {
          if (activeCamera !== null) {
            updateCameraStatus("Streaming camera " + (activeCamera + 1) + ".", false);
          }
        });
        cameraImg.addEventListener("error", function () {
          selectCameraRadio("off");
          stopCameraStream("Camera stream unavailable.", true);
        });
      }

      if (cameraRadios.length) {
        cameraRadios.forEach(function (radio) {
          radio.addEventListener("change", function () {
            if (!this.checked) {
              return;
            }
            handleCameraSelection(this.value);
          });
        });
      }
      stopCameraStream("Select a camera to start streaming.", false);

      function formatValue(value, unit, fractionDigits) {
        if (typeof value !== "number" || isNaN(value)) {
          return "--";
        }
        var digits = typeof fractionDigits === "number" ? fractionDigits : 2;
        var text = value.toFixed(digits);
        return unit ? text + " " + unit : text;
      }

      async function refreshEnvironment() {
        if (!envTemp || !envHumidity || !envPressure) {
          return;
        }
        try {
          const response = await fetch("/api/status/environment", { cache: "no-store" });
          if (!response.ok) {
            throw new Error("HTTP " + response.status);
          }
          const payload = await response.json();
          const results = payload.results || {};
          const errors = payload.errors || {};
          var aht = results.aht20 || {};
          var bmp = results.bmp280 || {};
          var temperature = typeof aht.temperature_c === "number" ? aht.temperature_c : (typeof bmp.temperature_c === "number" ? bmp.temperature_c : null);
          var humidity = typeof aht.humidity_pct === "number" ? aht.humidity_pct : null;
          var pressure = typeof bmp.pressure_hpa === "number" ? bmp.pressure_hpa : null;

          envTemp.textContent = formatValue(temperature, "°C", 1);
          envHumidity.textContent = formatValue(humidity, "%", 1);
          envPressure.textContent = formatValue(pressure, "hPa", 1);

          if (envStatus) {
            if (Object.keys(errors).length) {
              var errorMessages = Object.keys(errors)
                .map(function (key) { return key + ": " + errors[key]; })
                .join("; ");
              envStatus.textContent = "Sensor issues: " + errorMessages;
            } else {
              envStatus.textContent = "";
            }
          }
        } catch (error) {
          envTemp.textContent = "--";
          envHumidity.textContent = "--";
          envPressure.textContent = "--";
          if (envStatus) {
            envStatus.textContent = "Environment data unavailable: " + error.message;
          }
        }
      }

      async function refreshPowerStatus() {
        if (!powerVoltage || !powerCurrent || !powerConsumption || !powerFlow) {
          return;
        }
        try {
          const response = await fetch("/api/status/ups", { cache: "no-store" });
          if (!response.ok) {
            throw new Error("HTTP " + response.status);
          }
          const payload = await response.json();
          const readings = payload.readings || {};
          var voltage = typeof readings.bus_voltage_v === "number" ? readings.bus_voltage_v : null;
          var current = typeof readings.current_ma === "number" ? readings.current_ma : null;
          var power = typeof readings.power_mw === "number" ? readings.power_mw : null;
          var flow = readings.flow || "unknown";

          powerVoltage.textContent = formatValue(voltage, "V", 2);
          powerCurrent.textContent = typeof current === "number" ? current.toFixed(1) + " mA" : "--";
          powerConsumption.textContent = typeof power === "number" ? power.toFixed(0) + " mW" : "--";
          powerFlow.textContent = flow.charAt(0).toUpperCase() + flow.slice(1);
          if (powerStatus) {
            powerStatus.textContent = "";
          }
        } catch (error) {
          powerVoltage.textContent = "--";
          powerCurrent.textContent = "--";
          powerConsumption.textContent = "--";
          powerFlow.textContent = "--";
          if (powerStatus) {
            powerStatus.textContent = "Power data unavailable: " + error.message;
          }
        }
      }

      async function refreshPirStatus() {
        try {
          const response = await fetch("/api/status/pir", { cache: "no-store" });
          if (!response.ok) {
            throw new Error("HTTP " + response.status);
          }
          const payload = await response.json();
          latestPirStates = payload.states || {};
          var pins = Object.keys(latestPirStates)
            .map(function (key) { return parseInt(key, 10); })
            .filter(function (value) { return !isNaN(value); })
            .sort(function (a, b) { return a - b; });
          pirPinOrder = pins;
          if (pirStatus) {
            pirStatus.textContent = pins.length ? "" : "No PIR sensors detected.";
          }
          updateHouseRows();
        } catch (error) {
          latestPirStates = {};
          pirPinOrder = [];
          if (pirStatus) {
            pirStatus.textContent = "PIR sensors unavailable: " + error.message;
          }
          updateHouseRows();
        }
      }

      function clearPolling() {
        pollTimers.forEach(function (timer) {
          clearInterval(timer);
        });
        pollTimers = [];
      }

      function schedulePolling() {
        clearPolling();
        pollTimers.push(setInterval(refreshPirStatus, 10000));
        pollTimers.push(setInterval(refreshEnvironment, 15000));
        pollTimers.push(setInterval(refreshPowerStatus, 20000));
      }

      refreshPirStatus();
      refreshEnvironment();
      refreshPowerStatus();
      schedulePolling();

      if (rgbLedForm) {
        rgbLedForm.addEventListener("submit", async function (event) {
          event.preventDefault();
          var hex = rgbLedPicker && rgbLedPicker.value ? rgbLedPicker.value : "#000000";
          if (hex.charAt(0) === "#") {
            hex = hex.slice(1);
          }
          if (!/^[0-9a-fA-F]{6}$/.test(hex)) {
            hex = "000000";
          }
          var red = parseInt(hex.slice(0, 2), 16);
          var green = parseInt(hex.slice(2, 4), 16);
          var blue = parseInt(hex.slice(4, 6), 16);
          var holdSeconds = parseFloat(rgbLedHold && rgbLedHold.value ? rgbLedHold.value : "1");
          if (isNaN(holdSeconds)) {
            holdSeconds = 1;
          }
          holdSeconds = Math.max(0, Math.min(10, holdSeconds));

          if (rgbLedFeedback) {
            rgbLedFeedback.textContent = "Sending color command...";
            rgbLedFeedback.classList.remove("danger");
          }

          try {
            const response = await fetch("/api/tests/rgb-led/color", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                red: red,
                green: green,
                blue: blue,
                hold_seconds: holdSeconds
              })
            });
            let payload = null;
            try {
              payload = await response.json();
            } catch (jsonError) {
              payload = null;
            }
            if (!response.ok) {
              var detail = payload && payload.detail ? payload.detail : "HTTP " + response.status;
              throw new Error(detail);
            }
            if (rgbLedFeedback) {
              var summary = payload && payload.result && payload.result.summary ? payload.result.summary : "RGB LED command executed.";
              rgbLedFeedback.textContent = summary;
              rgbLedFeedback.classList.remove("danger");
            }
          } catch (error) {
            if (rgbLedFeedback) {
              rgbLedFeedback.textContent = "RGB LED test failed: " + error.message;
              rgbLedFeedback.classList.add("danger");
            }
          }
        });
      }
    })();
  </script>
</body>
</html>
"""
Retrieve the shared hardware registry from the application state."""

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


def _resolve_camera_device(settings, override: int | None) -> int:
    if override is not None:
        return override
    if settings.camera_device is not None:
        return settings.camera_device
    return DEFAULT_CAMERA_DEVICE_INDEX


def _camera_guard(request: Request, purpose: str):
    coordinator = getattr(request.app.state, "camera_coordinator", None)
    if coordinator is None:
        return nullcontext()
    try:
        return coordinator.acquire(purpose, blocking=False)
    except CameraBusyError as exc:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=str(exc)) from exc


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


@router.get("/api/status/pir")
async def pir_status() -> Dict[str, object]:
    """Return the current PIR motion sensor states."""

    settings = get_settings()
    logger.debug("Requesting PIR sensor states for pins %s", settings.pir_pins)
    try:
        states = await asyncio.to_thread(read_pir_states, settings.pir_pins)
    except PIRUnavailable as exc:
        logger.warning("PIR status unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("PIR status request failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    logger.info("PIR states retrieved: %s", states)
    return {"status": HardwareStatus.OK.value, "states": states}


@router.get("/api/status/ups")
async def ups_status() -> Dict[str, object]:
    """Return the latest UPS telemetry."""

    settings = get_settings()
    addresses = _resolve_ups_addresses(settings)
    logger.debug(
        "Querying UPS telemetry on bus=%s addresses=%s (shunt=%.5fΩ)",
        settings.i2c_bus_id,
        [hex(a) for a in addresses],
        settings.uptime_shunt_resistance_ohms,
    )
    try:
        readings = await asyncio.to_thread(
            read_ups,
            settings.i2c_bus_id,
            addresses,
            settings.uptime_shunt_resistance_ohms,
        )
    except SMBusNotAvailable as exc:
        logger.warning("SMBus not available for UPS telemetry: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("UPS telemetry read failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    details = readings.to_dict()
    logger.info(
        "UPS telemetry read succeeded at address %s (bus=%sV current=%s)",
        details.get("address"),
        details.get("bus_voltage_v"),
        details.get("current_ma"),
    )
    return {"status": HardwareStatus.OK.value, "readings": details}


@router.get("/api/camera/frame")
async def camera_frame(
    request: Request,
    device: int | None = Query(None, ge=0, description="Camera device index."),
) -> Response:
    """Capture a single JPEG frame from the USB camera."""

    settings = get_settings()
    selected_device = _resolve_camera_device(settings, device)
    logger.debug("Capturing single camera frame from device %s", selected_device)
    guard = _camera_guard(request, "snapshot")
    try:
        with guard:
            frame = await asyncio.to_thread(capture_jpeg_frame, selected_device)
    except CameraUnavailable as exc:
        logger.warning("USB camera unavailable for single frame capture: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    logger.info("Captured %d bytes from USB camera", len(frame))
    return Response(content=frame, media_type="image/jpeg")


@router.get("/api/camera/stream")
async def camera_stream(
    request: Request,
    device: int | None = Query(None, ge=0, description="Camera device index."),
) -> StreamingResponse:
    """Stream MJPEG frames from the USB camera."""

    settings = get_settings()
    selected_device = _resolve_camera_device(settings, device)
    logger.debug("Opening camera stream for device %s", selected_device)
    guard = _camera_guard(request, "stream")

    def generator():
        with guard:
            yield from mjpeg_stream(selected_device)

    try:
        stream = iterate_in_threadpool(generator())
    except CameraUnavailable as exc:
        logger.warning("USB camera unavailable for streaming: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    logger.info("USB camera stream initialised for device %s", selected_device)
    return StreamingResponse(
        stream,
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@router.get("/api/run/status")
async def run_status(request: Request) -> Dict[str, object]:
    """Return a snapshot of run-mode controller activity."""

    controller = getattr(request.app.state, "run_controller", None)
    if controller is None:
        raise HTTPException(status_code=404, detail="Run mode is not active.")
    return {"mode": "run", "status": controller.status()}


@router.post("/api/tests/rgb-led/color")
async def rgb_led_color_test(payload: RGBLedColorRequest) -> Dict[str, object]:
    """Allow the user to test arbitrary RGB LED colors."""

    settings = get_settings()
    pins = tuple(settings.rgb_led_pins)
    logger.debug("Executing RGB LED color test (pins=%s payload=%s)", pins, payload.model_dump())
    try:
        await asyncio.to_thread(
            set_rgb_led_color,
            pins,
            payload.red,
            payload.green,
            payload.blue,
            payload.hold_seconds,
        )
    except RGBLedUnavailable as exc:
        logger.warning("RGB LED color test unavailable: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("RGB LED color test failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    result = HardwareTestResult(
        id="rgb-led-color",
        name="RGB LED Color",
        status=HardwareStatus.OK,
        summary=f"RGB LED set to #{payload.hex_code}.",
        details={
            "pins": list(pins),
            "hold_seconds": payload.hold_seconds,
            "color": {
                "red": payload.red,
                "green": payload.green,
                "blue": payload.blue,
            },
        },
    )
    logger.info("RGB LED color test completed successfully")
    return {"result": result.to_dict()}


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
