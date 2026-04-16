from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.core.app_paths import (
    DEFAULT_IDLE_TIMEOUT_SECONDS,
    app_version,
    runtime_metadata_path,
    runtime_mode,
    runtime_port,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalWebRuntimeHost:
    def __init__(
        self,
        *,
        metadata_path: Path | None = None,
        mode: str | None = None,
        version: str | None = None,
        port: int | None = None,
        idle_timeout_seconds: int = DEFAULT_IDLE_TIMEOUT_SECONDS,
    ) -> None:
        self.metadata_path = metadata_path or runtime_metadata_path()
        self.mode = mode or runtime_mode()
        self.version = version or app_version()
        self.port = int(port or runtime_port())
        self.idle_timeout_seconds = int(idle_timeout_seconds)
        self.pid = os.getpid()
        self.started_at = _now_iso()
        self.last_activity_at = self.started_at
        self.last_activity_kind = "startup"
        self.active_requests = 0
        self.background_jobs = 0
        self._lock = threading.Lock()
        self._monitor_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._write_metadata(state="starting")
        if self.mode == "release" and self._monitor_thread is None:
            self._monitor_thread = threading.Thread(
                target=self._idle_monitor,
                daemon=True,
                name="ytbdlp-release-idle-monitor",
            )
            self._monitor_thread.start()

    def shutdown(self) -> None:
        self._stop_event.set()
        self.touch("shutdown", persist=False)
        self._write_metadata(state="stopped")

    def set_port(self, port: int) -> None:
        with self._lock:
            self.port = int(port)
        self._write_metadata(state="running")

    def touch(self, kind: str, *, persist: bool = True) -> None:
        with self._lock:
            self.last_activity_at = _now_iso()
            self.last_activity_kind = kind
        if persist:
            self._write_metadata(state="running")

    def request_started(self, request_name: str) -> None:
        with self._lock:
            self.active_requests += 1
        self.touch(f"request:{request_name}")

    def request_finished(self, request_name: str) -> None:
        with self._lock:
            self.active_requests = max(0, self.active_requests - 1)
        self.touch(f"request_complete:{request_name}")

    def background_job_started(self, name: str) -> None:
        with self._lock:
            self.background_jobs += 1
        self.touch(f"job:{name}")

    def background_job_finished(self, name: str) -> None:
        with self._lock:
            self.background_jobs = max(0, self.background_jobs - 1)
        self.touch(f"job_complete:{name}")

    @contextmanager
    def background_job(self, name: str) -> Iterator[None]:
        self.background_job_started(name)
        try:
            yield
        finally:
            self.background_job_finished(name)

    def _idle_monitor(self) -> None:
        while not self._stop_event.wait(15):
            if not self._should_stop_for_idle():
                continue
            self._write_metadata(state="idle_shutdown")
            os._exit(0)

    def _should_stop_for_idle(self) -> bool:
        with self._lock:
            if self.active_requests > 0 or self.background_jobs > 0:
                return False
            last_activity = self.last_activity_at
        try:
            last_timestamp = datetime.fromisoformat(last_activity.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return False
        return (time.time() - last_timestamp) >= self.idle_timeout_seconds

    def _write_metadata(self, *, state: str) -> None:
        payload = {
            "mode": self.mode,
            "state": state,
            "pid": self.pid,
            "port": self.port,
            "version": self.version,
            "started_at": self.started_at,
            "last_activity_at": self.last_activity_at,
            "last_activity_kind": self.last_activity_kind,
            "active_requests": self.active_requests,
            "background_jobs": self.background_jobs,
            "idle_timeout_seconds": self.idle_timeout_seconds,
        }
        try:
            self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
            self.metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            return


runtime_host = LocalWebRuntimeHost()
