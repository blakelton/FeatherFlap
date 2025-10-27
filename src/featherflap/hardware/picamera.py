"""Helpers for interacting with the Raspberry Pi CSI camera via Picamera2."""

from __future__ import annotations

import io
import time
from contextlib import suppress
from typing import Generator, Tuple

from ..logger import get_logger

logger = get_logger(__name__)


class PicameraUnavailable(RuntimeError):
    """Raised when Picamera2 cannot be used (missing dependency or hardware)."""


def _ensure_picamera2():
    try:
        from picamera2 import Picamera2  # type: ignore
    except ImportError as exc:  # pragma: no cover - optional dependency
        logger.error("Picamera2 import failed: %s", exc)
        raise PicameraUnavailable("Picamera2 is not installed.") from exc
    return Picamera2


def capture_picamera_jpeg(
    size: Tuple[int, int] = (1296, 972),
    quality: int = 90,
    warmup_seconds: float = 0.15,
) -> bytes:
    """Capture a single JPEG frame from the CSI camera."""

    Picamera2 = _ensure_picamera2()
    logger.debug("Capturing CSI frame (size=%s quality=%s)", size, quality)
    picam = Picamera2()
    config = picam.create_still_configuration(main={"size": size})
    picam.configure(config)
    try:
        picam.start()
        if warmup_seconds > 0:
            time.sleep(warmup_seconds)
        buffer = io.BytesIO()
        picam.capture_file(buffer, format="jpeg", quality=quality)
        payload = buffer.getvalue()
        logger.info("Captured CSI frame (%d bytes)", len(payload))
        return payload
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("CSI frame capture failed: %s", exc)
        raise PicameraUnavailable("Failed to capture from Picamera2.") from exc
    finally:
        with suppress(Exception):
            picam.stop()
        picam.close()


def picamera_mjpeg_stream(
    size: Tuple[int, int] = (1296, 972),
    fps: float = 15.0,
    quality: int = 85,
) -> Generator[bytes, None, None]:
    """Yield multipart MJPEG frames from the CSI camera."""

    Picamera2 = _ensure_picamera2()
    logger.info("Starting Picamera2 MJPEG stream (size=%s fps=%s)", size, fps)
    picam = Picamera2()
    config = picam.create_video_configuration(main={"size": size})
    picam.configure(config)
    frame_interval = 1.0 / max(1.0, fps)
    try:
        picam.start()
        while True:
            start = time.monotonic()
            buffer = io.BytesIO()
            picam.capture_file(buffer, format="jpeg", quality=quality)
            payload = buffer.getvalue()
            logger.debug("Picamera2 MJPEG frame (%d bytes)", len(payload))
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
            delay = frame_interval - elapsed
            if delay > 0:
                time.sleep(delay)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Picamera2 MJPEG stream failed: %s", exc)
        raise PicameraUnavailable("CSI streaming halted unexpectedly.") from exc
    finally:
        with suppress(Exception):
            picam.stop()
        picam.close()
        logger.info("Stopped Picamera2 MJPEG stream")
