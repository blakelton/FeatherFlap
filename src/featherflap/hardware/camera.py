"""USB camera helpers optimised for Raspberry Pi Zero 2 W."""

from __future__ import annotations

import time
from contextlib import contextmanager
import threading
from pathlib import Path
from typing import Generator, Optional

from ..logger import get_logger

DEFAULT_DEVICE_INDEX = 0
DEFAULT_FRAME_WIDTH = 640
DEFAULT_FRAME_HEIGHT = 480
DEFAULT_JPEG_QUALITY = 80
DEFAULT_STREAM_JPEG_QUALITY = 75
JPEG_QUALITY_MIN = 10
JPEG_QUALITY_MAX = 95
STREAM_QUALITY_MAX = 90
MIN_STREAM_FPS = 1.0
DEFAULT_STREAM_FPS = 10.0
FRAME_INTERVAL_BASE_SECONDS = 1.0
logger = get_logger(__name__)
_cv2_loaded = False


class CameraUnavailable(RuntimeError):
    """Raised when OpenCV or the camera device cannot be opened."""


def _ensure_cv2():
    global _cv2_loaded
    try:
        import cv2  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        logger.error("OpenCV import failed: %s", exc)
        raise CameraUnavailable("OpenCV (cv2) is not installed.") from exc
    if not _cv2_loaded:
        logger.debug("OpenCV library successfully loaded")
        _cv2_loaded = True
    return cv2


@contextmanager
def _open_capture(device: int | str, width: Optional[int], height: Optional[int]):
    cv2 = _ensure_cv2()
    index = device if isinstance(device, int) else str(device)
    logger.debug("Opening camera device %s (width=%s height=%s)", index, width, height)
    capture = cv2.VideoCapture(index, cv2.CAP_V4L2)
    if not capture.isOpened():
        capture.release()
        logger.error("Unable to open camera device %s", index)
        raise CameraUnavailable(f"Unable to open camera device {index}.")
    if width:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, float(width))
    if height:
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, float(height))
    try:
        yield capture
    finally:
        logger.debug("Releasing camera device %s", index)
        capture.release()


def capture_jpeg_frame(
    device: int | str = DEFAULT_DEVICE_INDEX,
    width: Optional[int] = DEFAULT_FRAME_WIDTH,
    height: Optional[int] = DEFAULT_FRAME_HEIGHT,
    quality: int = DEFAULT_JPEG_QUALITY,
) -> bytes:
    """Capture a single frame and return it as JPEG bytes."""

    logger.debug("Capturing JPEG frame (device=%s width=%s height=%s quality=%s)", device, width, height, quality)
    with _open_capture(device, width, height) as capture:
        ok, frame = capture.read()
        if not ok or frame is None:
            logger.error("Camera frame capture failed: empty frame received")
            raise CameraUnavailable("Camera opened but did not deliver a frame.")
        cv2 = _ensure_cv2()
        encode_params = [
            int(cv2.IMWRITE_JPEG_QUALITY),
            int(max(JPEG_QUALITY_MIN, min(JPEG_QUALITY_MAX, quality))),
        ]
        success, encoded = cv2.imencode(".jpg", frame, encode_params)
        if not success:
            logger.error("Camera frame encoding failed")
            raise CameraUnavailable("Failed to encode camera frame as JPEG.")
        payload = encoded.tobytes()
        logger.info("Captured single JPEG frame (%d bytes)", len(payload))
        return payload


def mjpeg_stream(
    device: int | str = DEFAULT_DEVICE_INDEX,
    width: Optional[int] = DEFAULT_FRAME_WIDTH,
    height: Optional[int] = DEFAULT_FRAME_HEIGHT,
    fps: float = DEFAULT_STREAM_FPS,
    quality: int = DEFAULT_STREAM_JPEG_QUALITY,
) -> Generator[bytes, None, None]:
    """Yield multipart MJPEG frames suitable for a StreamingResponse."""

    frame_interval = FRAME_INTERVAL_BASE_SECONDS / max(MIN_STREAM_FPS, fps)
    logger.info(
        "Starting MJPEG stream (device=%s width=%s height=%s fps=%s quality=%s)",
        device,
        width,
        height,
        fps,
        quality,
    )
    with _open_capture(device, width, height) as capture:
        cv2 = _ensure_cv2()
        encode_params = [
            int(cv2.IMWRITE_JPEG_QUALITY),
            int(max(JPEG_QUALITY_MIN, min(STREAM_QUALITY_MAX, quality))),
        ]
        while True:
            start = time.monotonic()
            ok, frame = capture.read()
            if not ok or frame is None:
                logger.error("Camera stream halted: capture returned empty frame")
                raise CameraUnavailable("Camera stream halted unexpectedly.")
            success, encoded = cv2.imencode(".jpg", frame, encode_params)
        if not success:
            logger.error("Camera stream encoding failed")
            raise CameraUnavailable("Failed to encode camera frame as JPEG.")
            payload = encoded.tobytes()
            logger.debug("Encoded MJPEG frame (%d bytes)", len(payload))
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: "
                + str(len(payload)).encode("ascii")
                + b"\r\n\r\n"
                + payload
                + b"\r\n"
            )
            elapsed = time.monotonic() - start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)


def record_video(
    output_path: Path,
    *,
    device: int | str = DEFAULT_DEVICE_INDEX,
    width: int = DEFAULT_FRAME_WIDTH,
    height: int = DEFAULT_FRAME_HEIGHT,
    fps: float = DEFAULT_STREAM_FPS,
    max_seconds: int = 30,
    stop_event: Optional[threading.Event] = None,
) -> None:
    """Record a video clip to ``output_path`` using OpenCV."""

    if fps <= 0:
        raise ValueError("FPS must be positive.")
    duration_limit = max(1, max_seconds)
    stop_event = stop_event or threading.Event()
    cv2 = _ensure_cv2()
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    with _open_capture(device, width, height) as capture:
        writer = cv2.VideoWriter(str(output_path), fourcc, float(fps), (int(width), int(height)))
        start = time.monotonic()
        frame_interval = 1.0 / fps
        frame_count = 0
        try:
            while not stop_event.is_set() and (time.monotonic() - start) < duration_limit:
                ok, frame = capture.read()
                if not ok or frame is None:
                    logger.warning("Camera frame read failed during recording; stopping early.")
                    break
                writer.write(frame)
                frame_count += 1
                elapsed = time.monotonic() - start
                sleep_time = frame_interval * frame_count - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)
        finally:
            writer.release()
    logger.info("Recorded %d frames to %s", frame_count, output_path)
