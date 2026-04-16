from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from app.adapters.yt_dlp_adapter import run_command


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_normalize_text(v) for v in value)
    return str(value).strip()


def _safe_watch_url(video_id: str, fallback: str | None = None) -> str:
    if fallback and fallback.startswith("http"):
        return fallback
    return f"https://www.youtube.com/watch?v={video_id}"


def search_candidates(
    base_cmd: Sequence[str],
    queries: Sequence[str],
    search_limit: int,
    workdir: Path,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    out_path = workdir / "01_search_candidates.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for query in queries:
            cmd = list(base_cmd) + ["--dump-single-json", "--flat-playlist", f"ytsearch{search_limit}:{query}"]
            proc = run_command(cmd, check=False)
            if proc.returncode != 0 or not proc.stdout.strip():
                record = {
                    "query": query,
                    "error": proc.stderr.strip() or proc.stdout.strip() or "search_failed",
                }
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                continue

            try:
                payload = json.loads(proc.stdout.strip().splitlines()[-1])
            except json.JSONDecodeError as exc:
                record = {
                    "query": query,
                    "error": f"json_decode_error: {exc}",
                    "raw_tail": proc.stdout.strip()[-500:],
                }
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                continue

            entries = payload.get("entries") or []
            for idx, entry in enumerate(entries, start=1):
                video_id = _normalize_text(entry.get("id") or entry.get("url"))
                if not video_id:
                    continue
                item = {
                    "query": query,
                    "search_rank": idx,
                    "video_id": video_id,
                    "title": _normalize_text(entry.get("title")),
                    "watch_url": _safe_watch_url(video_id, _normalize_text(entry.get("url"))),
                    "channel": _normalize_text(entry.get("channel") or entry.get("uploader")),
                }
                results.append(item)
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
    return results


def dedupe_by_video_id(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    for item in items:
        video_id = item.get("video_id")
        if not video_id:
            continue
        if video_id not in merged:
            merged[video_id] = dict(item)
            merged[video_id]["query_hits"] = [item.get("query")]
            merged[video_id]["best_rank"] = item.get("search_rank")
        else:
            merged[video_id]["query_hits"].append(item.get("query"))
            prev_rank = merged[video_id].get("best_rank")
            cur_rank = item.get("search_rank")
            if isinstance(cur_rank, int) and (prev_rank is None or cur_rank < prev_rank):
                merged[video_id]["best_rank"] = cur_rank
    return list(merged.values())

