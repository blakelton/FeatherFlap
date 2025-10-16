"""USB camera helpers optimised for Raspberry Pi Zero 2 W."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Generator, Optional


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


class CameraUnavailable(RuntimeError):
    """Raised when OpenCV or the camera device cannot be opened."""


def _ensure_cv2():
    try:
        import cv2  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise CameraUnavailable("OpenCV (cv2) is not installed.") from exc
    return cv2


@contextmanager
def _open_capture(device: int | str, width: Optional[int], height: Optional[int]):
    cv2 = _ensure_cv2()
    index = device if isinstance(device, int) else str(device)
    capture = cv2.VideoCapture(index, cv2.CAP_V4L2)
    if not capture.isOpened():
        capture.release()
        raise CameraUnavailable(f"Unable to open camera device {index}.")
    if width:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, float(width))
    if height:
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, float(height))
    try:
        yield capture
    finally:
        capture.release()


def capture_jpeg_frame(
    device: int | str = DEFAULT_DEVICE_INDEX,
    width: Optional[int] = DEFAULT_FRAME_WIDTH,
    height: Optional[int] = DEFAULT_FRAME_HEIGHT,
    quality: int = DEFAULT_JPEG_QUALITY,
) -> bytes:
    """Capture a single frame and return it as JPEG bytes."""

    with _open_capture(device, width, height) as capture:
        ok, frame = capture.read()
        if not ok or frame is None:
            raise CameraUnavailable("Camera opened but did not deliver a frame.")
        cv2 = _ensure_cv2()
        encode_params = [
            int(cv2.IMWRITE_JPEG_QUALITY),
            int(max(JPEG_QUALITY_MIN, min(JPEG_QUALITY_MAX, quality))),
        ]
        success, encoded = cv2.imencode(".jpg", frame, encode_params)
        if not success:
            raise CameraUnavailable("Failed to encode camera frame as JPEG.")
        return encoded.tobytes()


def mjpeg_stream(
    device: int | str = DEFAULT_DEVICE_INDEX,
    width: Optional[int] = DEFAULT_FRAME_WIDTH,
    height: Optional[int] = DEFAULT_FRAME_HEIGHT,
    fps: float = DEFAULT_STREAM_FPS,
    quality: int = DEFAULT_STREAM_JPEG_QUALITY,
) -> Generator[bytes, None, None]:
    """Yield multipart MJPEG frames suitable for a StreamingResponse."""

    frame_interval = FRAME_INTERVAL_BASE_SECONDS / max(MIN_STREAM_FPS, fps)
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
                raise CameraUnavailable("Camera stream halted unexpectedly.")
            success, encoded = cv2.imencode(".jpg", frame, encode_params)
            if not success:
                raise CameraUnavailable("Failed to encode camera frame as JPEG.")
            payload = encoded.tobytes()
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
