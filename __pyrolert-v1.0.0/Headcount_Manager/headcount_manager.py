from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from ultralytics import YOLO

from Headcount_Manager.esp32_capture import capture_image_stream
from Database import db as _db
from Database.supabase_client import push_headcount_log, upload_headcount_image

SUPABASE_TIMEOUT_S = 10  # max seconds to wait for each Supabase network call

# Confidence thresholds
CONF_HIGH = 0.70
CONF_MID  = 0.50
CONF_LOW  = 0.30

# BGR colors
COLOR_GREEN  = (0, 255, 0)
COLOR_YELLOW = (0, 255, 255)
COLOR_RED    = (0, 0, 255)


@dataclass
class HeadcountResult:
    high_count:  int    # confidence >= 70%  green
    mid_count:   int    # confidence >= 50%  yellow
    low_count:   int    # confidence >= 30%  red
    total_count: int
    saved_path:  Path
    timestamp:   str


class HeadcountManager:
    def __init__(
        self,
        esp32_url:            str,
        model_path:           Path,
        raw_output_dir:       Path,
        annotated_output_dir: Path,
        interval_s:           int,
        db_conn=None,
        resize:               tuple[int, int] | None = None,  # (width, height), None = no resize
        show_labels:          bool = True,                    # False = boxes only, no label/percentage
    ) -> None:
        self.esp32_url             = esp32_url
        self._raw_output_dir       = Path(raw_output_dir)
        self._annotated_output_dir = Path(annotated_output_dir)
        self.interval_s            = interval_s
        self.resize                = resize
        self.show_labels           = show_labels
        self._db_conn              = db_conn
        self.model                 = YOLO(str(model_path), task="detect")
        self._last_ts:              float | None = None
        self._busy                 = False
        self._lock                 = threading.Lock()
        self._episode_id:          Optional[int] = None  # Supabase episode id
        self._sqlite_episode_id:   Optional[int] = None  # local SQLite episode id

    def set_episode(self, supabase_episode_id: Optional[int], sqlite_episode_id: Optional[int] = None) -> None:
        """Link subsequent headcount logs to an alert episode (pass None to unlink)."""
        self._episode_id = supabase_episode_id
        self._sqlite_episode_id = sqlite_episode_id
        if supabase_episode_id is None:
            with self._lock:
                self._last_ts = None  # reset timer so next episode starts fresh

    def trigger_if_due(self, current_ts: float) -> None:
        if self._episode_id is None:
            return  # no active episode — skip silently
        with self._lock:
            if self._busy:
                print("[Headcount] Still running previous capture, skipping.")
                return
            if self._last_ts and (current_ts - self._last_ts) < self.interval_s:
                remaining = self.interval_s - (current_ts - self._last_ts)
                print(f"[Headcount] Next in {remaining:.0f}s, skipping.")
                return
            self._busy = True
        threading.Thread(target=self._run, args=("auto",), daemon=True).start()

    def trigger_now(self) -> None:
        with self._lock:
            if self._busy:
                print("[Headcount] Still running previous capture, skipping.")
                return
            self._busy = True
        threading.Thread(target=self._run, args=("manual",), daemon=True).start()

    def process_frame(self, frame: np.ndarray, output_path: Path) -> HeadcountResult:
        """Run YOLO on a numpy image array and save annotated result to output_path."""
        if self.resize:
            frame = cv2.resize(frame, self.resize, interpolation=cv2.INTER_AREA)

        results    = self.model.predict(frame, verbose=False)
        detections = results[0].boxes

        high_count = 0
        mid_count  = 0
        low_count  = 0

        for box in detections:
            conf = float(box.conf[0])

            if conf >= CONF_HIGH:
                color = COLOR_GREEN
                high_count += 1
            elif conf >= CONF_MID:
                color = COLOR_YELLOW
                mid_count += 1
            elif conf >= CONF_LOW:
                color = COLOR_RED
                low_count += 1
            else:
                continue  # below 30%, ignore

            xmin, ymin, xmax, ymax = box.xyxy[0].cpu().numpy().astype(int)
            cv2.rectangle(frame, (xmin, ymin), (xmax, ymax), color, 2)

            if self.show_labels:
                label = f"person: {int(conf * 100)}%"
                label_size, baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                label_ymin = max(ymin, label_size[1] + 10)
                cv2.rectangle(frame,
                    (xmin, label_ymin - label_size[1] - 10),
                    (xmin + label_size[0], label_ymin + baseline - 10),
                    color, cv2.FILLED)
                cv2.putText(frame, label, (xmin, label_ymin - 7),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        total_count = high_count + mid_count + low_count
        cv2.imwrite(str(output_path), frame)

        return HeadcountResult(
            high_count=high_count,
            mid_count=mid_count,
            low_count=low_count,
            total_count=total_count,
            saved_path=output_path,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    def process_image(self, image_path: Path, output_path: Path | None = None) -> HeadcountResult:
        """Run YOLO on an existing image file. Used for local testing without ESP32."""
        if output_path is None:
            output_path = image_path
        frame = cv2.imread(str(image_path))
        return self.process_frame(frame, output_path)

    def _log_timeout(self, trigger_source: str, ts: float) -> None:
        """Save a timeout entry to SQLite and push to Supabase."""
        log_id = None
        if self._db_conn is not None:
            try:
                log_id = _db.insert_headcount_log(
                    self._db_conn,
                    sqlite_episode_id=self._sqlite_episode_id,
                    supabase_episode_id=self._episode_id,
                    ts=ts,
                    high_count=0,
                    mid_count=0,
                    low_count=0,
                    total_count=0,
                    trigger_source=trigger_source,
                    status='timeout',
                )
            except Exception as db_err:
                print(f"[Headcount] SQLite timeout log failed: {db_err}")

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                push_headcount_log,
                ts, 0, 0, 0, 0,
                trigger_source,
                self._episode_id,
                None,
                'timeout',
            )
            try:
                pushed = bool(future.result(timeout=SUPABASE_TIMEOUT_S))
                if pushed and log_id is not None and self._db_conn is not None:
                    try:
                        _db.mark_headcount_log_synced(self._db_conn, log_id, None)
                    except Exception:
                        pass
            except FuturesTimeoutError:
                print(f"[Headcount] Supabase timeout log push timed out — will retry via sync worker.")

    def _run(self, trigger_source: str = "auto") -> None:
        import requests as _requests
        try:
            self._raw_output_dir.mkdir(parents=True, exist_ok=True)
            self._annotated_output_dir.mkdir(parents=True, exist_ok=True)

            print("[Headcount] Capturing image from ESP32-CAM...")
            try:
                capture = capture_image_stream(
                    esp32_url=self.esp32_url,
                    output_dir=self._raw_output_dir,
                )
            except _requests.exceptions.RequestException as e:
                ts = time.time()
                print(f"[Headcount] Capture failed: {e} — logging timeout entry.")
                self._log_timeout(trigger_source, ts)
                with self._lock:
                    self._last_ts = ts  # reset 30s clock so it doesn't retry immediately
                return

            if not capture:
                print("[Headcount] Capture failed — skipping.")
                return

            # Decode raw JPEG bytes to numpy array (no second disk read)
            np_arr = np.frombuffer(capture.raw_bytes, dtype=np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if frame is None:
                print("[Headcount] Failed to decode image bytes.")
                return

            # Annotated image saved separately from the raw backup
            raw_stem       = capture.saved_path.stem  # esp32_YYYYMMDD_HHMMSS_raw
            annotated_path = self._annotated_output_dir / f"{raw_stem.replace('_raw', '')}_annotated.jpg"

            result = self.process_frame(frame, annotated_path)
            self._print_result(result)

            ts = time.time()

            # Save to SQLite immediately (unsynced) so nothing is lost if Supabase is down
            log_id = None
            if self._db_conn is not None:
                try:
                    log_id = _db.insert_headcount_log(
                        self._db_conn,
                        sqlite_episode_id=self._sqlite_episode_id,
                        supabase_episode_id=self._episode_id,
                        ts=ts,
                        high_count=result.high_count,
                        mid_count=result.mid_count,
                        low_count=result.low_count,
                        total_count=result.total_count,
                        trigger_source=trigger_source,
                        annotated_path=str(annotated_path),
                    )
                except Exception as db_err:
                    print(f"[Headcount] SQLite insert failed: {db_err}")

            # Upload annotated image and push log row to Supabase (each with timeout)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(upload_headcount_image, annotated_path, annotated_path.name)
                try:
                    image_url = future.result(timeout=SUPABASE_TIMEOUT_S)
                    if image_url:
                        print(f"[Headcount] Supabase upload OK → {image_url}")
                    else:
                        print("[Headcount] Supabase upload skipped (no client or failed).")
                except FuturesTimeoutError:
                    print(f"[Headcount] Supabase upload timed out after {SUPABASE_TIMEOUT_S}s — skipping.")
                    image_url = None

            pushed = False
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    push_headcount_log,
                    ts,
                    result.high_count,
                    result.mid_count,
                    result.low_count,
                    result.total_count,
                    trigger_source,
                    self._episode_id,
                    image_url,
                )
                try:
                    pushed = bool(future.result(timeout=SUPABASE_TIMEOUT_S))
                except FuturesTimeoutError:
                    print(f"[Headcount] Supabase log push timed out after {SUPABASE_TIMEOUT_S}s — will retry via sync worker.")

            # Mark SQLite row as synced if both Supabase steps succeeded
            if pushed and log_id is not None and self._db_conn is not None:
                try:
                    _db.mark_headcount_log_synced(self._db_conn, log_id, image_url)
                except Exception as db_err:
                    print(f"[Headcount] SQLite mark-synced failed: {db_err}")

            with self._lock:
                self._last_ts = time.time()

        except Exception as e:
            print(f"[Headcount] Error: {e}")
        finally:
            with self._lock:
                self._busy = False

    def _print_result(self, result: HeadcountResult) -> None:
        print(f"[Headcount] ── Result @ {result.timestamp} ──────────────────")
        print(f"[Headcount]  High confidence (>=70%) : {result.high_count:>3} person(s)  [green]")
        print(f"[Headcount]  Mid  confidence (>=50%) : {result.mid_count:>3} person(s)  [yellow]")
        print(f"[Headcount]  Low  confidence (>=30%) : {result.low_count:>3} person(s)  [red]")
        print(f"[Headcount]  Total                   : {result.total_count:>3} person(s)")
        print(f"[Headcount]  Saved : {result.saved_path.name}")
        print(f"[Headcount] ────────────────────────────────────────────────")
