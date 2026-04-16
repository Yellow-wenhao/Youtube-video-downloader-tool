from __future__ import annotations

import concurrent.futures
import json
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from app.adapters.yt_dlp_adapter import run_command


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(_normalize_text(v) for v in value)
    return str(value).strip()


def fetch_one_detail(base_cmd: Sequence[str], item: Dict[str, Any], idx: int) -> Dict[str, Any]:
    url = item["watch_url"]
    cmd = list(base_cmd) + ["--dump-single-json", url]
    proc = run_command(cmd, check=False)
    record: Dict[str, Any] = dict(item)
    record["detail_index"] = idx

    if proc.returncode != 0 or not proc.stdout.strip():
        record["detail_error"] = proc.stderr.strip() or proc.stdout.strip() or "detail_failed"
        return record

    try:
        meta = json.loads(proc.stdout.strip().splitlines()[-1])
    except json.JSONDecodeError as exc:
        record["detail_error"] = f"json_decode_error: {exc}"
        record["detail_raw_tail"] = proc.stdout.strip()[-500:]
        return record

    record.update(
        {
            "video_id": _normalize_text(meta.get("id") or record.get("video_id")),
            "watch_url": _normalize_text(meta.get("webpage_url") or meta.get("original_url") or url),
            "title": _normalize_text(meta.get("title") or record.get("title")),
            "description": _normalize_text(meta.get("description")),
            "duration": meta.get("duration"),
            "upload_date": _normalize_text(meta.get("upload_date")),
            "channel": _normalize_text(meta.get("channel") or meta.get("uploader") or record.get("channel")),
            "channel_id": _normalize_text(meta.get("channel_id")),
            "uploader_id": _normalize_text(meta.get("uploader_id")),
            "view_count": meta.get("view_count"),
            "like_count": meta.get("like_count"),
            "live_status": _normalize_text(meta.get("live_status")),
            "is_live": bool(meta.get("is_live")),
            "was_live": bool(meta.get("was_live")),
            "availability": _normalize_text(meta.get("availability")),
            "tags": meta.get("tags") or [],
            "categories": meta.get("categories") or [],
        }
    )
    return record


def fetch_detail_metadata(
    base_cmd: Sequence[str],
    items: Sequence[Dict[str, Any]],
    workdir: Path,
    workers: int = 1,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> List[Dict[str, Any]]:
    out_path = workdir / "02_detailed_candidates.jsonl"
    total = len(items)
    if total == 0:
        out_path.write_text("", encoding="utf-8")
        return []

    max_workers = max(1, int(workers or 1))
    results: List[Dict[str, Any]] = []

    if max_workers <= 1:
        for idx, item in enumerate(items, start=1):
            results.append(fetch_one_detail(base_cmd, item, idx))
    else:
        done = 0
        lock = threading.Lock()
        step = max(1, total // 10)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(fetch_one_detail, base_cmd, item, idx) for idx, item in enumerate(items, start=1)]
            for fut in concurrent.futures.as_completed(futures):
                results.append(fut.result())
                with lock:
                    done += 1
                    if done % step == 0 or done == total:
                        if progress_callback is not None:
                            progress_callback(done, total)
                        else:
                            print(f"      元数据进度: {done}/{total}")

    results.sort(key=lambda x: int(x.get("detail_index") or 0))
    with out_path.open("w", encoding="utf-8") as fh:
        for record in results:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return results

