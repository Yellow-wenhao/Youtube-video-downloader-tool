from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.agent.planner import AgentPlanner, PlanDraft
from app.core.app_paths import default_download_dir
from app.core.download_workspace_service import download_workspace_paths
from app.core.models import TaskStep

CN_TO_EN_TERMS = {
    "测评": "review",
    "评测": "review",
    "教程": "tutorial",
    "教学": "tutorial",
    "讲解": "explained",
    "纪录片": "documentary",
    "访谈": "interview",
    "演讲": "talk",
    "课程": "course",
    "新闻": "news",
    "实拍": "footage",
    "体验": "review",
    "对比": "comparison",
    "开箱": "unboxing",
    "音乐": "music",
    "现场": "live",
    "游戏": "gameplay",
    "旅行": "travel",
    "美食": "food",
}

QUERY_DESCRIPTOR_PATTERNS = [
    r"\breview\b",
    r"\breviews\b",
    r"\bcomparison\b",
    r"\bcompare\b",
    r"\bfootage\b",
    r"\bfirst\s*look\b",
    r"测评",
    r"评测",
    r"实拍",
    r"体验",
    r"对比",
    r"教程",
    r"教学",
    r"讲解",
    r"开箱",
]


class LegacyRuleBasedPlanner(AgentPlanner):
    planner_name = "legacy_rule_based"

    def build_plan(self, user_request: str, workdir: str | Path, defaults: dict[str, Any] | None = None) -> PlanDraft:
        text = (user_request or "").strip()
        lowered = text.lower()
        defaults = defaults or {}
        workdir_str = str(Path(workdir))

        if self._is_env_request(text, lowered):
            return PlanDraft(
                title="Runtime environment check",
                intent="check_runtime_env",
                params={"workdir": workdir_str},
                steps=[TaskStep(step_id="env", title="Check runtime environment", tool_name="check_runtime_env", payload={})],
                planner_name=self.planner_name,
            )

        if self._is_status_request(text, lowered):
            return PlanDraft(
                title="Task status lookup",
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
            )

        if self._is_retry_request(text, lowered):
            params = self._extract_download_preferences(text, defaults)
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
                    requires_confirmation=not self._allows_direct_download(text),
                )
            ]
            return PlanDraft(
                title="Retry failed downloads",
                intent="retry_failed_downloads",
                params=params,
                steps=steps,
                planner_name=self.planner_name,
            )

        query_profile = self._build_query_profile(text)
        display_query = query_profile["display_query"]
        topic_phrase = query_profile["topic_phrase"]
        topic_aliases = query_profile["topic_aliases"]
        search_queries = query_profile["search_queries"]
        search_limit = self._extract_search_limit(text) or int(defaults.get("search_limit") or 30)
        years = self._extract_year_range(text)
        prefs = self._extract_download_preferences(text, defaults)
        wants_download = self._wants_download(text)

        params = {
            "query": topic_phrase or display_query,
            "display_query": display_query,
            "topic_phrase": topic_phrase,
            "topic_aliases": topic_aliases,
            "queries": search_queries,
            "search_limit": search_limit,
            "year_from": years.get("year_from"),
            "year_to": years.get("year_to"),
            "workdir": workdir_str,
            **prefs,
        }

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
                    "query": text,
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
                    "year_from": years.get("year_from"),
                    "year_to": years.get("year_to"),
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
            "download_dir": str(Path(params.get("download_dir") or default_download_dir())),
                        "items_path": "{{steps.filter.scored_items_path}}",
                        **self._download_tool_payload(params),
                    },
                    requires_confirmation=not self._allows_direct_download(text),
                )
            )

        title = f"Agent task: {topic_phrase or display_query}" if (topic_phrase or display_query) else "Agent task"
        return PlanDraft(
            title=title,
            intent="search_pipeline",
            params=params,
            steps=steps,
            planner_name=self.planner_name,
        )

    def _is_env_request(self, text: str, lowered: str) -> bool:
        keywords = ("检查环境", "环境检查", "runtime", "ffmpeg", "yt-dlp")
        return any(k in text or k in lowered for k in keywords) and any(token in text for token in ["检查", "看看", "查看", "确认"])

    def _is_status_request(self, text: str, lowered: str) -> bool:
        status_words = ("状态", "进度", "报告", "结果", "任务情况")
        action_words = ("查看", "看看", "查询", "读取", "显示")
        return any(word in text for word in status_words) and (any(word in text for word in action_words) or "status" in lowered)

    def _is_retry_request(self, text: str, lowered: str) -> bool:
        return ("重试" in text or "retry" in lowered) and ("失败" in text or "failed" in lowered)

    def _wants_download(self, text: str) -> bool:
        return "下载" in text or "download" in text.lower()

    def _allows_direct_download(self, text: str) -> bool:
        direct_markers = ("直接下载", "立即下载", "马上下载", "自动下载", "不用确认", "无需确认")
        if any(marker in text for marker in direct_markers):
            return True
        if "确认后" in text or "先筛" in text:
            return False
        return False

    def _extract_search_limit(self, text: str) -> int | None:
        patterns = [
            r"筛\s*(\d{1,3})\s*(个|条|项)?",
            r"找\s*(\d{1,3})\s*(个|条|项)?",
            r"(\d{1,3})\s*(个|条|项)\s*(视频)?",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                value = int(match.group(1))
                if 1 <= value <= 500:
                    return value
        return None

    def _extract_year_range(self, text: str) -> dict[str, int | None]:
        result: dict[str, int | None] = {"year_from": None, "year_to": None}
        m = re.search(r"(20\d{2})\s*年?\s*(以?后|之后|后|后的|起)", text)
        if m:
            result["year_from"] = int(m.group(1))
            return result
        m = re.search(r"(20\d{2})\s*年?\s*(以前|之前|前|前的)", text)
        if m:
            result["year_to"] = int(m.group(1))
            return result
        m = re.search(r"(20\d{2})\s*[-到至]\s*(20\d{2})", text)
        if m:
            y1, y2 = int(m.group(1)), int(m.group(2))
            result["year_from"] = min(y1, y2)
            result["year_to"] = max(y1, y2)
        return result

    def _extract_resolution(self, text: str) -> int | None:
        m = re.search(r"(\d{3,4})p", text.lower())
        if m:
            return int(m.group(1))
        if "4k" in text.lower():
            return 2160
        return None

    def _extract_query(self, text: str) -> str:
        for pattern in [r'"([^"]+)"', r"“([^”]+)”", r"'([^']+)'", r"‘([^’]+)’"]:
            m = re.search(pattern, text)
            if m:
                return m.group(1).strip()

        cleaned = text
        cleaned = re.sub(r"\d{1,3}\s*(个|条|项)\s*(视频)?", " ", cleaned)
        replacements = [
            r"帮我", r"请", r"给我", r"我想", r"我要", r"想要", r"搜索", r"搜一下", r"搜", r"找一下", r"找", r"下载", r"视频", r"先筛", r"筛选", r"过滤", r"筛", r"确认后再", r"确认后", r"再下载", r"然后", r"并且", r"并", r"YouTube",
        ]
        for pattern in replacements:
            cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"20\d{2}\s*年?\s*(以?后|之后|后|后的|起|以前|之前|前|前的)?", " ", cleaned)
        cleaned = re.sub(r"\d{3,4}p|4k", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\d{1,3}\s*(个|条|项)\s*(视频)?", " ", cleaned)
        cleaned = re.sub(r"[，。,\.；;：:!！?？（）()\[\]]", " ", cleaned)
        cleaned = re.sub(r"^\s*的\s+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned:
            return cleaned
        fallback = re.sub(r"[，。,\.；;：:!！?？（）()\[\]]", " ", text)
        return re.sub(r"\s+", " ", fallback).strip() or "YouTube search"

    def _build_query_profile(self, text: str) -> dict[str, Any]:
        display_query = self._extract_query(text)
        topic_phrase = self._strip_query_descriptors(display_query)
        translated_display = self._translate_known_terms(display_query)
        translated_topic = self._translate_known_terms(topic_phrase)
        english_suffixes = self._extract_english_search_suffixes(text, display_query)

        search_queries: list[str] = []
        for candidate in [
            display_query,
            topic_phrase,
            translated_display,
            self._append_suffixes(translated_topic, english_suffixes),
            self._append_suffixes(topic_phrase, self._extract_cn_search_suffixes(text, display_query)),
        ]:
            normalized = self._normalize_query(candidate)
            if normalized and normalized not in search_queries:
                search_queries.append(normalized)

        if not search_queries:
            search_queries = [display_query or "YouTube search"]

        topic_aliases: list[str] = []
        for alias in [topic_phrase, translated_topic]:
            normalized = self._normalize_query(alias)
            if normalized and normalized not in topic_aliases:
                topic_aliases.append(normalized)

        return {
            "display_query": display_query,
            "topic_phrase": topic_phrase or display_query,
            "topic_aliases": topic_aliases,
            "search_queries": search_queries[:4],
        }

    def _strip_query_descriptors(self, value: str) -> str:
        cleaned = value or ""
        for pattern in QUERY_DESCRIPTOR_PATTERNS:
            cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\b(video|videos|youtube)\b", " ", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"[，。,\.；;：:!！?？（）()\[\]]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or value.strip()

    def _translate_known_terms(self, value: str) -> str:
        translated = value or ""
        for src in sorted(CN_TO_EN_TERMS.keys(), key=len, reverse=True):
            translated = re.sub(re.escape(src), f" {CN_TO_EN_TERMS[src]} ", translated, flags=re.IGNORECASE)
        return self._normalize_query(translated)

    def _extract_english_search_suffixes(self, text: str, query: str) -> list[str]:
        lowered = f"{text} {query}".lower()
        if any(token in lowered for token in ["comparison", "对比", "vs"]):
            return ["comparison"]
        if any(token in lowered for token in ["tutorial", "教程", "教学"]):
            return ["tutorial"]
        if any(token in lowered for token in ["documentary", "纪录片"]):
            return ["documentary"]
        if any(token in lowered for token in ["interview", "访谈"]):
            return ["interview"]
        if any(token in lowered for token in ["unboxing", "开箱"]):
            return ["unboxing"]
        return ["review"]

    def _extract_cn_search_suffixes(self, text: str, query: str) -> list[str]:
        merged = f"{text} {query}"
        if any(token in merged for token in ["对比"]):
            return ["对比"]
        if any(token in merged for token in ["教程", "教学"]):
            return ["教程"]
        if any(token in merged for token in ["纪录片"]):
            return ["纪录片"]
        if any(token in merged for token in ["访谈"]):
            return ["访谈"]
        if any(token in merged for token in ["开箱"]):
            return ["开箱"]
        if any(token in merged for token in ["测评", "评测"]):
            return ["测评"]
        return []

    def _append_suffixes(self, base: str, suffixes: list[str]) -> str:
        base_norm = self._normalize_query(base)
        if not base_norm:
            return ""
        suffix_text = " ".join(suffixes).strip()
        if not suffix_text:
            return base_norm
        lowered = base_norm.lower()
        if suffix_text.lower() in lowered:
            return base_norm
        return f"{base_norm} {suffix_text}".strip()

    def _normalize_query(self, value: str) -> str:
        cleaned = re.sub(r"\s+", " ", (value or "").strip())
        cleaned = re.sub(r"^\s*的\s+", " ", cleaned)
        return cleaned.strip()

    def _extract_download_preferences(self, text: str, defaults: dict[str, Any]) -> dict[str, Any]:
        prefs: dict[str, Any] = {
            "binary": defaults.get("binary", "yt-dlp"),
            "cookies_from_browser": defaults.get("cookies_from_browser", ""),
            "cookies_file": defaults.get("cookies_file", ""),
            "extra_args": list(defaults.get("extra_args", [])),
            "metadata_workers": int(defaults.get("metadata_workers", 1)),
            "min_duration": int(defaults.get("min_duration", 30)),
            "download_dir": defaults.get("download_dir", str(default_download_dir())),
            "download_mode": defaults.get("download_mode", "video"),
            "include_audio": bool(defaults.get("include_audio", True)),
            "video_container": defaults.get("video_container", "auto"),
            "max_height": defaults.get("max_height"),
            "max_bitrate_kbps": defaults.get("max_bitrate_kbps"),
            "audio_format": defaults.get("audio_format", "best"),
            "audio_quality": defaults.get("audio_quality"),
            "sponsorblock_remove": defaults.get("sponsorblock_remove", ""),
            "clean_video": bool(defaults.get("clean_video", False)),
            "concurrent_videos": int(defaults.get("concurrent_videos", 1)),
            "concurrent_fragments": int(defaults.get("concurrent_fragments", 4)),
            "download_session_name": defaults.get("download_session_name", ""),
            "full_csv": bool(defaults.get("full_csv", False)),
        }
        resolution = self._extract_resolution(text)
        if resolution:
            prefs["max_height"] = resolution
        if "仅音频" in text or "只要音频" in text or "audio only" in text.lower():
            prefs["download_mode"] = "audio"
        if "不要音频" in text or "无音频" in text:
            prefs["include_audio"] = False
        if "mp3" in text.lower():
            prefs["download_mode"] = "audio"
            prefs["audio_format"] = "mp3"
        if "m4a" in text.lower():
            prefs["audio_format"] = "m4a"
        if "SponsorBlock" in text or "赞助片段" in text or "纯净模式" in text:
            prefs["sponsorblock_remove"] = defaults.get("sponsorblock_remove", "sponsor,selfpromo,intro,outro,interaction")
            prefs["clean_video"] = True
        return prefs

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
