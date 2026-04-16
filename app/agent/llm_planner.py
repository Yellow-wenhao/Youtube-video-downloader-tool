from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib import error, request

from app.agent.planner import (
    AgentPlanner,
    PlanDraft,
    PlannerConfigurationError,
    PlannerConnectionError,
    PlannerResponseError,
    PlannerSchemaError,
)
from app.agent.prompt_loader import render_prompt_template
from app.core.download_workspace_service import download_workspace_paths
from app.core.models import TaskStep

DEFAULT_PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "deepseek": "https://api.deepseek.com",
    "moonshot": "https://api.moonshot.cn/v1",
    "aliyun_bailian": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
}

PROVIDER_MODEL_SUGGESTIONS = {
    "openai": ["gpt-5.4", "gpt-5.3", "gpt-4.1"],
    "openrouter": ["openai/gpt-5", "anthropic/claude-3.7-sonnet", "google/gemini-2.5-pro"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "moonshot": ["kimi-k2-0711-preview", "kimi-latest"],
    "aliyun_bailian": ["qwen3.6-plus", "qwen-plus", "qwen-turbo"],
    "dashscope": ["qwen3.6-plus", "qwen-plus", "qwen-turbo"],
}


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _clean_int(value: Any, fallback: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = fallback
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _clean_optional_int(value: Any, minimum: int | None = None, maximum: int | None = None) -> int | None:
    if value in ("", None):
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _clean_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on", "是"}:
        return True
    if text in {"0", "false", "no", "n", "off", "否"}:
        return False
    return default


def provider_model_suggestions(provider: str) -> list[str]:
    provider_key = _clean_text(provider).lower()
    return list(PROVIDER_MODEL_SUGGESTIONS.get(provider_key, []))


def resolve_runtime_config(defaults: dict[str, Any] | None = None) -> dict[str, str]:
    defaults = defaults or {}
    provider = _clean_text(defaults.get("llm_provider")) or os.environ.get("YTBDLP_LLM_PROVIDER", "").strip()
    provider_key = provider.lower()
    model = _clean_text(defaults.get("llm_model")) or os.environ.get("YTBDLP_LLM_MODEL", "").strip()
    api_key = _clean_text(defaults.get("llm_api_key")) or os.environ.get("YTBDLP_LLM_API_KEY", "").strip()
    base_url = _clean_text(defaults.get("llm_base_url")) or os.environ.get("YTBDLP_LLM_BASE_URL", "").strip()
    if not base_url and provider_key in DEFAULT_PROVIDER_BASE_URLS:
        base_url = DEFAULT_PROVIDER_BASE_URLS[provider_key]

    if not provider:
        raise PlannerConfigurationError("Agent 未配置 provider。请在配置页填写 Agent Provider。")
    if not model:
        raise PlannerConfigurationError("Agent 未配置模型。请在配置页填写 Agent Model。")
    if not api_key:
        raise PlannerConfigurationError("Agent 未配置 API Key。请在配置页填写 Agent API Key。")
    if not base_url:
        raise PlannerConfigurationError("Agent 未配置 Base URL。请在配置页填写 Agent Base URL。")

    return {
        "provider": provider,
        "provider_key": provider_key,
        "model": model,
        "api_key": api_key,
        "base_url": base_url.rstrip("/"),
    }


def test_llm_connection(defaults: dict[str, Any] | None = None) -> dict[str, Any]:
    runtime = resolve_runtime_config(defaults)
    endpoint = runtime["base_url"] + "/chat/completions"
    body = {
        "model": runtime["model"],
        "temperature": 0,
        "max_tokens": 32,
        "messages": [
            {
                "role": "system",
                "content": 'Reply with strict JSON only: {"ok":true,"message":"connected"}',
            },
            {
                "role": "user",
                "content": "ping",
            },
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        response_payload = _post_json(endpoint, body, runtime)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code == 400 and "response_format" in detail:
            fallback_body = dict(body)
            fallback_body.pop("response_format", None)
            response_payload = _post_json(endpoint, fallback_body, runtime)
        else:
            raise PlannerConfigurationError(
                f"连接测试失败: HTTP {exc.code}. provider={runtime['provider']} detail={detail[:400]}"
            ) from exc
    except error.URLError as exc:
        raise PlannerConnectionError(
            f"连接测试失败，无法访问 {endpoint}: {exc}",
            details={"provider": runtime["provider"], "endpoint": endpoint},
        ) from exc

    content = _extract_message_content(response_payload)
    repaired = _parse_json_with_repair(content)
    return {
        "ok": True,
        "error_category": "success",
        "user_title": "LLM 连接测试成功",
        "user_message": "当前配置可以正常连到规划模型。",
        "user_recovery": "",
        "user_actions": [],
        "provider": runtime["provider"],
        "model": runtime["model"],
        "base_url": runtime["base_url"],
        "message": str(repaired.get("message") or "connected"),
    }


def _provider_headers(runtime: dict[str, str]) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {runtime['api_key']}",
        "User-Agent": "YTBDLP-Agent/1.0",
    }
    provider_key = runtime["provider_key"]
    if provider_key == "openrouter":
        headers["HTTP-Referer"] = "https://local.ytbdlp.app"
        headers["X-Title"] = "YTBDLP Agent Planner"
    return headers


def _post_json(endpoint: str, body: dict[str, Any], runtime: dict[str, str]) -> dict[str, Any]:
    req = request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers=_provider_headers(runtime),
        method="POST",
    )
    with request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _extract_message_content(response_payload: dict[str, Any]) -> str:
    try:
        content = response_payload["choices"][0]["message"]["content"]
    except Exception as exc:
        raise PlannerResponseError("LLM planner 响应缺少 message.content。") from exc

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                for key in ("text", "content", "value"):
                    if isinstance(item.get(key), str) and item.get(key):
                        parts.append(str(item.get(key)))
                        break
        return "\n".join(parts).strip()
    return str(content or "").strip()


def _parse_json_with_repair(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if not text:
        raise PlannerResponseError("LLM planner 返回内容为空。")

    candidates = [text]
    fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    candidates.extend(seg.strip() for seg in fenced if seg.strip())

    extracted = _extract_balanced_json_objects(text)
    candidates.extend(seg for seg in extracted if seg)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, str):
                nested = json.loads(parsed)
                if isinstance(nested, dict):
                    return nested
        except Exception:
            continue

    repaired = text.replace("\r", "\n").strip()
    repaired = re.sub(r"^\s*json\s*", "", repaired, flags=re.IGNORECASE)
    if repaired.startswith("{") and repaired.endswith("}"):
        try:
            parsed = json.loads(repaired)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    raise PlannerResponseError("LLM planner 返回内容无法解析为 JSON，二次修复也失败。")


def _extract_balanced_json_objects(text: str) -> list[str]:
    results: list[str] = []
    start = -1
    depth = 0
    in_string = False
    escape = False
    for idx, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            if depth == 0:
                start = idx
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    results.append(text[start : idx + 1].strip())
                    start = -1
    return results


class LLMPlanner(AgentPlanner):
    planner_name = "llm"
    SUPPORTED_INTENTS = {"search_pipeline", "retry_failed_downloads", "get_task_status", "check_runtime_env"}
    SUPPORTED_DOWNLOAD_MODES = {"video", "audio"}

    def build_plan(
        self,
        user_request: str,
        workdir: str | Path,
        defaults: dict[str, Any] | None = None,
    ) -> PlanDraft:
        merged_defaults = defaults or {}
        runtime = self._resolve_runtime_config(merged_defaults)
        payload = self._request_plan_payload(user_request, workdir, merged_defaults, runtime)
        return self._compile_plan(user_request, workdir, merged_defaults, payload)

    def _resolve_runtime_config(self, defaults: dict[str, Any]) -> dict[str, str]:
        return resolve_runtime_config(defaults)

    def _request_plan_payload(
        self,
        user_request: str,
        workdir: str | Path,
        defaults: dict[str, Any],
        runtime: dict[str, str],
    ) -> dict[str, Any]:
        endpoint = runtime["base_url"] + "/chat/completions"
        body = {
            "model": runtime["model"],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": self._build_system_prompt(defaults)},
                {"role": "user", "content": self._build_user_prompt(user_request, workdir, defaults)},
            ],
        }
        try:
            response_payload = _post_json(endpoint, body, runtime)
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            if exc.code == 400 and "response_format" in detail:
                fallback_body = dict(body)
                fallback_body.pop("response_format", None)
                try:
                    response_payload = _post_json(endpoint, fallback_body, runtime)
                except Exception:
                    raise PlannerConfigurationError(
                        f"LLM planner 请求失败: HTTP {exc.code}. provider={runtime['provider']} endpoint={endpoint} detail={detail[:600]}"
                    ) from exc
            else:
                raise PlannerConnectionError(
                    f"LLM planner 请求失败: HTTP {exc.code}. provider={runtime['provider']} endpoint={endpoint} detail={detail[:600]}",
                    details={"provider": runtime["provider"], "endpoint": endpoint, "http_status": exc.code},
                ) from exc
        except error.URLError as exc:
            raise PlannerConnectionError(
                f"LLM planner 无法连接到 provider={runtime['provider']} endpoint={endpoint}: {exc}",
                details={"provider": runtime["provider"], "endpoint": endpoint},
            ) from exc
        except Exception as exc:
            raise PlannerConnectionError(
                f"LLM planner 请求异常: {exc}",
                details={"provider": runtime["provider"], "endpoint": endpoint},
            ) from exc

        return _parse_json_with_repair(_extract_message_content(response_payload))

    def _build_system_prompt(self, defaults: dict[str, Any]) -> str:
        tool_defaults = {
            "search_limit": int(defaults.get("search_limit", 30) or 30),
            "min_duration": int(defaults.get("min_duration", 120) or 120),
            "metadata_workers": int(defaults.get("metadata_workers", 1) or 1),
            "download_mode": _clean_text(defaults.get("download_mode") or "video"),
            "include_audio": bool(defaults.get("include_audio", True)),
            "video_container": _clean_text(defaults.get("video_container") or "auto"),
            "max_height": _clean_text(defaults.get("max_height") or ""),
            "audio_format": _clean_text(defaults.get("audio_format") or "best"),
            "audio_quality": defaults.get("audio_quality"),
            "clean_video": bool(defaults.get("clean_video", False)),
            "concurrent_videos": int(defaults.get("concurrent_videos", 1) or 1),
            "concurrent_fragments": int(defaults.get("concurrent_fragments", 4) or 4),
        }
        return render_prompt_template(
            "system_prompt.md",
            {"TOOL_DEFAULTS_JSON": json.dumps(tool_defaults, ensure_ascii=False)},
        )

    def _build_user_prompt(self, user_request: str, workdir: str | Path, defaults: dict[str, Any]) -> str:
        context = {
            "user_request": user_request,
            "workdir": str(Path(workdir)),
            "default_download_dir": _clean_text(defaults.get("download_dir") or (Path(workdir) / "downloads")),
            "binary": _clean_text(defaults.get("binary") or "yt-dlp"),
            "cookies_from_browser": _clean_text(defaults.get("cookies_from_browser")),
            "cookies_file": _clean_text(defaults.get("cookies_file")),
            "extra_args": list(defaults.get("extra_args", [])),
            "full_csv": bool(defaults.get("full_csv", False)),
            "recent_task_preferences": defaults.get("recent_task_preferences") if isinstance(defaults.get("recent_task_preferences"), dict) else {},
            "recent_result_context": defaults.get("recent_result_context") if isinstance(defaults.get("recent_result_context"), dict) else {},
            "common_filter_preferences": defaults.get("common_filter_preferences") if isinstance(defaults.get("common_filter_preferences"), dict) else {},
        }
        return json.dumps(context, ensure_ascii=False)

    def _compile_plan(
        self,
        user_request: str,
        workdir: str | Path,
        defaults: dict[str, Any],
        payload: dict[str, Any],
    ) -> PlanDraft:
        payload = self._normalize_payload(payload)
        workdir_str = str(Path(workdir))
        intent = _clean_text(payload.get("intent") or "search_pipeline")
        planner_notes = payload.get("planner_notes")
        if not isinstance(planner_notes, list):
            planner_notes = []
        notes = [str(item) for item in planner_notes if str(item).strip()]

        if intent == "check_runtime_env":
            return PlanDraft(
                title=_clean_text(payload.get("title") or "Runtime environment check"),
                intent="check_runtime_env",
                params={"workdir": workdir_str},
                steps=[TaskStep(step_id="env", title="Check runtime environment", tool_name="check_runtime_env", payload={})],
                planner_name=self.planner_name,
                planner_notes=notes,
            )

        if intent == "get_task_status":
            return PlanDraft(
                title=_clean_text(payload.get("title") or "Task status lookup"),
                intent="get_task_status",
                params={"workdir": workdir_str},
                steps=[
                    TaskStep(
                        step_id="status",
                        title="Read task status",
                        tool_name="get_task_status",
                        payload={"workdir": workdir_str},
                    )
                ],
                planner_name=self.planner_name,
                planner_notes=notes,
            )

        if intent == "retry_failed_downloads":
            params = self._compile_common_params(workdir_str, defaults, payload)
            workspace_paths = download_workspace_paths(
                workdir_str,
                defaults=defaults,
                params=params,
            )
            steps = [
                TaskStep(
                    step_id="retry",
                    title="Retry failed downloads",
                    tool_name="retry_failed_downloads",
                    payload={
                        "workdir": workdir_str,
                        "download_dir": str(workspace_paths.download_dir),
                        "failed_urls_file": str(workspace_paths.failed_urls_file),
                        **self._download_tool_payload(params),
                    },
                    requires_confirmation=_clean_bool(payload.get("confirm_before_download"), True),
                )
            ]
            return PlanDraft(
                title=_clean_text(payload.get("title") or "Retry failed downloads"),
                intent="retry_failed_downloads",
                params=params,
                steps=steps,
                planner_name=self.planner_name,
                planner_notes=notes,
            )

        params = self._compile_common_params(workdir_str, defaults, payload)
        search_queries = params["queries"]
        search_limit = int(params["search_limit"])
        topic_phrase = _clean_text(params.get("topic_phrase"))
        topic_aliases = params.get("topic_aliases", [])
        wants_download = _clean_bool(payload.get("wants_download"), False)
        confirm_before_download = _clean_bool(payload.get("confirm_before_download"), True)

        steps = [
            TaskStep(step_id="env", title="Check runtime environment", tool_name="check_runtime_env", payload={}),
            TaskStep(
                step_id="search",
                title="Search videos",
                tool_name="search_videos",
                payload={
                    "queries": search_queries,
                    "workdir": workdir_str,
                    "search_limit": search_limit,
                    "binary": params.get("binary", "yt-dlp"),
                    "cookies_from_browser": params.get("cookies_from_browser", ""),
                    "cookies_file": params.get("cookies_file", ""),
                    "extra_args": params.get("extra_args", []),
                },
            ),
            TaskStep(
                step_id="details",
                title="Fetch detailed metadata",
                tool_name="fetch_video_details",
                payload={
                    "workdir": workdir_str,
                    "items_path": "{{steps.search.deduped_items_path}}",
                    "workers": int(params.get("metadata_workers", 1)),
                    "binary": params.get("binary", "yt-dlp"),
                    "cookies_from_browser": params.get("cookies_from_browser", ""),
                    "cookies_file": params.get("cookies_file", ""),
                    "extra_args": params.get("extra_args", []),
                },
            ),
            TaskStep(
                step_id="vector_index",
                title="Build semantic vector index",
                tool_name="build_vector_index",
                payload={
                    "items_path": "{{steps.details.detailed_items_path}}",
                    "index_path": str(Path(workdir_str) / "09_vector_index.json"),
                    "dimensions": 384,
                },
            ),
            TaskStep(
                step_id="semantic",
                title="Rank candidates by semantic similarity",
                tool_name="knn_search",
                payload={
                    "query": user_request,
                    "index_path": "{{steps.vector_index.index_path}}",
                    "items_path": "{{steps.details.detailed_items_path}}",
                    "output_path": str(Path(workdir_str) / "02b_vector_scored_candidates.jsonl"),
                    "top_k": max(200, search_limit * max(1, len(search_queries))),
                    "metric": "cosine",
                    "dimensions": 384,
                    "score_threshold": 0.08,
                },
            ),
            TaskStep(
                step_id="filter",
                title="Filter candidate videos",
                tool_name="filter_videos",
                payload={
                    "items_path": "{{steps.semantic.scored_items_path}}",
                    "topic_phrase": topic_phrase,
                    "topic_aliases": topic_aliases,
                    "min_duration": int(params.get("min_duration", 30)),
                    "year_from": params.get("year_from"),
                    "year_to": params.get("year_to"),
                    "lang_rules": "both",
                },
            ),
            TaskStep(
                step_id="prepare",
                title="Prepare download list",
                tool_name="prepare_download_list",
                payload={
                    "items_path": "{{steps.filter.scored_items_path}}",
                    "workdir": workdir_str,
                    "full_csv": bool(params.get("full_csv", False)),
                },
            ),
        ]

        if wants_download:
            steps.append(
                TaskStep(
                    step_id="download",
                    title="Download selected videos",
                    tool_name="start_download",
                    payload={
                        "workdir": workdir_str,
                        "download_dir": str(Path(params.get("download_dir") or (Path(workdir_str) / "downloads"))),
                        "items_path": "{{steps.filter.scored_items_path}}",
                        **self._download_tool_payload(params),
                    },
                    requires_confirmation=confirm_before_download,
                )
            )

        return PlanDraft(
            title=_clean_text(payload.get("title") or f"Agent task: {topic_phrase or params['display_query'] or 'YouTube search'}"),
            intent="search_pipeline",
            params=params,
            steps=steps,
            planner_name=self.planner_name,
            planner_notes=notes,
        )

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise PlannerSchemaError("LLM planner 返回了非对象计划结构。")
        normalized = dict(payload)
        intent = _clean_text(normalized.get("intent") or "search_pipeline")
        if intent not in self.SUPPORTED_INTENTS:
            raise PlannerSchemaError(
                f"LLM planner 返回了不支持的 intent: {intent}",
                details={"intent": intent, "supported_intents": sorted(self.SUPPORTED_INTENTS)},
            )
        normalized["intent"] = intent

        download_mode = _clean_text(normalized.get("download_mode") or "video").lower() or "video"
        if download_mode not in self.SUPPORTED_DOWNLOAD_MODES:
            download_mode = "video"
        normalized["download_mode"] = download_mode

        if "search_queries" in normalized and not isinstance(normalized.get("search_queries"), list):
            normalized["search_queries"] = [normalized.get("search_queries")]
        if "topic_aliases" in normalized and not isinstance(normalized.get("topic_aliases"), list):
            normalized["topic_aliases"] = [normalized.get("topic_aliases")]
        if "planner_notes" in normalized and not isinstance(normalized.get("planner_notes"), list):
            normalized["planner_notes"] = [normalized.get("planner_notes")]
        if "extra_args" in normalized and isinstance(normalized.get("extra_args"), str):
            normalized["extra_args"] = normalized["extra_args"].split()

        if normalized["intent"] == "search_pipeline":
            query = _clean_text(normalized.get("query") or normalized.get("topic_phrase"))
            search_queries = normalized.get("search_queries") or []
            if not search_queries and query:
                normalized["search_queries"] = [query]
            if not normalized.get("search_queries"):
                raise PlannerSchemaError("搜索型计划缺少 query/search_queries。")

        return normalized

    def _compile_common_params(
        self,
        workdir_str: str,
        defaults: dict[str, Any],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise PlannerSchemaError("LLM planner 返回了非对象计划结构。")
        raw_queries = payload.get("search_queries")
        if isinstance(raw_queries, list):
            search_queries = [_clean_text(item) for item in raw_queries if _clean_text(item)]
        else:
            search_queries = []
        display_query = _clean_text(payload.get("query") or payload.get("topic_phrase"))
        if not search_queries and display_query:
            search_queries = [display_query]
        if not search_queries:
            raise PlannerSchemaError(
                "LLM planner 没有返回可执行的 search_queries。",
                details={"payload_keys": sorted(payload.keys())},
            )

        raw_aliases = payload.get("topic_aliases")
        if isinstance(raw_aliases, list):
            topic_aliases = [_clean_text(item) for item in raw_aliases if _clean_text(item)]
        else:
            topic_aliases = []
        topic_phrase = _clean_text(payload.get("topic_phrase") or display_query)

        extra_args_value = payload.get("extra_args", defaults.get("extra_args", []))
        if isinstance(extra_args_value, list):
            extra_args = [str(item) for item in extra_args_value if str(item).strip()]
        elif isinstance(extra_args_value, str) and extra_args_value.strip():
            extra_args = extra_args_value.split()
        else:
            extra_args = []

        return {
            "query": topic_phrase or display_query,
            "display_query": display_query or topic_phrase,
            "topic_phrase": topic_phrase,
            "topic_aliases": topic_aliases,
            "queries": search_queries[:4],
            "search_limit": _clean_int(payload.get("search_limit", defaults.get("search_limit", 30)), 30, minimum=1, maximum=500),
            "year_from": _clean_optional_int(payload.get("year_from"), minimum=1990, maximum=2100),
            "year_to": _clean_optional_int(payload.get("year_to"), minimum=1990, maximum=2100),
            "workdir": workdir_str,
            "binary": _clean_text(defaults.get("binary") or "yt-dlp"),
            "cookies_from_browser": _clean_text(payload.get("cookies_from_browser", defaults.get("cookies_from_browser"))),
            "cookies_file": _clean_text(payload.get("cookies_file", defaults.get("cookies_file"))),
            "extra_args": extra_args,
            "metadata_workers": _clean_int(payload.get("metadata_workers", defaults.get("metadata_workers", 1)), 1, minimum=1, maximum=16),
            "min_duration": _clean_int(payload.get("min_duration", defaults.get("min_duration", 30)), 30, minimum=0, maximum=7200),
            "download_dir": _clean_text(defaults.get("download_dir") or (Path(workdir_str) / "downloads")),
            "download_mode": _clean_text(payload.get("download_mode", defaults.get("download_mode", "video"))) or "video",
            "include_audio": _clean_bool(payload.get("include_audio", defaults.get("include_audio", True)), True),
            "video_container": _clean_text(payload.get("video_container", defaults.get("video_container", "auto"))) or "auto",
            "max_height": _clean_optional_int(payload.get("max_height", defaults.get("max_height")), minimum=0, maximum=4320),
            "max_bitrate_kbps": defaults.get("max_bitrate_kbps"),
            "audio_format": _clean_text(payload.get("audio_format", defaults.get("audio_format", "best"))) or "best",
            "audio_quality": _clean_optional_int(payload.get("audio_quality", defaults.get("audio_quality")), minimum=0, maximum=10),
            "sponsorblock_remove": _clean_text(payload.get("sponsorblock_remove", defaults.get("sponsorblock_remove"))),
            "clean_video": _clean_bool(payload.get("clean_video", defaults.get("clean_video", False)), False),
            "concurrent_videos": _clean_int(payload.get("concurrent_videos", defaults.get("concurrent_videos", 1)), 1, minimum=1, maximum=8),
            "concurrent_fragments": _clean_int(payload.get("concurrent_fragments", defaults.get("concurrent_fragments", 4)), 4, minimum=1, maximum=16),
            "download_session_name": _clean_text(defaults.get("download_session_name")),
            "full_csv": _clean_bool(payload.get("full_csv", defaults.get("full_csv", False)), False),
        }

    def _download_tool_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "binary": params.get("binary", "yt-dlp"),
            "cookies_from_browser": params.get("cookies_from_browser", ""),
            "cookies_file": params.get("cookies_file", ""),
            "extra_args": list(params.get("extra_args", [])),
            "download_mode": params.get("download_mode", "video"),
            "include_audio": bool(params.get("include_audio", True)),
            "video_container": params.get("video_container", "auto"),
            "max_height": params.get("max_height"),
            "max_bitrate_kbps": params.get("max_bitrate_kbps"),
            "audio_format": params.get("audio_format", "best"),
            "audio_quality": params.get("audio_quality"),
            "sponsorblock_remove": params.get("sponsorblock_remove", ""),
            "clean_video": bool(params.get("clean_video", False)),
            "concurrent_videos": int(params.get("concurrent_videos", 1)),
            "concurrent_fragments": int(params.get("concurrent_fragments", 4)),
            "download_session_name": params.get("download_session_name", ""),
        }
