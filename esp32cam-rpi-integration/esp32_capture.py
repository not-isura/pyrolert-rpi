from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import time
from typing import Optional

import requests


@dataclass(frozen=True)
class CaptureResult:
    saved_path: Path
    bytes_written: int
    raw_bytes: bytes = b""


def _trigger_capture(esp32_url: str, timeout: float = 5.0) -> bool:
    try:
        response = requests.get(f"{esp32_url}/capture", timeout=timeout)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException:
        return False


def _download_image(esp32_url: str, timeout: float = 10.0) -> Optional[bytes]:
    try:
        response = requests.get(f"{esp32_url}/saved-photo", timeout=timeout)
        response.raise_for_status()
        return response.content
    except requests.exceptions.RequestException:
        return None


def capture_image_stream(
    esp32_url: str,
    output_dir: Path,
    min_bytes: int = 1000,
    timeout: float = 15.0,
) -> Optional[CaptureResult]:
    """Single-request capture via /capture-stream — faster, no SPIFFS involved."""
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        response = requests.get(f"{esp32_url}/capture-stream", timeout=timeout)
        response.raise_for_status()
        image = response.content
        if not image or len(image) < min_bytes:
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = output_dir / f"esp32_{timestamp}_raw.jpg"
        filename.write_bytes(image)
        return CaptureResult(saved_path=filename, bytes_written=len(image), raw_bytes=image)
    except requests.exceptions.RequestException:
        return None


def capture_image_from_esp32(
    esp32_url: str,
    output_dir: Path,
    capture_delay: int,
    retries: int,
    min_bytes: int = 1000,
) -> Optional[CaptureResult]:
    output_dir.mkdir(parents=True, exist_ok=True)

    if not _trigger_capture(esp32_url):
        return None

    time.sleep(max(capture_delay, 0))

    for _ in range(max(retries, 1)):
        image = _download_image(esp32_url)
        if image and len(image) >= min_bytes:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = output_dir / f"esp32_{timestamp}.jpg"
            filename.write_bytes(image)
            return CaptureResult(saved_path=filename, bytes_written=len(image))
        time.sleep(1)

    return None
