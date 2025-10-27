"""API routes for the FeatherFlap hardware diagnostics server."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import os
from contextlib import nullcontext
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from starlette.concurrency import iterate_in_threadpool

from pydantic import BaseModel, Field

from ..config import (
    DEFAULT_CAMERA_DEVICE_INDEX,
    DEFAULT_UPTIME_I2C_ADDRESSES,
    TemperatureUnit,
    convert_temperature,
    get_settings,
    update_settings,
)
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


class TemperatureSettingsPayload(BaseModel):
    unit: TemperatureUnit = Field(default=TemperatureUnit.CELSIUS)


class PIRSettingsPayload(BaseModel):
    pins: list[int] = Field(default_factory=list)
    motion_poll_interval_seconds: float = Field(0.25, gt=0.0)


class CameraSettingsPayload(BaseModel):
    device: Optional[int] = Field(default=DEFAULT_CAMERA_DEVICE_INDEX, ge=0)
    record_width: int = Field(default=640, gt=0)
    record_height: int = Field(default=480, gt=0)
    record_fps: float = Field(default=15.0, gt=0.0)


class RecordingSettingsPayload(BaseModel):
    path: str = Field(default="recordings")
    max_seconds: int = Field(default=30, gt=0)
    min_gap_seconds: int = Field(default=45, ge=0)


class ConfigurationUpdateRequest(BaseModel):
    temperature: TemperatureSettingsPayload
    pir: PIRSettingsPayload
    camera: CameraSettingsPayload
    recording: RecordingSettingsPayload


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
      max-width: 1200px;
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
      flex-wrap: wrap;
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
    form select,
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
    form input[type="number"],
    form input[type="text"],
    form select {
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
    .system-grid {
      display: grid;
      gap: 1rem;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      margin-bottom: 1rem;
    }
    .spec-value {
      font-size: 1.5rem;
      font-weight: 700;
    }
    .progress {
      width: 100%;
      height: 0.4rem;
      border-radius: 999px;
      background: rgba(15,23,42,0.15);
      overflow: hidden;
      margin-top: 0.35rem;
    }
    .progress span {
      display: block;
      height: 100%;
      background: #2563eb;
      width: 0;
    }
    .charts-grid {
      display: grid;
      gap: 1rem;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    }
    .chart-card canvas {
      width: 100%;
      max-width: 100%;
      display: block;
    }
    .diag-accordion {
      display: flex;
      flex-direction: column;
      gap: 0.75rem;
    }
    details.diagnostic-item {
      border: 1px solid rgba(0,0,0,0.1);
      border-radius: 10px;
      padding: 0.5rem 0.75rem;
      background: rgba(255,255,255,0.03);
    }
    details.diagnostic-item summary {
      list-style: none;
      cursor: pointer;
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      align-items: center;
    }
    details.diagnostic-item summary::-webkit-details-marker {
      display: none;
    }
    .diag-pill {
      padding: 0.25rem 0.75rem;
      border-radius: 999px;
      font-weight: 600;
      font-size: 0.85rem;
    }
    .diag-pill-pass {
      background: #1a7f37;
      color: #fff;
    }
    .diag-pill-fail {
      background: #b42318;
      color: #fff;
    }
    .diag-pill-info {
      background: #475467;
      color: #fff;
    }
    .diag-body {
      margin-top: 0.5rem;
    }
    .diag-body button {
      padding: 0.5rem 0.9rem;
      border-radius: 6px;
      border: none;
      background: #2563eb;
      color: #fff;
      font-weight: 600;
      cursor: pointer;
    }
    .diag-summary {
      margin: 0.5rem 0;
    }
    .config-grid {
      display: grid;
      gap: 1rem;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    }
    .form-actions {
      margin-top: 1rem;
      display: flex;
      flex-wrap: wrap;
      gap: 1rem;
      align-items: center;
    }
    .feedback-success {
      color: #1a7f37;
      font-weight: 600;
    }
    .feedback-error {
      color: #b42318;
      font-weight: 600;
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
      details.diagnostic-item summary {
        flex-direction: column;
        align-items: flex-start;
      }
    }
  </style>
</head>
<body>
  <header class="page-header">
    <h1>FeatherFlap Control Center</h1>
    <p class="muted">Monitor bird houses, tune runtime settings, and run diagnostics.</p>
  </header>
  <nav class="tabs" role="tablist">
    <button class="tab-button active" type="button" data-tab="home">Home</button>
    <button class="tab-button" type="button" data-tab="testing">Diagnostics</button>
    <button class="tab-button" type="button" data-tab="config">Configuration</button>
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
      <article class="card">
        <h2>System Specifications</h2>
        <div class="system-grid">
          <div>
            <p class="muted">CPU Load (1m / 5m / 15m)</p>
            <p class="spec-value" id="spec-load">--</p>
          </div>
          <div>
            <p class="muted">Temperature</p>
            <p class="spec-value" id="spec-temperature">--</p>
          </div>
          <div>
            <p class="muted">Storage</p>
            <p class="spec-value" id="spec-storage">--</p>
            <div class="progress"><span id="storage-progress"></span></div>
          </div>
          <div>
            <p class="muted">Memory</p>
            <p class="spec-value" id="spec-memory">--</p>
            <div class="progress"><span id="memory-progress"></span></div>
          </div>
        </div>
        <div class="charts-grid">
          <article class="card chart-card">
            <h3>CPU Utilisation</h3>
            <canvas id="chart-cpu" width="320" height="120" aria-label="CPU utilisation chart"></canvas>
            <p class="muted" id="cpu-chart-label">--</p>
          </article>
          <article class="card chart-card">
            <h3>Memory Usage</h3>
            <canvas id="chart-ram" width="320" height="120" aria-label="Memory usage chart"></canvas>
            <p class="muted" id="ram-chart-label">--</p>
          </article>
          <article class="card chart-card">
            <h3>Temperature Trend</h3>
            <canvas id="chart-temp" width="320" height="120" aria-label="Temperature chart"></canvas>
            <p class="muted" id="temp-chart-label">--</p>
          </article>
        </div>
      </article>

      <article class="card">
        <div class="testing-header">
          <div>
            <h2>Diagnostics</h2>
            <p class="muted">Run individual tests or the full hardware suite.</p>
          </div>
          <button id="run-all" type="button">Run full suite</button>
        </div>
        <div id="diagnostic-accordion" class="diag-accordion" role="list"></div>
      </article>
    </section>

    <section id="config-tab" class="tab-panel" role="tabpanel" aria-labelledby="config">
      <form id="settings-form">
        <div class="config-grid">
          <article class="card">
            <h2>Temperature</h2>
            <label>
              Display unit
              <select id="temperature-unit"></select>
            </label>
            <p class="muted">Applies to environment readouts and charts.</p>
          </article>
          <article class="card">
            <h2>PIR Sensors</h2>
            <label>
              GPIO pins (comma separated)
              <input type="text" id="pir-pins" placeholder="17,27" />
            </label>
            <label>
              Motion polling interval (seconds)
              <input type="number" id="pir-interval" min="0.05" step="0.05" />
            </label>
          </article>
          <article class="card">
            <h2>Camera</h2>
            <label>
              Default device index
              <input type="number" id="camera-device" min="0" />
            </label>
            <label>
              Capture resolution (width × height)
              <div style="display:flex; gap:0.5rem;">
                <input type="number" id="camera-width" min="160" />
                <input type="number" id="camera-height" min="120" />
              </div>
            </label>
            <label>
              Record FPS
              <input type="number" id="camera-fps" min="1" step="0.5" />
            </label>
          </article>
          <article class="card">
            <h2>Recording</h2>
            <label>
              Storage path
              <input type="text" id="recording-path" />
            </label>
            <label>
              Max clip length (seconds)
              <input type="number" id="recording-max" min="1" />
            </label>
            <label>
              Cooldown between clips (seconds)
              <input type="number" id="recording-gap" min="0" />
            </label>
          </article>
        </div>
        <div class="form-actions">
          <button type="submit">Save settings</button>
          <p id="settings-feedback" class="muted" aria-live="polite"></p>
        </div>
      </form>
    </section>
  </main>

  <script type="text/javascript">
    (function () {
      var tabButtons = Array.prototype.slice.call(document.querySelectorAll(".tab-button"));
      var panels = {
        home: document.getElementById("home-tab"),
        testing: document.getElementById("testing-tab"),
        config: document.getElementById("config-tab")
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

      var defaultTabButton = tabButtons.find(function (btn) { return btn.classList.contains("active"); }) || tabButtons[0];
      if (defaultTabButton) {
        showTab(defaultTabButton.dataset.tab || "home");
      }

      function createMiniChart(canvasId, color) {
        var canvas = document.getElementById(canvasId);
        if (!canvas || !canvas.getContext) {
          return null;
        }
        var context = canvas.getContext("2d");
        var maxPoints = 60;
        var data = [];
        function draw() {
          var width = canvas.width;
          var height = canvas.height;
          context.clearRect(0, 0, width, height);
          if (data.length < 2) {
            return;
          }
          var min = Math.min.apply(null, data);
          var max = Math.max.apply(null, data);
          if (min === max) {
            max += 1;
            min -= 1;
          }
          context.beginPath();
          data.forEach(function (value, index) {
            var x = (index / (data.length - 1)) * width;
            var y = height - ((value - min) / (max - min)) * height;
            if (index === 0) {
              context.moveTo(x, y);
            } else {
              context.lineTo(x, y);
            }
          });
          context.strokeStyle = color;
          context.lineWidth = 2;
          context.stroke();
        }
        return {
          push: function (value) {
            if (typeof value !== "number" || isNaN(value)) {
              return;
            }
            data.push(value);
            if (data.length > maxPoints) {
              data.shift();
            }
            draw();
          }
        };
      }

      var charts = {
        cpu: createMiniChart("chart-cpu", "#2563eb"),
        ram: createMiniChart("chart-ram", "#16a34a"),
        temp: createMiniChart("chart-temp", "#dc2626")
      };

      var diagnosticAccordion = document.getElementById("diagnostic-accordion");
      var runAllButton = document.getElementById("run-all");
      var diagStatusLabels = {
        ok: { text: "Passed", className: "diag-pill-pass" },
        error: { text: "Failed", className: "diag-pill-fail" },
        warning: { text: "Information", className: "diag-pill-info" },
        skipped: { text: "Information", className: "diag-pill-info" }
      };

      var runtimeSettings = null;
      var availableTemperatureUnits = [];

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

      var specLoad = document.getElementById("spec-load");
      var specTemperature = document.getElementById("spec-temperature");
      var specStorage = document.getElementById("spec-storage");
      var specMemory = document.getElementById("spec-memory");
      var storageProgress = document.getElementById("storage-progress");
      var memoryProgress = document.getElementById("memory-progress");
      var cpuChartLabel = document.getElementById("cpu-chart-label");
      var ramChartLabel = document.getElementById("ram-chart-label");
      var tempChartLabel = document.getElementById("temp-chart-label");

      var temperatureUnitField = document.getElementById("temperature-unit");
      var pirPinsField = document.getElementById("pir-pins");
      var pirIntervalField = document.getElementById("pir-interval");
      var cameraDeviceField = document.getElementById("camera-device");
      var cameraWidthField = document.getElementById("camera-width");
      var cameraHeightField = document.getElementById("camera-height");
      var cameraFpsField = document.getElementById("camera-fps");
      var recordingPathField = document.getElementById("recording-path");
      var recordingMaxField = document.getElementById("recording-max");
      var recordingGapField = document.getElementById("recording-gap");
      var settingsForm = document.getElementById("settings-form");
      var settingsFeedback = document.getElementById("settings-feedback");

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

      function temperatureUnitSuffix() {
        var unit = (runtimeSettings && runtimeSettings.temperature && runtimeSettings.temperature.unit) || "celsius";
        if (unit === "fahrenheit") {
          return "°F";
        }
        if (unit === "kelvin") {
          return "K";
        }
        return "°C";
      }

      function convertTemperatureValue(value) {
        if (typeof value !== "number" || isNaN(value)) {
          return null;
        }
        var unit = (runtimeSettings && runtimeSettings.temperature && runtimeSettings.temperature.unit) || "celsius";
        if (unit === "fahrenheit") {
          return value * 9 / 5 + 32;
        }
        if (unit === "kelvin") {
          return value + 273.15;
        }
        return value;
      }

      function updateHouseRows() {
        houseRows.forEach(function (house, index) {
          if (!house || !house.cameraCell) {
            return;
          }
          if (activeCamera === house.cameraIndex) {
            setBadge(house.cameraCell, "Active", "status-active");
          } else {
            setBadge(house.cameraCell, "Standby", "status-idle");
          }
          var pin = pirPinOrder[index];
          if (pin === undefined) {
            if (house.pirState) {
              setBadge(house.pirState, "Pending", "status-idle");
            }
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

      function formatBytes(bytes) {
        if (typeof bytes !== "number" || isNaN(bytes)) {
          return "--";
        }
        var units = ["B", "KB", "MB", "GB", "TB"];
        var index = 0;
        var value = bytes;
        while (value >= 1024 && index < units.length - 1) {
          value /= 1024;
          index += 1;
        }
        return value.toFixed(value >= 10 || index === 0 ? 0 : 1) + " " + units[index];
      }

      function populateTemperatureSelect(options) {
        if (!temperatureUnitField || !options || !options.length) {
          return;
        }
        temperatureUnitField.innerHTML = "";
        options.forEach(function (opt) {
          var option = document.createElement("option");
          option.value = opt;
          option.textContent = opt.charAt(0).toUpperCase() + opt.slice(1);
          temperatureUnitField.appendChild(option);
        });
      }

      function populateSettingsForm(snapshot) {
        if (!snapshot) {
          return;
        }
        runtimeSettings = snapshot;
        if (temperatureUnitField && snapshot.temperature) {
          temperatureUnitField.value = snapshot.temperature.unit;
        }
        if (pirPinsField && snapshot.pir) {
          pirPinsField.value = (snapshot.pir.pins || []).join(", ");
        }
        if (pirIntervalField && snapshot.pir) {
          pirIntervalField.value = snapshot.pir.motion_poll_interval_seconds;
        }
        if (cameraDeviceField && snapshot.camera) {
          cameraDeviceField.value = snapshot.camera.device ?? "";
        }
        if (cameraWidthField && snapshot.camera) {
          cameraWidthField.value = snapshot.camera.record_width;
        }
        if (cameraHeightField && snapshot.camera) {
          cameraHeightField.value = snapshot.camera.record_height;
        }
        if (cameraFpsField && snapshot.camera) {
          cameraFpsField.value = snapshot.camera.record_fps;
        }
        if (recordingPathField && snapshot.recording) {
          recordingPathField.value = snapshot.recording.path;
        }
        if (recordingMaxField && snapshot.recording) {
          recordingMaxField.value = snapshot.recording.max_seconds;
        }
        if (recordingGapField && snapshot.recording) {
          recordingGapField.value = snapshot.recording.min_gap_seconds;
        }
        pirPinOrder = (snapshot.pir && snapshot.pir.pins) ? snapshot.pir.pins.slice(0, houseRows.length) : [];
        updateHouseRows();
      }

      async function fetchSettings() {
        try {
          const response = await fetch("/api/config", { cache: "no-store" });
          if (!response.ok) {
            throw new Error("HTTP " + response.status);
          }
          const payload = await response.json();
          availableTemperatureUnits = payload.temperature.available_units || [];
          populateTemperatureSelect(availableTemperatureUnits);
          populateSettingsForm(payload);
        } catch (error) {
          console.error("Failed to load configuration", error);
        }
      }

      function parsePins(input) {
        if (!input) {
          return [];
        }
        return input
          .split(/[,\s]+/)
          .map(function (item) { return item.trim(); })
          .filter(Boolean)
          .map(function (value) {
            var parsed = parseInt(value, 10);
            return isNaN(parsed) ? null : parsed;
          })
          .filter(function (value) { return value !== null; });
      }

      async function submitSettings(event) {
        event.preventDefault();
        if (settingsFeedback) {
          settingsFeedback.textContent = "Saving settings...";
          settingsFeedback.classList.remove("feedback-success", "feedback-error");
        }
        var payload = {
          temperature: {
            unit: temperatureUnitField ? temperatureUnitField.value : "celsius"
          },
          pir: {
            pins: parsePins(pirPinsField ? pirPinsField.value : ""),
            motion_poll_interval_seconds: parseFloat(pirIntervalField ? pirIntervalField.value : "0.25") || 0.25
          },
          camera: {
            device: cameraDeviceField && cameraDeviceField.value !== "" ? parseInt(cameraDeviceField.value, 10) : null,
            record_width: parseInt(cameraWidthField ? cameraWidthField.value : "0", 10) || 640,
            record_height: parseInt(cameraHeightField ? cameraHeightField.value : "0", 10) || 480,
            record_fps: parseFloat(cameraFpsField ? cameraFpsField.value : "0") || 15
          },
          recording: {
            path: recordingPathField ? recordingPathField.value : "recordings",
            max_seconds: parseInt(recordingMaxField ? recordingMaxField.value : "0", 10) || 30,
            min_gap_seconds: parseInt(recordingGapField ? recordingGapField.value : "0", 10) || 45
          }
        };
        try {
          const response = await fetch("/api/config", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
          });
          if (!response.ok) {
            throw new Error("HTTP " + response.status);
          }
          const updated = await response.json();
          populateSettingsForm(updated);
          if (settingsFeedback) {
            settingsFeedback.textContent = updated.message || "Settings updated.";
            settingsFeedback.classList.add("feedback-success");
          }
          refreshEnvironment();
          refreshSystemStatus();
        } catch (error) {
          if (settingsFeedback) {
            settingsFeedback.textContent = "Failed to save settings: " + error.message;
            settingsFeedback.classList.add("feedback-error");
          }
        }
      }

      if (settingsForm) {
        settingsForm.addEventListener("submit", submitSettings);
      }

      function createDiagnosticItem(test) {
        var details = document.createElement("details");
        details.className = "diagnostic-item";
        details.dataset.testId = test.id;
        details.innerHTML =
          '<summary>' +
          '<div><h3>' + test.name + '</h3><p class="muted">' + test.description + '</p></div>' +
          '<span class="diag-pill diag-pill-info" id="pill-' + test.id + '">Information</span>' +
          '</summary>' +
          '<div class="diag-body">' +
          '<button type="button" class="diag-run" data-test="' + test.id + '">Run test</button>' +
          '<p class="diag-summary" id="status-' + test.id + '">No results yet.</p>' +
          '<pre id="details-' + test.id + '" hidden></pre>' +
          '</div>';
        return details;
      }

      function renderStatus(testId, result) {
        var statusEl = document.getElementById("status-" + testId);
        var detailsEl = document.getElementById("details-" + testId);
        var pillEl = document.getElementById("pill-" + testId);
        if (!statusEl || !detailsEl || !pillEl) {
          return;
        }
        var map = diagStatusLabels[(result.status || "info").toLowerCase()] || diagStatusLabels.warning;
        pillEl.textContent = map.text;
        pillEl.className = "diag-pill " + map.className;
        statusEl.textContent = (result.status || "info").toUpperCase() + ": " + (result.summary || "No summary available.");
        if (result.details && Object.keys(result.details).length > 0) {
          detailsEl.hidden = false;
          detailsEl.textContent = JSON.stringify(result.details, null, 2);
        } else {
          detailsEl.hidden = true;
          detailsEl.textContent = "";
        }
      }

      async function fetchTests() {
        if (!diagnosticAccordion) {
          return;
        }
        diagnosticAccordion.innerHTML = "";
        try {
          const response = await fetch("/api/tests");
          if (!response.ok) {
            throw new Error("HTTP " + response.status);
          }
          const tests = await response.json();
          tests.forEach(function (test) {
            diagnosticAccordion.appendChild(createDiagnosticItem(test));
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

      if (diagnosticAccordion) {
        diagnosticAccordion.addEventListener("click", function (event) {
          var target = event.target;
          if (target.tagName === "BUTTON" && target.dataset.test) {
            runTest(target.dataset.test);
          }
        });
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
          var convertedTemp = convertTemperatureValue(temperature);
          envTemp.textContent = typeof convertedTemp === "number" ? convertedTemp.toFixed(1) + " " + temperatureUnitSuffix() : "--";
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
          pirPinOrder = pins.slice(0, houseRows.length);
          if (pirStatus) {
            pirStatus.textContent = pins.length ? "" : "No PIR sensors detected.";
          }
          updateHouseRows();
        } catch (error) {
          latestPirStates = {};
          if (pirStatus) {
            pirStatus.textContent = "PIR sensors unavailable: " + error.message;
          }
          updateHouseRows();
        }
      }

      async function refreshSystemStatus() {
        try {
          const response = await fetch("/api/status/system", { cache: "no-store" });
          if (!response.ok) {
            throw new Error("HTTP " + response.status);
          }
          const payload = await response.json();
          if (specLoad) {
            var loadValues = payload.load || {};
            specLoad.textContent = [loadValues["1m"], loadValues["5m"], loadValues["15m"]]
              .map(function (value) {
                return typeof value === "number" ? value.toFixed(2) : "--";
              })
              .join(" / ");
          }
          if (specTemperature) {
            var preferred = payload.temperature && payload.temperature.preferred ? payload.temperature.preferred : null;
            if (preferred && typeof preferred.value === "number") {
              specTemperature.textContent = preferred.value.toFixed(1) + " " + temperatureUnitSuffix();
            } else {
              specTemperature.textContent = "--";
            }
          }
          if (specStorage) {
            var storage = payload.storage || {};
            var used = storage.used_bytes;
            var total = storage.total_bytes;
            if (typeof used === "number" && typeof total === "number") {
              var percent = total > 0 ? (used / total) * 100 : 0;
              specStorage.textContent = formatBytes(used) + " of " + formatBytes(total) + " (" + percent.toFixed(1) + "%)";
              if (storageProgress) {
                storageProgress.style.width = Math.min(100, Math.max(0, percent)) + "%";
              }
            } else {
              specStorage.textContent = "--";
            }
          }
          if (specMemory) {
            var memory = payload.memory || {};
            var memUsed = memory.used_bytes;
            var memTotal = memory.total_bytes;
            if (typeof memUsed === "number" && typeof memTotal === "number") {
              var memPercent = memTotal > 0 ? (memUsed / memTotal) * 100 : 0;
              specMemory.textContent = formatBytes(memUsed) + " of " + formatBytes(memTotal) + " (" + memPercent.toFixed(1) + "%)";
              if (memoryProgress) {
                memoryProgress.style.width = Math.min(100, Math.max(0, memPercent)) + "%";
              }
            } else {
              specMemory.textContent = "--";
            }
          }
          if (charts.cpu && typeof payload.cpu_percent === "number") {
            charts.cpu.push(payload.cpu_percent);
            if (cpuChartLabel) {
              cpuChartLabel.textContent = payload.cpu_percent.toFixed(1) + "%";
            }
          }
          if (charts.ram && payload.memory && typeof payload.memory.percent_used === "number") {
            charts.ram.push(payload.memory.percent_used);
            if (ramChartLabel) {
              ramChartLabel.textContent = payload.memory.percent_used.toFixed(1) + "%";
            }
          }
          var displayTemperature = payload.temperature && payload.temperature.preferred ? payload.temperature.preferred.value : null;
          if (charts.temp && typeof displayTemperature === "number") {
            charts.temp.push(displayTemperature);
            if (tempChartLabel) {
              tempChartLabel.textContent = displayTemperature.toFixed(1) + " " + temperatureUnitSuffix();
            }
          }
        } catch (error) {
          console.warn("System status unavailable:", error);
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
        pollTimers.push(setInterval(refreshSystemStatus, 5000));
      }

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

      fetchSettings().then(function () {
        refreshPirStatus();
        refreshEnvironment();
        refreshPowerStatus();
        refreshSystemStatus();
        schedulePolling();
      });
      fetchTests();
    })();
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


def _serialize_runtime_config(settings) -> Dict[str, Any]:
    """Normalise runtime settings into a frontend-friendly payload."""

    return {
        "temperature": {
            "unit": settings.temperature_unit.value,
            "available_units": [unit.value for unit in TemperatureUnit],
        },
        "pir": {
            "pins": list(settings.pir_pins),
            "motion_poll_interval_seconds": settings.motion_poll_interval_seconds,
        },
        "camera": {
            "device": settings.camera_device,
            "record_width": settings.camera_record_width,
            "record_height": settings.camera_record_height,
            "record_fps": settings.camera_record_fps,
        },
        "recording": {
            "path": str(settings.recordings_path),
            "max_seconds": settings.recording_max_seconds,
            "min_gap_seconds": settings.recording_min_gap_seconds,
        },
    }


_CPU_TIMES: Optional[tuple[int, int]] = None


def _read_cpu_times() -> Optional[tuple[int, int]]:
    """Read total and idle CPU times from /proc/stat."""

    try:
        with open("/proc/stat", "r", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("cpu "):
                    parts = line.split()
                    values = [int(value) for value in parts[1:]]
                    if len(values) < 4:
                        return None
                    idle = values[3] + (values[4] if len(values) > 4 else 0)
                    total = sum(values)
                    return total, idle
    except (OSError, ValueError):
        return None
    return None


def _cpu_percent() -> Optional[float]:
    """Compute CPU utilisation between successive calls."""

    global _CPU_TIMES
    current = _read_cpu_times()
    if current is None:
        return None
    previous = _CPU_TIMES
    _CPU_TIMES = current
    if previous is None:
        return None
    total_diff = current[0] - previous[0]
    idle_diff = current[1] - previous[1]
    if total_diff <= 0:
        return None
    busy = total_diff - idle_diff
    percent = (busy / total_diff) * 100.0
    return max(0.0, min(100.0, percent))


def _memory_snapshot() -> Dict[str, Optional[float]]:
    """Return memory statistics derived from /proc/meminfo."""

    snapshot: Dict[str, Optional[float]] = {
        "total_bytes": None,
        "available_bytes": None,
        "used_bytes": None,
        "percent_used": None,
    }
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as handle:
            meminfo: Dict[str, int] = {}
            for line in handle:
                parts = line.strip().split(":")
                if len(parts) != 2:
                    continue
                key = parts[0]
                value_tokens = parts[1].strip().split()
                if not value_tokens:
                    continue
                try:
                    meminfo[key] = int(value_tokens[0]) * 1024  # values are in kB
                except ValueError:
                    continue
        total = meminfo.get("MemTotal")
        available = meminfo.get("MemAvailable")
        if total is not None and available is not None:
            used = total - available
            percent = (used / total) * 100 if total else None
            snapshot.update(
                {
                    "total_bytes": float(total),
                    "available_bytes": float(available),
                    "used_bytes": float(used),
                    "percent_used": float(percent) if percent is not None else None,
                }
            )
    except OSError:
        return snapshot
    return snapshot


def _storage_snapshot(recordings_path: Path) -> Dict[str, Optional[float]]:
    """Return disk usage information for the recordings path or its nearest parent."""

    path = recordings_path
    try:
        resolved = path.expanduser()
    except OSError:
        resolved = Path("/")
    probe = resolved if resolved.exists() else resolved.parent
    if not probe.exists():
        probe = Path("/")
    try:
        usage = shutil.disk_usage(probe)
    except OSError:
        return {"path": str(probe), "total_bytes": None, "used_bytes": None, "free_bytes": None}
    used = usage.total - usage.free
    return {
        "path": str(probe),
        "total_bytes": float(usage.total),
        "used_bytes": float(used),
        "free_bytes": float(usage.free),
    }


def _read_temperature_sensor() -> Optional[float]:
    """Read SoC temperature (°C) from standard thermal zone paths."""

    candidates = (
        Path("/sys/class/thermal/thermal_zone0/temp"),
        Path("/sys/class/hwmon/hwmon0/temp1_input"),
    )
    for candidate in candidates:
        try:
            raw = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not raw:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if value > 200:
            value /= 1000.0
        return value
    return None


def _collect_system_status(settings) -> Dict[str, object]:
    """Gather CPU, memory, storage, and thermal metrics."""

    try:
        load1, load5, load15 = os.getloadavg()
        load = {"1m": load1, "5m": load5, "15m": load15}
    except OSError:
        load = {"1m": None, "5m": None, "15m": None}
    memory = _memory_snapshot()
    storage = _storage_snapshot(settings.recordings_path)
    temperature_c = _read_temperature_sensor()
    preferred = (
        convert_temperature(temperature_c, settings.temperature_unit) if temperature_c is not None else None
    )
    status: Dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "load": load,
        "cpu_percent": _cpu_percent(),
        "cpu_count": os.cpu_count(),
        "memory": memory,
        "storage": storage,
        "temperature": {
            "celsius": temperature_c,
            "preferred": {
                "unit": settings.temperature_unit.value,
                "value": preferred,
            },
        },
    }
    return status


@router.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    """Serve the HTML dashboard."""

    logger.debug("Serving dashboard HTML")
    return HTMLResponse(content=DASHBOARD_HTML)


@router.get("/api/config")
async def read_configuration() -> Dict[str, Any]:
    """Return the current runtime configuration snapshot."""

    settings = get_settings()
    logger.debug("Providing configuration snapshot")
    return _serialize_runtime_config(settings)


@router.put("/api/config")
async def write_configuration(payload: ConfigurationUpdateRequest) -> Dict[str, Any]:
    """Update runtime configuration and refresh the cached settings."""

    logger.info("Applying runtime configuration update")
    updates: Dict[str, Any] = {
        "temperature_unit": payload.temperature.unit,
        "pir_pins": payload.pir.pins,
        "motion_poll_interval_seconds": payload.pir.motion_poll_interval_seconds,
        "camera_device": payload.camera.device,
        "camera_record_width": payload.camera.record_width,
        "camera_record_height": payload.camera.record_height,
        "camera_record_fps": payload.camera.record_fps,
        "recordings_path": payload.recording.path,
        "recording_max_seconds": payload.recording.max_seconds,
        "recording_min_gap_seconds": payload.recording.min_gap_seconds,
    }
    settings = update_settings(updates)
    response = _serialize_runtime_config(settings)
    response["message"] = "Settings updated."
    return response


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
    if snapshot.results:
        sensor_aht = snapshot.results.get("aht20") or {}
        sensor_bmp = snapshot.results.get("bmp280") or {}
        temperature_c = sensor_aht.get("temperature_c")
        if temperature_c is None:
            temperature_c = sensor_bmp.get("temperature_c")
    else:
        temperature_c = None

    logger.info(
        "Environment snapshot completed with status=%s (results=%d errors=%d)",
        status,
        len(snapshot.results),
        len(snapshot.errors),
    )
    return {
        "status": status,
        "results": snapshot.results,
        "errors": snapshot.errors,
        "display": {
            "temperature": {
                "value": convert_temperature(temperature_c, settings.temperature_unit)
                if temperature_c is not None
                else None,
                "unit": settings.temperature_unit.value,
            }
        },
    }


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


@router.get("/api/status/system")
async def system_status() -> Dict[str, object]:
    """Return CPU load, memory, storage, and temperature statistics."""

    settings = get_settings()
    return _collect_system_status(settings)


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
