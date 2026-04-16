from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.core.report_service import export_outputs, normalize_text


def review_source_path(workdir: Path) -> Path:
    return workdir / "03_scored_candidates.jsonl"


def candidate_selection_key(item: dict[str, Any], index: int = 0) -> str:
    video_id = normalize_text(item.get("video_id"))
    if video_id:
        return f"video:{video_id}"
    watch_url = normalize_text(item.get("watch_url"))
    if watch_url:
        return f"url:{watch_url}"
    return f"row:{index}"


def thumbnail_url(video_id: str) -> str:
    clean_id = normalize_text(video_id)
    if not clean_id:
        return ""
    return f"https://i.ytimg.com/vi/{clean_id}/hqdefault.jpg"


def format_duration_label(value: Any) -> str:
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return "-"
    if seconds < 0:
        return "-"
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes}:{sec:02d}"


def compact_preview(value: Any, *, limit: int = 180) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    compact = re.sub(r"\s+", " ", text)
    return compact[: limit - 1] + "…" if len(compact) > limit else compact


def summarize_reasons(value: Any, *, limit: int = 2, max_chars: int = 150) -> str:
    if isinstance(value, list):
        parts = [normalize_text(part) for part in value if normalize_text(part)]
    else:
        raw = normalize_text(value).replace("\r", "\n")
        parts = [
            part.strip(" ;；,，")
            for part in re.split(r"[\n|;；]+", raw)
            if part.strip(" ;；,，")
        ]
    if not parts:
        return "暂无筛选结论"
    summary = "；".join(parts[:limit])
    return summary[: max_chars - 1] + "…" if len(summary) > max_chars else summary


def is_low_similarity(item: dict[str, Any]) -> bool:
    try:
        score = float(item.get("vector_score"))
        threshold = float(item.get("vector_threshold") or 0.08)
    except (TypeError, ValueError):
        return False
    return score < threshold


def ensure_review_metadata(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in items:
        enriched = dict(item)
        if "agent_selected" not in enriched:
            enriched["agent_selected"] = bool(enriched.get("selected"))
        normalized.append(enriched)
    return normalized


def load_review_items(workdir: Path) -> list[dict[str, Any]]:
    source = review_source_path(workdir)
    if not source.exists():
        raise FileNotFoundError(f"未找到筛选结果文件: {source}")
    items: list[dict[str, Any]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        payload = line.strip()
        if not payload:
            continue
        items.append(json.loads(payload))
    return ensure_review_metadata(items)


def review_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total_count": len(items),
        "selected_count": sum(1 for item in items if item.get("selected")),
        "agent_selected_count": sum(1 for item in items if item.get("agent_selected")),
        "manual_review_count": sum(1 for item in items if item.get("manual_review")),
        "low_similarity_count": sum(1 for item in items if is_low_similarity(item)),
        "modified_count": sum(1 for item in items if bool(item.get("selected")) != bool(item.get("agent_selected"))),
    }


def save_review_selection(workdir: Path, selected_keys: list[str]) -> list[dict[str, Any]]:
    items = load_review_items(workdir)
    wanted = {normalize_text(key) for key in selected_keys if normalize_text(key)}

    updated: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        enriched = dict(item)
        key = candidate_selection_key(enriched, index)
        enriched["selected"] = key in wanted
        updated.append(enriched)

    source = review_source_path(workdir)
    with source.open("w", encoding="utf-8") as fh:
        for item in updated:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    export_outputs(updated, workdir, full_csv=(workdir / "04_all_scored.csv").exists())
    return updated
