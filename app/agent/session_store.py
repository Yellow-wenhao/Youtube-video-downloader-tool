from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.models import DownloadSessionRef, TaskResult, TaskSpec


class SessionStore:
    _PREFERENCE_KEYS = (
        "recent_task_preferences",
        "recent_result_context",
        "common_filter_preferences",
    )

    def __init__(self, workdir: str | Path) -> None:
        self.workdir = Path(workdir)
        self.agent_dir = self.workdir / ".agent"
        self.agent_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.agent_dir / "session.json"

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self._blank_payload()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        return self._normalize_payload(payload)

    def save(self, payload: dict[str, Any]) -> None:
        self.path.write_text(
            json.dumps(self._normalize_payload(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _blank_payload(self) -> dict[str, Any]:
        return {
            "defaults": {},
            "last_task_id": "",
            "last_download_session": {},
            "preferences": {key: {} for key in self._PREFERENCE_KEYS},
        }

    def _normalize_payload(self, payload: Any) -> dict[str, Any]:
        normalized = self._blank_payload()
        if not isinstance(payload, dict):
            return normalized

        defaults = payload.get("defaults")
        normalized["defaults"] = dict(defaults) if isinstance(defaults, dict) else {}
        normalized["last_task_id"] = str(payload.get("last_task_id") or "")

        last_download_session = payload.get("last_download_session")
        normalized["last_download_session"] = dict(last_download_session) if isinstance(last_download_session, dict) else {}

        preferences = payload.get("preferences") if isinstance(payload.get("preferences"), dict) else payload
        normalized["preferences"] = {
            key: dict(preferences.get(key) or {}) if isinstance(preferences.get(key), dict) else {}
            for key in self._PREFERENCE_KEYS
        }
        return normalized

    def _get_preference(self, key: str) -> dict[str, Any]:
        preferences = self.load().get("preferences") or {}
        value = preferences.get(key) or {}
        return dict(value) if isinstance(value, dict) else {}

    def _update_preference(self, key: str, value: dict[str, Any]) -> None:
        payload = self.load()
        preferences = payload.get("preferences") or {}
        current = preferences.get(key) or {}
        merged = dict(current) if isinstance(current, dict) else {}
        merged.update({name: item for name, item in value.items() if item is not None})
        preferences[key] = merged
        payload["preferences"] = preferences
        self.save(payload)

    def get_defaults(self) -> dict[str, Any]:
        return self.load().get("defaults") or {}

    def update_defaults(self, defaults: dict[str, Any]) -> None:
        payload = self.load()
        merged = payload.get("defaults") or {}
        merged.update(defaults)
        payload["defaults"] = merged
        self.save(payload)

    def get_last_task_id(self) -> str:
        return str(self.load().get("last_task_id") or "")

    def set_last_task_id(self, task_id: str) -> None:
        payload = self.load()
        payload["last_task_id"] = task_id
        self.save(payload)

    def get_last_download_session(self) -> DownloadSessionRef:
        payload = self.load().get("last_download_session") or {}
        if not isinstance(payload, dict):
            return DownloadSessionRef()
        return DownloadSessionRef(
            session_dir=str(payload.get("session_dir") or ""),
            report_csv=str(payload.get("report_csv") or ""),
            failed_urls_file=str(payload.get("failed_urls_file") or ""),
            source_task_id=str(payload.get("source_task_id") or ""),
            updated_at=str(payload.get("updated_at") or ""),
        )

    def set_last_download_session(self, ref: DownloadSessionRef) -> None:
        payload = self.load()
        payload["last_download_session"] = asdict(ref)
        self.save(payload)

    def clear_last_download_session(self) -> None:
        payload = self.load()
        payload["last_download_session"] = {}
        self.save(payload)

    def get_recent_task_preferences(self) -> dict[str, Any]:
        return self._get_preference("recent_task_preferences")

    def update_recent_task_preferences(self, preferences: dict[str, Any]) -> None:
        self._update_preference("recent_task_preferences", preferences)

    def get_recent_result_context(self) -> dict[str, Any]:
        return self._get_preference("recent_result_context")

    def update_recent_result_context(self, context: dict[str, Any]) -> None:
        self._update_preference("recent_result_context", context)

    def get_common_filter_preferences(self) -> dict[str, Any]:
        return self._get_preference("common_filter_preferences")

    def update_common_filter_preferences(self, preferences: dict[str, Any]) -> None:
        self._update_preference("common_filter_preferences", preferences)

    def planner_memory_context(self) -> dict[str, Any]:
        return {
            "recent_task_preferences": self.get_recent_task_preferences(),
            "recent_result_context": self.get_recent_result_context(),
            "common_filter_preferences": self.get_common_filter_preferences(),
        }

    def remember_planned_task(
        self,
        task: TaskSpec,
        *,
        user_request: str,
        runtime_defaults: dict[str, Any] | None = None,
    ) -> None:
        params = task.params or {}
        runtime = runtime_defaults or {}
        updated_at = task.updated_at or self._now()
        self.update_recent_task_preferences(
            {
                "task_id": task.task_id,
                "title": task.title,
                "user_request": user_request,
                "intent": task.intent,
                "status": task.status.value,
                "query": str(params.get("query") or ""),
                "display_query": str(params.get("display_query") or ""),
                "topic_phrase": str(params.get("topic_phrase") or ""),
                "search_queries": list(params.get("queries") or []),
                "search_limit": params.get("search_limit"),
                "download_mode": str(params.get("download_mode") or ""),
                "include_audio": params.get("include_audio"),
                "llm_provider": str(runtime.get("llm_provider") or ""),
                "llm_model": str(runtime.get("llm_model") or ""),
                "updated_at": updated_at,
            }
        )
        self.update_common_filter_preferences(
            {
                "search_limit": params.get("search_limit"),
                "metadata_workers": params.get("metadata_workers"),
                "min_duration": params.get("min_duration"),
                "year_from": params.get("year_from"),
                "year_to": params.get("year_to"),
                "full_csv": params.get("full_csv"),
                "updated_at": updated_at,
            }
        )

    def remember_task_result(self, task: TaskSpec, result: TaskResult) -> None:
        updated_at = result.finished_at or self._now()
        self.update_recent_task_preferences(
            {
                "task_id": task.task_id,
                "title": task.title,
                "intent": task.intent,
                "status": result.status.value,
                "last_result_message": result.message,
                "updated_at": updated_at,
            }
        )
        self.update_recent_result_context(
            {
                "task_id": task.task_id,
                "task_status": result.status.value,
                "task_message": result.message,
                "updated_at": updated_at,
            }
        )

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()
