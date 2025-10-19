"""Run-mode controller orchestrating motion detection and recording."""

from __future__ import annotations

import os
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..config import AppSettings
from ..hardware.camera import CameraUnavailable, record_video
from ..logger import get_logger
from .camera import CameraBusyError, CameraUsageCoordinator
from .sleep import SleepScheduler

logger = get_logger(__name__)


class RunModeController:
    """Background supervisor for motion-triggered recordings."""

    def __init__(self, settings: AppSettings, camera_coordinator: CameraUsageCoordinator):
        self._settings = settings
        self._camera = camera_coordinator
        self._stop_event = threading.Event()
        self._motion_thread: Optional[threading.Thread] = None
        self._recording_thread: Optional[threading.Thread] = None
        self._recording_lock = threading.Lock()
        self._recording_active = False
        self._last_recording_end = 0.0
        self._recording_path: Optional[Path] = None
        self._scheduler = SleepScheduler(settings.sleep_windows)
        self._recordings_dir = settings.recordings_path.expanduser().resolve()
        self._recordings_dir.mkdir(parents=True, exist_ok=True)
        self._network_path = settings.network_export_path.expanduser().resolve() if settings.network_export_path else None
        if self._network_path:
            self._network_path.mkdir(parents=True, exist_ok=True)
        self._gpio = None
        self._pir_pins = settings.pir_pins

    # --------------------------------------------------------------------- #
    # Lifecycle                                                             #
    # --------------------------------------------------------------------- #

    def start(self) -> None:
        if self._motion_thread and self._motion_thread.is_alive():
            logger.debug("RunModeController already started")
            return
        self._stop_event.clear()
        self._setup_gpio()
        self._motion_thread = threading.Thread(target=self._motion_loop, name="featherflap-motion", daemon=True)
        self._motion_thread.start()
        logger.info("Run mode controller started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._motion_thread:
            self._motion_thread.join(timeout=5)
        if self._recording_thread:
            self._recording_thread.join(timeout=10)
        self._cleanup_gpio()
        logger.info("Run mode controller stopped")

    # --------------------------------------------------------------------- #
    # GPIO handling                                                         #
    # --------------------------------------------------------------------- #

    def _setup_gpio(self) -> None:
        if not self._pir_pins:
            return
        try:
            import RPi.GPIO as GPIO  # type: ignore
        except ImportError:
            logger.warning("RPi.GPIO not installed; run mode will rely on fallback timers.")
            return
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        for pin in self._pir_pins:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        self._gpio = GPIO
        logger.debug("Configured PIR GPIO pins: %s", self._pir_pins)

    def _cleanup_gpio(self) -> None:
        if self._gpio:
            for pin in self._pir_pins:
                try:
                    self._gpio.cleanup(pin)
                except Exception:  # pragma: no cover - defensive
                    pass
            self._gpio = None

    # --------------------------------------------------------------------- #
    # Motion detection & recording                                          #
    # --------------------------------------------------------------------- #

    def _motion_loop(self) -> None:
        logger.debug("Motion detection loop active")
        while not self._stop_event.is_set():
            now = datetime.now()
            if self._scheduler.is_sleep_time(now):
                if self._recording_active:
                    logger.info("Entering sleep window; stopping recording")
                self._stop_event.wait(timeout=30)
                continue

            triggered = self._check_motion()
            if triggered:
                self._handle_motion()
            self._stop_event.wait(timeout=self._settings.motion_poll_interval_seconds)
        logger.debug("Motion detection loop finished")

    def _check_motion(self) -> bool:
        if self._gpio is None or not self._pir_pins:
            # No hardware pin, fall back to periodic recording every few minutes to ensure sanity.
            return (time.time() - self._last_recording_end) > max(self._settings.recording_min_gap_seconds, 120)
        return any(self._gpio.input(pin) for pin in self._pir_pins)  # type: ignore[operator]

    def _handle_motion(self) -> None:
        now = time.time()
        if self._recording_active:
            logger.debug("Motion detected but recording already active")
            return
        if now - self._last_recording_end < self._settings.recording_min_gap_seconds:
            logger.debug(
                "Motion detected but cooldown (%ss) has not elapsed",
                self._settings.recording_min_gap_seconds,
            )
            return
        if self._recording_thread and self._recording_thread.is_alive():
            logger.debug("Ignoring motion trigger while previous recording thread finishes")
            return
        self._recording_thread = threading.Thread(
            target=self._record_motion,
            name="featherflap-record",
            daemon=True,
        )
        self._recording_thread.start()

    def _record_motion(self) -> None:
        with self._recording_lock:
            try:
                lease = self._camera.acquire("record", blocking=True)
            except CameraBusyError:
                logger.warning("Camera busy; skipping recording trigger")
                return

            with lease:
                self._recording_active = True
                timestamp_dir = datetime.now().strftime("%Y-%m-%d")
                directory = self._recordings_dir / timestamp_dir
                directory.mkdir(parents=True, exist_ok=True)
                filename = datetime.now().strftime("%H-%M-%S")
                path = directory / f"{filename}.mp4"
                logger.info("Recording started: %s", path)
                try:
                    record_video(
                        output_path=path,
                        device=self._settings.camera_device
                        if self._settings.camera_device is not None
                        else 0,
                        width=self._settings.camera_record_width,
                        height=self._settings.camera_record_height,
                        fps=self._settings.camera_record_fps,
                        max_seconds=self._settings.recording_max_seconds,
                        stop_event=self._stop_event,
                    )
                except CameraUnavailable as exc:
                    logger.error("Camera unavailable during recording: %s", exc)
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        pass
                except Exception as exc:  # pragma: no cover - defensive
                    logger.exception("Unexpected recording failure: %s", exc)
                    try:
                        path.unlink(missing_ok=True)
                    except OSError:
                        pass
                else:
                    self._recording_path = path
                    self._mirror_recording(path)
                finally:
                    self._recording_active = False
                    self._last_recording_end = time.time()
                    logger.info("Recording finished")

    def _mirror_recording(self, path: Path) -> None:
        if not self._network_path:
            return
        try:
            target_dir = self._network_path / path.parent.name
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target_dir / path.name)
            logger.info("Mirrored recording to %s", target_dir / path.name)
        except OSError as exc:
            logger.warning("Failed to mirror recording to network path: %s", exc)

    # --------------------------------------------------------------------- #
    # Status reporting                                                      #
    # --------------------------------------------------------------------- #

    def status(self) -> dict:
        return {
            "recording_active": self._recording_active,
            "recording_path": str(self._recording_path) if self._recording_path else None,
            "camera_in_use": self._camera.in_use(),
            "last_recording_end": self._last_recording_end,
        }
