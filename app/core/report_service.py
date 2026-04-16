from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, urlparse


CSV_COLUMNS = [
    "selected",
    "manual_review",
    "score",
    "topic_phrase",
    "video_id",
    "title",
    "watch_url",
    "channel",
    "channel_id",
    "duration",
    "upload_date",
    "upload_year",
    "view_count",
    "like_count",
    "live_status",
    "availability",
    "detail_error",
    "query_hits",
    "best_rank",
    "positive_hits",
    "negative_hits",
    "content_hits",
    "tags_preview",
    "description_preview",
    "reasons",
]


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(normalize_text(v) for v in value)
    return str(value).strip()


def csv_row(item: Dict[str, Any]) -> Dict[str, Any]:
    row = {key: item.get(key) for key in CSV_COLUMNS}
    row["query_hits"] = "; ".join(item.get("query_hits") or [])
    return row


def export_outputs(items: Sequence[Dict[str, Any]], workdir: Path, full_csv: bool) -> Tuple[Path, Path, Path, Optional[Path]]:
    all_jsonl = workdir / "03_scored_candidates.jsonl"
    selected_csv = workdir / "04_selected_for_review.csv"
    selected_urls = workdir / "05_selected_urls.txt"
    all_csv: Optional[Path] = workdir / "04_all_scored.csv" if full_csv else None

    with all_jsonl.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    with selected_csv.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for item in items:
            if not item.get("selected"):
                continue
            writer.writerow(csv_row(item))

    if full_csv and all_csv is not None:
        with all_csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for item in items:
                writer.writerow(csv_row(item))

    with selected_urls.open("w", encoding="utf-8") as fh:
        for item in items:
            if item.get("selected"):
                fh.write(f"{item.get('watch_url')}\n")

    return all_jsonl, selected_csv, selected_urls, all_csv


def chunked(seq: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def load_urls_file(path: Path) -> List[str]:
    if not path.exists():
        raise SystemExit(f"URL 文件不存在: {path}")
    urls: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("http"):
            urls.append(s)
    if not urls:
        raise SystemExit(f"URL 文件没有可下载链接: {path}")
    return urls


def load_url_title_map_from_csv(workdir: Path) -> Dict[str, str]:
    csv_path = workdir / "04_selected_for_review.csv"
    if not csv_path.exists():
        return {}
    out: Dict[str, str] = {}
    try:
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                url = normalize_text(row.get("watch_url"))
                title = normalize_text(row.get("title"))
                if url and title and url not in out:
                    out[url] = title
    except Exception:
        return {}
    return out


def extract_video_id(url: str) -> str:
    try:
        p = urlparse(url.strip())
    except Exception:
        return ""
    host = (p.netloc or "").lower()
    path = (p.path or "").strip("/")
    if "youtu.be" in host and path:
        return path.split("/")[0]
    if "youtube.com" in host:
        q = parse_qs(p.query or "")
        if q.get("v"):
            return (q["v"][0] or "").strip()
        parts = [x for x in path.split("/") if x]
        if len(parts) >= 2 and parts[0] in {"shorts", "live", "embed", "v"}:
            return parts[1]
    return ""


def write_download_report_csv(
    session_dir: Path,
    download_dir: Path,
    items: Sequence[Dict[str, Any]],
    failed_urls: Sequence[str],
    failed_reason_map: Optional[Dict[str, str]] = None,
) -> Path:
    def _format_upload_date_yyyy_mm_dd(raw: Any) -> str:
        s = normalize_text(raw)
        if not s:
            return ""
        if len(s) == 8 and s.isdigit():
            return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            yyyy, mm, dd = s[:4], s[5:7], s[8:10]
            if yyyy.isdigit() and mm.isdigit() and dd.isdigit():
                return s
        return s

    out_csv = session_dir / "07_download_report.csv"
    failed_set = {u.strip() for u in failed_urls if u and u.strip()}
    failed_reason_map = failed_reason_map or {}
    failed_set.update({u.strip() for u in failed_reason_map.keys() if u and u.strip()})
    fields = [
        "视频id",
        "视频原标题",
        "视频在YouTube上传的时间",
        "视频url",
        "视频是否下载成功",
    ]
    with out_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for it in items:
            if not it.get("selected"):
                continue
            url = normalize_text(it.get("watch_url"))
            vid = normalize_text(it.get("video_id")) or extract_video_id(url)
            is_success = "否" if url in failed_set else "是"
            writer.writerow(
                {
                    "视频id": vid,
                    "视频原标题": normalize_text(it.get("title")),
                    "视频在YouTube上传的时间": _format_upload_date_yyyy_mm_dd(it.get("upload_date")),
                    "视频url": url,
                    "视频是否下载成功": is_success,
                }
            )
    return out_csv
