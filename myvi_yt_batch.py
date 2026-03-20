#!/usr/bin/env python3
"""
Batch collect and optionally download YouTube videos (car review / intro style)
using yt-dlp. 车型与关键词由 --vehicle-phrase 与 query 文件配置，不限定单一车型。

Pipeline:
1) ytsearch: 多关键词搜索
2) 按 video id 去重
3) 拉取完整元数据
4) 本地规则打分（可英文/马来意图词、可选上传年份区间）
5) 导出 JSONL / CSV / URL 列表
6) 可选 --download

Use only where you are authorized or platform terms allow.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import re
import shlex
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import parse_qs, urlparse

DEFAULT_QUERIES = [
    "Perodua Myvi review",
    "Perodua Myvi walkaround",
    "Perodua Myvi test drive",
    "Perodua Myvi interior exterior",
    "Perodua Myvi overview",
    "Perodua Myvi first look",
    "Perodua Myvi ulasan",
    "Perodua Myvi pandu uji",
    "Perodua Myvi luar dalam",
    "Perodua Myvi features",
    "Perodua Myvi specs",
    "Perodua Myvi 2022 facelift",
    "Perodua Myvi 2023 review",
    "Perodua Myvi 2024 review",
]

# 英文等通用介绍意图（--lang-rules en 或 both）
POSITIVE_INTENT_PATTERNS_EN: List[str] = [
    r"\breview\b",
    r"\boverview\b",
    r"\bfirst\s+look\b",
    r"\bwalk\s*around\b",
    r"\bwalkaround\b",
    r"\btest\s*drive\b",
    r"\bdrive\b",
    r"\binterior\b",
    r"\bexterior\b",
    r"\bfeatures?\b",
    r"\bspecs?\b",
    r"\bon\s+road\b",
    r"\blaunch\b",
    r"\bfacelift\b",
]
# 马来语等补充（--lang-rules my 或 both）
MALAY_INTENT_PATTERNS: List[str] = [
    r"\bspesifikasi\b",
    r"\bulasan\b",
    r"\bpandu\s*uji\b",
    r"\blu[ae]r\s+dalam\b",
    r"\bpengenalan\b",
    r"\bperbandingan\b",
    r"\bpenapis\b",
    r"\bciri-ciri\b",
    r"\bvideo\s+kereta\b",
]

VISUAL_REAL_CAR_HINT_PATTERNS = [
    r"\bwalk\s*around\b",
    r"\bwalkaround\b",
    r"\binterior\b",
    r"\bexterior\b",
    r"\btest\s*drive\b",
    r"\bon\s+road\b",
    r"\bpov\b",
    r"\bdrive\b",
    r"\bfootage\b",
    r"\bshowroom\b",
    r"\blaunch\b",
    r"\bpandu\s*uji\b",
    r"\blu[ae]r\s+dalam\b",
]

NEGATIVE_PATTERNS = [
    r"\bshorts\b",
    r"\bpodcast\b",
    r"\bnews\b",
    r"\baccident\b",
    r"\bcrash\b",
    r"\bdrift\b",
    r"\bdrag\b",
    r"\brace\b",
    r"\btop\s*speed\b",
    r"\bexhaust\b",
    r"\bmuffler\b",
    r"\bmodified\b",
    r"\bmodifikasi\b",
    r"\bmodification\b",
    r"\bbodykit\b",
    r"\bsound\s*system\b",
    r"\bkaraoke\b",
    r"\bdiecast\b",
    r"\btoy\b",
    r"\bbeamng\b",
    r"\bassetto\b",
    r"\bgta\b",
    r"\bets2\b",
    r"\bcompilation\b",
    r"\bedit\b",
    r"\bmusic\s+video\b",
    r"\bprice\s+list\b",
]


@dataclass
class ScoreResult:
    selected: bool
    manual_review: bool
    score: int
    reasons: List[str]
    positive_hits: str = ""
    negative_hits: str = ""
    visual_hits: str = ""


@dataclass
class ScoringConfig:
    """打分与入选条件（车型短语、上传年份区间、意图词语言）。"""

    vehicle_phrase: str
    min_duration: int
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    lang_rules: str = "both"  # en | my | both


def compile_patterns(patterns: Sequence[str]) -> List[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


def positive_intent_pattern_list(lang_rules: str) -> List[str]:
    lr = (lang_rules or "both").lower().strip()
    if lr == "en":
        return list(POSITIVE_INTENT_PATTERNS_EN)
    if lr == "my":
        return list(MALAY_INTENT_PATTERNS)
    seen: set[str] = set()
    out: List[str] = []
    for p in POSITIVE_INTENT_PATTERNS_EN + MALAY_INTENT_PATTERNS:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


VISUAL_HINT_RE = compile_patterns(VISUAL_REAL_CAR_HINT_PATTERNS)
NEGATIVE_RE = compile_patterns(NEGATIVE_PATTERNS)


def parse_upload_year(upload_date: Any) -> Optional[int]:
    s = normalize_text(upload_date)
    if len(s) >= 4 and s[:4].isdigit():
        y = int(s[:4])
        if 1990 <= y <= 2100:
            return y
    return None


def vehicle_match_flags(text: str, phrase: str) -> Tuple[bool, bool, bool]:
    """返回 (整句命中, 分词全命中, 至少一词命中)。"""
    p = phrase.strip().lower()
    tokens = [t for t in p.split() if t]
    if not tokens:
        return False, False, False
    exact = p in text
    if len(tokens) >= 2:
        loose = all(t in text for t in tokens)
        any_tok = any(t in text for t in tokens)
    else:
        loose = tokens[0] in text
        any_tok = loose
    return exact, loose, any_tok


def query_match_in_title_desc(text_td: str, query_hits: Sequence[str]) -> Tuple[bool, List[str]]:
    """
    标准严格模式：
    - 对每个查询词，若“整句命中”或“分词全命中”则视为命中。
    - 命中范围仅限 标题 + 描述（不看 tags）。
    """
    matched: List[str] = []
    base = (text_td or "").strip().lower()
    if not base:
        return False, matched
    for raw in query_hits or []:
        q = normalize_text(raw).lower()
        if not q:
            continue
        if q in base:
            matched.append(raw)
            continue
        tokens = [t for t in re.split(r"[^0-9a-z\u4e00-\u9fff]+", q) if t]
        if tokens and all(t in base for t in tokens):
            matched.append(raw)
    # 去重保序
    uniq: List[str] = []
    seen: set[str] = set()
    for m in matched:
        if m in seen:
            continue
        seen.add(m)
        uniq.append(m)
    return bool(uniq), uniq


def hits_join(hits: List[str], max_len: int = 500) -> str:
    s = "; ".join(hits[:40])
    return s if len(s) <= max_len else s[: max_len - 3] + "..."


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(normalize_text(v) for v in value)
    return str(value).strip()


def contains_any(text: str, patterns: Sequence[re.Pattern[str]]) -> Tuple[bool, List[str]]:
    hits: List[str] = []
    for pat in patterns:
        if pat.search(text):
            hits.append(pat.pattern)
    return bool(hits), hits


def ensure_binary(binary: str) -> None:
    if shutil.which(binary) is None:
        raise SystemExit(
            f"未找到可执行文件: {binary}\n"
            "请先安装 yt-dlp，并确保它在 PATH 里，例如:\n"
            '  python -m pip install -U "yt-dlp[default]"\n'
            "另外建议安装 ffmpeg，以便合并音视频流。"
        )


def run_command(cmd: Sequence[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        list(cmd),
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        msg = proc.stderr.strip() or proc.stdout.strip() or "unknown error"
        raise RuntimeError(f"命令执行失败: {' '.join(cmd)}\n{msg}")
    return proc


def yt_dlp_base(
    binary: str,
    cookies_from_browser: str | None,
    cookies_file: str | None,
    extra_args: Sequence[str] | None = None,
) -> List[str]:
    cmd = [binary, "--no-warnings", "--ignore-no-formats-error"]
    if cookies_from_browser:
        cmd += ["--cookies-from-browser", cookies_from_browser]
    if cookies_file:
        cmd += ["--cookies", cookies_file]
    if extra_args:
        cmd += [str(a) for a in extra_args if str(a).strip()]
    return cmd


def load_queries(query_file: Path | None) -> List[str]:
    if query_file is None:
        return list(DEFAULT_QUERIES)
    queries: List[str] = []
    for line in query_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        queries.append(line)
    if not queries:
        raise SystemExit(f"关键词文件没有可用内容: {query_file}")
    return queries


def load_queries_from_inputs(query_file: Path | None, query_texts: Sequence[str] | None) -> List[str]:
    queries: List[str] = []
    if query_texts:
        for raw in query_texts:
            for line in normalize_text(raw).splitlines():
                s = line.strip()
                if s and not s.startswith("#"):
                    queries.append(s)
    if queries:
        return queries
    return load_queries(query_file)


def safe_watch_url(video_id: str, fallback: str | None = None) -> str:
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
                video_id = normalize_text(entry.get("id") or entry.get("url"))
                if not video_id:
                    continue
                item = {
                    "query": query,
                    "search_rank": idx,
                    "video_id": video_id,
                    "title": normalize_text(entry.get("title")),
                    "watch_url": safe_watch_url(video_id, normalize_text(entry.get("url"))),
                    "channel": normalize_text(entry.get("channel") or entry.get("uploader")),
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


def _fetch_one_detail(base_cmd: Sequence[str], item: Dict[str, Any], idx: int) -> Dict[str, Any]:
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
            "video_id": normalize_text(meta.get("id") or record.get("video_id")),
            "watch_url": normalize_text(meta.get("webpage_url") or meta.get("original_url") or url),
            "title": normalize_text(meta.get("title") or record.get("title")),
            "description": normalize_text(meta.get("description")),
            "duration": meta.get("duration"),
            "upload_date": normalize_text(meta.get("upload_date")),
            "channel": normalize_text(meta.get("channel") or meta.get("uploader") or record.get("channel")),
            "channel_id": normalize_text(meta.get("channel_id")),
            "uploader_id": normalize_text(meta.get("uploader_id")),
            "view_count": meta.get("view_count"),
            "like_count": meta.get("like_count"),
            "live_status": normalize_text(meta.get("live_status")),
            "is_live": bool(meta.get("is_live")),
            "was_live": bool(meta.get("was_live")),
            "availability": normalize_text(meta.get("availability")),
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
            results.append(_fetch_one_detail(base_cmd, item, idx))
    else:
        done = 0
        lock = threading.Lock()
        step = max(1, total // 10)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(_fetch_one_detail, base_cmd, item, idx) for idx, item in enumerate(items, start=1)]
            for fut in concurrent.futures.as_completed(futures):
                results.append(fut.result())
                with lock:
                    done += 1
                    if done % step == 0 or done == total:
                        print(f"      元数据进度: {done}/{total}")

    results.sort(key=lambda x: int(x.get("detail_index") or 0))
    with out_path.open("w", encoding="utf-8") as fh:
        for record in results:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return results


def score_candidate(
    item: Dict[str, Any],
    cfg: ScoringConfig,
) -> ScoreResult:
    phrase = (cfg.vehicle_phrase or "").strip()

    if item.get("detail_error"):
        return ScoreResult(
            selected=False,
            manual_review=False,
            score=-99,
            reasons=[f"详细元数据提取失败: {normalize_text(item.get('detail_error'))}"],
        )

    title = normalize_text(item.get("title"))
    description = normalize_text(item.get("description"))
    tags = normalize_text(item.get("tags"))
    text_td = " ".join([title, description]).lower()
    text = " ".join([title, description, tags]).lower()

    reasons: List[str] = []

    query_hits = item.get("query_hits") or []
    if not isinstance(query_hits, list):
        query_hits = [normalize_text(query_hits)]
    query_ok, matched_queries = query_match_in_title_desc(text_td, query_hits)
    if query_ok:
        reasons.append(f"关键词严格匹配: 通过（命中 {len(matched_queries)} 条查询词）")
    else:
        reasons.append("关键词严格匹配: 不通过（标题/描述未命中查询词）")

    # 模式1（唯一模式）：不做词表打分，仅做基础硬条件过滤。
    vehicle_ok = True
    if phrase:
        exact, loose, any_tok = vehicle_match_flags(text, phrase)
        vehicle_ok = exact or loose or any_tok
        reasons.append("车型短语检查: 通过" if vehicle_ok else "车型短语检查: 未命中")
    else:
        reasons.append("车型短语检查: 未设置，跳过")

    has_visual, visual_hits = contains_any(text, VISUAL_HINT_RE)
    if has_visual:
        reasons.append(f"命中实车展示线索 {len(visual_hits)} 个")

    upload_year = parse_upload_year(item.get("upload_date"))
    year_ok = True
    if cfg.year_from is not None or cfg.year_to is not None:
        if upload_year is None:
            year_ok = False
            reasons.append("已设年份区间但无上传日期，不入选")
        else:
            if cfg.year_from is not None and upload_year < cfg.year_from:
                year_ok = False
                reasons.append(f"上传年 {upload_year} < {cfg.year_from}")
            if cfg.year_to is not None and upload_year > cfg.year_to:
                year_ok = False
                reasons.append(f"上传年 {upload_year} > {cfg.year_to}")

    duration = item.get("duration")
    if isinstance(duration, (int, float)):
        reasons.append(f"时长: {int(duration)}s")
    else:
        reasons.append("缺少时长信息")

    live_status = normalize_text(item.get("live_status")).lower()
    if item.get("is_live") or item.get("was_live") or live_status in {"is_live", "was_live", "post_live", "is_upcoming"}:
        reasons.append("直播/直播回放/待开始")

    availability = normalize_text(item.get("availability")).lower()
    if availability in {"private", "premium_only", "subscriber_only", "needs_auth"}:
        reasons.append(f"可用性受限: {availability}")

    restricted = availability in {"private", "premium_only", "subscriber_only", "needs_auth"}

    selected = (
        query_ok
        and
        vehicle_ok
        and year_ok
        and not restricted
        and not (item.get("is_live") or item.get("was_live"))
        and (
            duration is None
            or (isinstance(duration, (int, float)) and duration >= cfg.min_duration)
        )
    )

    manual_review = False
    return ScoreResult(
        selected=selected,
        manual_review=manual_review,
        score=int(selected),
        reasons=reasons,
        positive_hits="",
        negative_hits="",
        visual_hits=hits_join(visual_hits),
    )


def filter_candidates(items: Sequence[Dict[str, Any]], cfg: ScoringConfig) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for item in items:
        scored = score_candidate(item, cfg)
        enriched = dict(item)
        enriched["selected"] = scored.selected
        enriched["manual_review"] = scored.manual_review
        enriched["score"] = scored.score
        enriched["reasons"] = " | ".join(scored.reasons)
        enriched["positive_hits"] = scored.positive_hits
        enriched["negative_hits"] = scored.negative_hits
        enriched["visual_hits"] = scored.visual_hits
        enriched["vehicle_phrase"] = cfg.vehicle_phrase.strip()
        enriched["upload_year"] = parse_upload_year(item.get("upload_date"))
        tags_list = item.get("tags") or []
        if isinstance(tags_list, list):
            enriched["tags_preview"] = "; ".join(str(t) for t in tags_list)[:500]
        else:
            enriched["tags_preview"] = normalize_text(tags_list)[:500]
        enriched["description_preview"] = normalize_text(item.get("description"))[:400]
        filtered.append(enriched)
    filtered.sort(
        key=lambda x: (bool(x.get("selected")), int(x.get("score") or -999), -int(x.get("best_rank") or 999999)),
        reverse=True,
    )
    return filtered


CSV_COLUMNS = [
    "selected",
    "manual_review",
    "score",
    "vehicle_phrase",
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
    "visual_hits",
    "tags_preview",
    "description_preview",
    "reasons",
]


def _csv_row(item: Dict[str, Any]) -> Dict[str, Any]:
    row = {key: item.get(key) for key in CSV_COLUMNS}
    row["query_hits"] = "; ".join(item.get("query_hits") or [])
    return row


def export_outputs(
    items: Sequence[Dict[str, Any]],
    workdir: Path,
    full_csv: bool,
) -> Tuple[Path, Path, Path, Optional[Path]]:
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
            writer.writerow(_csv_row(item))

    if full_csv and all_csv is not None:
        with all_csv.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for item in items:
                writer.writerow(_csv_row(item))

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


def has_independent_subtitle_track(
    base_cmd: Sequence[str],
    url: str,
    timeout_sec: int = 25,
) -> Optional[bool]:
    cmd = list(base_cmd) + ["--skip-download", "--no-playlist", "-J", url]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0:
        return None
    text = (proc.stdout or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    subs = data.get("subtitles")
    auto = data.get("automatic_captions")
    has_subs = isinstance(subs, dict) and any(bool(v) for v in subs.values())
    has_auto = isinstance(auto, dict) and any(bool(v) for v in auto.values())
    return bool(has_subs or has_auto)


def cleanup_subtitle_artifacts(download_dir: Path, video_ids: Sequence[str]) -> int:
    id_set = {v.strip() for v in video_ids if v and v.strip()}
    if not id_set or not download_dir.exists():
        return 0
    subtitle_exts = {".vtt", ".srt", ".ass", ".ssa", ".ttml", ".lrc", ".srv1", ".srv2", ".srv3", ".json3"}
    removed = 0
    for fp in download_dir.rglob("*"):
        if not fp.is_file():
            continue
        if fp.suffix.lower() not in subtitle_exts:
            continue
        name = fp.name
        if not any(f"[{vid}]" in name for vid in id_set):
            continue
        try:
            fp.unlink()
            removed += 1
        except Exception:
            pass
    return removed


def sanitize_name(s: str) -> str:
    x = normalize_text(s)
    x = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff._-]+", "_", x).strip("._-")
    return x[:96] if x else "task"


def organize_sidecar_files(videos_dir: Path, json_dir: Path, desc_dir: Path) -> Tuple[int, int]:
    moved_json = 0
    moved_desc = 0
    if not videos_dir.exists():
        return moved_json, moved_desc
    for fp in list(videos_dir.rglob("*")):
        if not fp.is_file():
            continue
        target: Optional[Path] = None
        if fp.name.endswith(".info.json"):
            target = json_dir / fp.name
            moved_json += 1
        elif fp.name.endswith(".description"):
            target = desc_dir / fp.name
            moved_desc += 1
        if target is None:
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                target.unlink()
            fp.replace(target)
        except Exception:
            # 失败时不阻断主流程
            pass
    return moved_json, moved_desc


MEDIA_EXTS = {
    ".mp4",
    ".mkv",
    ".webm",
    ".m4a",
    ".mp3",
    ".opus",
    ".wav",
    ".flac",
    ".mov",
}


def _find_first_file_by_video_id(download_dir: Path, video_id: str, kind: str) -> Optional[Path]:
    if not video_id or not download_dir.exists():
        return None
    needle = f"[{video_id}]"
    for fp in download_dir.rglob("*"):
        if not fp.is_file():
            continue
        name = fp.name
        if needle not in name:
            continue
        if kind == "media":
            if fp.suffix.lower() in MEDIA_EXTS:
                return fp
        elif kind == "info_json":
            if name.endswith(".info.json"):
                return fp
        elif kind == "description":
            if name.endswith(".description"):
                return fp
    return None


def write_download_report_csv(
    session_dir: Path,
    download_dir: Path,
    items: Sequence[Dict[str, Any]],
    failed_urls: Sequence[str],
    failed_reason_map: Optional[Dict[str, str]] = None,
) -> Path:
    out_csv = session_dir / "07_download_report.csv"
    failed_set = {u.strip() for u in failed_urls if u and u.strip()}
    failed_reason_map = failed_reason_map or {}
    failed_set.update({u.strip() for u in failed_reason_map.keys() if u and u.strip()})
    fields = [
        "video_id",
        "title",
        "watch_url",
        "失败原因",
        "上传时间",
    ]
    # 用 UTF-8 BOM，兼容 Windows Excel 直接打开时的中文显示。
    with out_csv.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for it in items:
            if not it.get("selected"):
                continue
            url = normalize_text(it.get("watch_url"))
            vid = normalize_text(it.get("video_id")) or extract_video_id(url)
            failure_reason = failed_reason_map.get(url, "") if url in failed_set else ""
            writer.writerow(
                {
                    "video_id": vid,
                    "title": normalize_text(it.get("title")),
                    "watch_url": url,
                    "失败原因": failure_reason,
                    "上传时间": normalize_text(it.get("upload_date")),
                }
            )
    return out_csv

def download_option_args(
    mode: str,
    include_audio: bool,
    video_container: str,
    max_height: Optional[int],
    max_bitrate_kbps: Optional[int],
    audio_format: str,
    audio_quality: Optional[int],
) -> List[str]:
    args: List[str] = []
    m = (mode or "video").strip().lower()
    vc = (video_container or "auto").strip().lower()
    af = (audio_format or "best").strip().lower()

    if m == "audio":
        args += ["-x"]
        if af != "best":
            args += ["--audio-format", af]
        if audio_quality is not None:
            args += ["--audio-quality", str(audio_quality)]
        return args

    # video mode: 固定分辨率策略（按用户选择的分辨率精确匹配）
    if isinstance(max_height, int) and max_height > 0:
        if include_audio:
            # 优先选择固定分辨率视频+最佳音频；找不到时退化到同分辨率单文件。
            fmt = f"bv*[height={max_height}]+ba/b[height={max_height}]"
        else:
            fmt = f"bv*[height={max_height}]/b[height={max_height}]"
    else:
        # 兜底：未设置分辨率时按最佳流
        video_part = "bv*"
        if isinstance(max_bitrate_kbps, int) and max_bitrate_kbps > 0:
            video_part += f"[tbr<={max_bitrate_kbps}]"
        fmt = f"{video_part}+ba/b" if include_audio else video_part
    args += ["-f", fmt]

    if vc in {"mp4", "mkv", "webm"}:
        if include_audio:
            args += ["--merge-output-format", vc]
        else:
            args += ["--remux-video", vc]
    return args


def download_selected(
    binary: str,
    items: Sequence[Dict[str, Any]],
    download_dir: Path,
    archive_file: Path,
    cookies_from_browser: str | None,
    cookies_file: str | None,
    extra_args: Sequence[str] | None = None,
    download_mode: str = "video",
    include_audio: bool = True,
    video_container: str = "auto",
    max_height: Optional[int] = None,
    max_bitrate_kbps: Optional[int] = None,
    audio_format: str = "best",
    audio_quality: Optional[int] = None,
    sponsorblock_remove: str = "",
    batch_size: int = 25,
    concurrent_videos: int = 1,
    concurrent_fragments: int = 4,
    download_session_name: str = "",
) -> None:
    urls = [normalize_text(item.get("watch_url")) for item in items if item.get("selected")]
    urls = [u for u in urls if u]
    if not urls:
        print("[INFO] 没有命中的可下载 URL，跳过下载。")
        return
    url_to_label: Dict[str, str] = {}
    for item in items:
        if not item.get("selected"):
            continue
        u = normalize_text(item.get("watch_url"))
        if not u:
            continue
        t = normalize_text(item.get("title"))
        vid = normalize_text(item.get("video_id")) or extract_video_id(u)
        label = t or (f"id={vid}" if vid else u)
        url_to_label[u] = label

    download_dir.mkdir(parents=True, exist_ok=True)
    session_seed = sanitize_name(download_session_name or archive_file.parent.name or "task")
    if download_session_name:
        # 显式会话名：用于同一任务重试时复用同一目录，避免碎片化。
        session_dir = download_dir / session_seed
    else:
        session_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = download_dir / f"{session_ts}_{session_seed}"
    videos_dir = session_dir / "videos"
    json_dir = session_dir / "json"
    desc_dir = session_dir / "description"
    videos_dir.mkdir(parents=True, exist_ok=True)
    json_dir.mkdir(parents=True, exist_ok=True)
    desc_dir.mkdir(parents=True, exist_ok=True)
    base = yt_dlp_base(
        binary=binary,
        cookies_from_browser=cookies_from_browser,
        cookies_file=cookies_file,
        extra_args=extra_args,
    )
    base_no_cookies = yt_dlp_base(
        binary=binary,
        cookies_from_browser=None,
        cookies_file=None,
        extra_args=extra_args,
    )
    template = str(videos_dir / "%(title)s [%(id)s].%(ext)s")
    option_args = download_option_args(
        mode=download_mode,
        include_audio=include_audio,
        video_container=video_container,
        max_height=max_height,
        max_bitrate_kbps=max_bitrate_kbps,
        audio_format=audio_format,
        audio_quality=audio_quality,
    )
    sblock_args: List[str] = []
    if sponsorblock_remove.strip():
        sblock_args = ["--sponsorblock-remove", sponsorblock_remove.strip()]
    # 统一策略：不下载字幕文件、不嵌入字幕（无论是否存在独立字幕轨）
    subtitle_policy_args = ["--no-write-subs", "--no-write-auto-subs", "--no-embed-subs"]
    progress_args = [
        "--newline",
        "--progress-template",
        "download:[PROG] %(info.id)s|%(progress._percent_str)s|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|%(progress.total_bytes_estimate)s|%(progress.speed)s",
    ]
    dl_parallel_args: List[str] = []
    if isinstance(concurrent_fragments, int) and concurrent_fragments > 1:
        dl_parallel_args += ["--concurrent-fragments", str(concurrent_fragments)]
    had_success = False
    errors: List[str] = []
    log_lock = threading.Lock()
    failed_urls: List[str] = []
    failed_reason_map: Dict[str, str] = {}
    print("[INFO] 画面中的烧录字幕(硬字幕)无法由 yt-dlp 剔除，本流程不会尝试处理硬字幕。")

    def _log(msg: str) -> None:
        with log_lock:
            print(msg, flush=True)

    def _summarize_error_text(msg: str) -> str:
        txt = (msg or "").strip()
        if not txt:
            return "unknown download error"
        lines = [ln.strip() for ln in txt.splitlines() if ln.strip()]
        # 优先抓 yt-dlp 的 ERROR 行，避免把正常日志当成失败原因。
        err_lines = [ln for ln in lines if "ERROR:" in ln or ln.startswith("ERROR")]
        if err_lines:
            return " | ".join(err_lines[-3:])
        # 其次抓常见失败关键字行
        bad_keys = ("HTTP Error", "403", "429", "timed out", "Unable to download", "Unsupported URL")
        bad_lines = [ln for ln in lines if any(k in ln for k in bad_keys)]
        if bad_lines:
            return " | ".join(bad_lines[-2:])
        return lines[-1][:400]

    def _classify_failure_reason(text: str) -> str:
        t = (text or "").lower()
        if not t:
            return "未知错误"
        if "no video formats found" in t or "no formats found" in t:
            return "无可用视频格式"
        if "private video" in t or "this video is private" in t:
            return "视频私有不可访问"
        if "members-only" in t or "membership" in t:
            return "会员专享限制"
        if "sign in to confirm your age" in t or "age-restricted" in t:
            return "年龄限制"
        if "video unavailable" in t:
            return "视频不可用/下架"
        if "403" in t or "forbidden" in t:
            return "访问被拒绝(403)"
        if "429" in t or "too many requests" in t:
            return "请求过于频繁(429)"
        if "timed out" in t or "timeout" in t or "connection reset" in t or "network is unreachable" in t:
            return "网络连接异常"
        if "unable to extract" in t or "unsupported url" in t or "extractor" in t:
            return "解析失败"
        if "copyright" in t or "blocked in your country" in t or "geo" in t:
            return "版权/地区限制"
        if "sponsorblock" in t:
            return "SponsorBlock相关失败"
        return "其他错误"

    def _run_download_once(cmd: Sequence[str], stream_output: bool) -> Tuple[int, str]:
        if stream_output:
            proc = subprocess.Popen(
                list(cmd),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            out_chunks: List[str] = []
            assert proc.stdout is not None
            for line in proc.stdout:
                out_chunks.append(line)
                _log(line.rstrip("\r\n"))
            proc.wait()
            return proc.returncode, "".join(out_chunks).strip()
        proc = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        text = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, text.strip()

    def _process_group(group: Sequence[str], stream_output: bool, task_idx: int, total_tasks: int) -> Tuple[bool, List[str]]:
        local_errors: List[str] = []
        group_head = group[0] if group else "<empty>"
        group_vid = extract_video_id(group_head)
        group_label = url_to_label.get(group_head, extract_video_id(group_head) or group_head)
        _log(f"[Q] 开始任务 {task_idx}/{total_tasks} | 视频数: {len(group)} | 视频: {group_label} | id: {group_vid or '-'}")
        soft_sub_ids: List[str] = []
        soft_sub_count = 0
        unknown_sub_count = 0
        for u in group:
            has_sub = has_independent_subtitle_track(base, u)
            # cookies 探测失败时，尝试一次无 cookies 探测
            if has_sub is None and (cookies_from_browser or cookies_file):
                has_sub = has_independent_subtitle_track(base_no_cookies, u)
            vid = extract_video_id(u)
            if has_sub is True:
                soft_sub_count += 1
                if vid:
                    soft_sub_ids.append(vid)
            elif has_sub is None:
                unknown_sub_count += 1
        if soft_sub_count > 0:
            _log(
                f"[INFO] 本批次检测到 {soft_sub_count} 个视频存在独立字幕轨(subtitles/automatic_captions)，"
                "已禁用字幕下载/嵌入，并将在下载后清理可能残留的字幕文件。"
            )
        if unknown_sub_count > 0:
            _log(
                f"[WARN] 本批次有 {unknown_sub_count} 个视频字幕轨探测失败，"
                "将继续下载，但仍强制禁用字幕下载/嵌入。"
            )

        if cookies_from_browser or cookies_file:
            _log("[INFO] 下载批次使用 cookies。")
        cmd = list(base) + [
            "--download-archive",
            str(archive_file),
            "--no-overwrites",
            "--write-info-json",
            "--write-description",
            "--ignore-errors",
            "--no-abort-on-error",
            "--restrict-filenames",
            "-o",
            template,
            *option_args,
            *progress_args,
            *dl_parallel_args,
            *sblock_args,
            *subtitle_policy_args,
            *group,
        ]
        code, msg = _run_download_once(cmd, stream_output=stream_output)
        if code == 0:
            removed = cleanup_subtitle_artifacts(download_dir, soft_sub_ids)
            if removed > 0:
                _log(f"[INFO] 已清理字幕相关产物: {removed} 个文件")
            _log(f"[Q] 完成任务 {task_idx}/{total_tasks} | 状态: 成功 | 视频: {group_label} | id: {group_vid or '-'}")
            return True, local_errors

        msg = msg or "unknown download error"
        concise = _summarize_error_text(msg)
        local_errors.append(f"视频={group_label} | url={group_head} | {concise}")

        # 某些环境下 browser cookies 会导致 Youtube 返回不可下载格式，失败时自动去 cookies 重试一次
        no_formats = "No video formats found" in msg
        has_cookie_opt = bool(cookies_from_browser or cookies_file)
        if no_formats and has_cookie_opt:
            _log("[WARN] 检测到 'No video formats found'，尝试不带 cookies 重试该批次...")
            retry_cmd = list(base_no_cookies) + [
                "--download-archive",
                str(archive_file),
                "--no-overwrites",
                "--write-info-json",
                "--write-description",
                "--ignore-errors",
                "--no-abort-on-error",
                "--restrict-filenames",
                "-o",
                template,
                *option_args,
                *progress_args,
                *dl_parallel_args,
                *sblock_args,
                *subtitle_policy_args,
                *group,
            ]
            retry_code, retry_msg = _run_download_once(retry_cmd, stream_output=stream_output)
            if retry_code == 0:
                removed = cleanup_subtitle_artifacts(download_dir, soft_sub_ids)
                if removed > 0:
                    _log(f"[INFO] 已清理字幕相关产物: {removed} 个文件")
                _log(f"[Q] 完成任务 {task_idx}/{total_tasks} | 状态: 成功(重试后) | 视频: {group_label} | id: {group_vid or '-'}")
                return True, local_errors
            retry_msg = retry_msg or "retry failed"
            retry_concise = _summarize_error_text(retry_msg)
            local_errors.append(f"视频={group_label} | url={group_head} | retry_without_cookies_failed: {retry_concise}")

        # SponsorBlock 偶发网络失败时，自动禁用 SponsorBlock 再尝试一次。
        if sblock_args:
            _log("[WARN] 检测到失败，尝试禁用 SponsorBlock 后重试该任务...")
            retry_no_sb_cmd = list(base) + [
                "--download-archive",
                str(archive_file),
                "--no-overwrites",
                "--write-info-json",
                "--write-description",
                "--ignore-errors",
                "--no-abort-on-error",
                "--restrict-filenames",
                "-o",
                template,
                *option_args,
                *progress_args,
                *dl_parallel_args,
                *subtitle_policy_args,
                *group,
            ]
            no_sb_code, no_sb_msg = _run_download_once(retry_no_sb_cmd, stream_output=stream_output)
            if no_sb_code == 0:
                removed = cleanup_subtitle_artifacts(download_dir, soft_sub_ids)
                if removed > 0:
                    _log(f"[INFO] 已清理字幕相关产物: {removed} 个文件")
                _log(f"[Q] 完成任务 {task_idx}/{total_tasks} | 状态: 成功(禁用 SponsorBlock 重试后) | 视频: {group_label} | id: {group_vid or '-'}")
                return True, local_errors
            no_sb_msg = no_sb_msg or "retry_without_sponsorblock_failed"
            local_errors.append(
                f"视频={group_label} | url={group_head} | retry_without_sponsorblock_failed: {_summarize_error_text(no_sb_msg)}"
            )

        # 即使批次失败，也尽量清理已存在的字幕产物
        removed = cleanup_subtitle_artifacts(download_dir, soft_sub_ids)
        if removed > 0:
            _log(f"[INFO] 已清理字幕相关产物: {removed} 个文件")
        _log(f"[Q] 完成任务 {task_idx}/{total_tasks} | 状态: 失败 | 视频: {group_label} | id: {group_vid or '-'}")
        with log_lock:
            failed_reason_map[group_head] = _classify_failure_reason(local_errors[-1] if local_errors else "")
        return False, local_errors

    cv = max(1, int(concurrent_videos or 1))
    if cv <= 1:
        groups = list(chunked(urls, batch_size))
        total_tasks = len(groups)
        for idx, group in enumerate(groups, start=1):
            ok, local_errors = _process_group(group, stream_output=True, task_idx=idx, total_tasks=total_tasks)
            if ok:
                had_success = True
            errors.extend(local_errors)
    else:
        print(f"[INFO] 并发下载模式：并发视频数={cv}，分片并发={max(1, int(concurrent_fragments or 1))}")
        groups = [[u] for u in urls]
        total_tasks = len(groups)
        failed_tasks = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=cv) as ex:
            futures = [ex.submit(_process_group, g, True, i + 1, total_tasks) for i, g in enumerate(groups)]
            for fut in concurrent.futures.as_completed(futures):
                ok, local_errors = fut.result()
                if ok:
                    had_success = True
                errors.extend(local_errors)
                if local_errors:
                    failed_tasks += 1
                    with log_lock:
                        tail = local_errors[-1]
                        print(f"[WARN] 并发任务失败(任务 {failed_tasks}/{total_tasks}): {tail}", flush=True)
                    m = re.search(r"url=(https?://\S+)\s*\|", tail)
                    if m:
                        failed_url = m.group(1)
                        failed_urls.append(failed_url)
                        with log_lock:
                            if failed_url not in failed_reason_map:
                                failed_reason_map[failed_url] = _classify_failure_reason(tail)

    if failed_urls:
        failed_file = archive_file.with_name("06_failed_urls.txt")
        uniq = []
        seen = set()
        for u in failed_urls:
            if u in seen:
                continue
            seen.add(u)
            uniq.append(u)
        failed_file.write_text("\n".join(uniq) + "\n", encoding="utf-8")
        print(f"[WARN] 本次有 {len(uniq)} 个 URL 下载失败，已写入: {failed_file}")

    moved_json, moved_desc = organize_sidecar_files(videos_dir, json_dir, desc_dir)
    print(f"[INFO] 下载产物目录: {session_dir}")
    try:
        (archive_file.parent / "08_last_download_session.txt").write_text(str(session_dir), encoding="utf-8")
    except Exception:
        pass
    if moved_json or moved_desc:
        print(f"[INFO] 已整理附属文件: json={moved_json} | description={moved_desc}")

    report_csv = write_download_report_csv(
        session_dir=session_dir,
        download_dir=session_dir,
        items=items,
        failed_urls=failed_urls,
        failed_reason_map=failed_reason_map,
    )
    print(f"[INFO] 下载结果汇总: {report_csv}")

    if not had_success:
        tail = errors[-1] if errors else "unknown download error"
        raise RuntimeError(f"下载未成功完成（全部批次失败）。最近错误:\n{tail}")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="按关键词搜索 YouTube，元数据筛选后可选批量下载（车型由 --vehicle-phrase 指定）"
    )
    parser.add_argument("--binary", default="yt-dlp", help="yt-dlp 可执行文件名或路径")
    parser.add_argument("--query-file", type=Path, help="关键词文件，每行一个搜索词，# 行为注释")
    parser.add_argument(
        "--query-text",
        action="append",
        default=[],
        help="直接输入查询词（可重复传入；若提供则优先于 --query-file）",
    )
    parser.add_argument("--workdir", type=Path, default=Path("./myvi_dataset"), help="中间结果输出目录")
    parser.add_argument("--download-dir", type=Path, default=Path("./myvi_downloads"), help="视频下载目录")
    parser.add_argument("--search-limit", type=int, default=50, help="每个关键词抓取的搜索结果条数")
    parser.add_argument("--metadata-workers", type=int, default=1, help="第 2 步元数据抓取并发数（1=串行）")
    parser.add_argument("--min-duration", type=int, default=120, help="最低时长（秒），低于则降分且通常不入选")
    parser.add_argument(
        "--vehicle-phrase",
        default="",
        help="可选：车型匹配短语（为空时不按车型词过滤）",
    )
    parser.add_argument(
        "--year-from",
        type=int,
        default=None,
        metavar="Y",
        help="仅保留上传年份 >= Y（需元数据 upload_date，与 --year-to 可配合分批按年抓）",
    )
    parser.add_argument("--year-to", type=int, default=None, metavar="Y", help="仅保留上传年份 <= Y")
    parser.add_argument(
        "--lang-rules",
        choices=("en", "my", "both"),
        default="both",
        help="兼容保留参数（当前筛选不再使用意图词/排除词词表）",
    )
    parser.add_argument(
        "--full-csv",
        action="store_true",
        help="额外写出 04_all_scored.csv（全部候选打分行，便于清洗数据集）",
    )
    parser.add_argument("--download", action="store_true", help="对入选 URL 执行下载")
    parser.add_argument("--cookies-from-browser", help="例如 chrome, firefox, edge")
    parser.add_argument("--cookies-file", help="Netscape 格式 cookies 文件路径")
    parser.add_argument(
        "--download-from-urls-file",
        type=Path,
        default=None,
        help="仅下载模式：从 URL 文本文件读取链接并下载（每行一个 URL）",
    )
    parser.add_argument(
        "--yt-extra-args",
        default="",
        help="透传给 yt-dlp 的附加参数字符串，例如: --proxy http://127.0.0.1:7890 --retries 20",
    )
    parser.add_argument(
        "--download-mode",
        choices=("video", "audio"),
        default="video",
        help="下载模式：video 视频（默认）或 audio 仅音频",
    )
    parser.add_argument(
        "--include-audio",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="视频模式下是否合并音频（默认开启，可用 --no-include-audio 关闭）",
    )
    parser.add_argument(
        "--video-container",
        choices=("auto", "mp4", "mkv", "webm"),
        default="auto",
        help="视频封装格式偏好（auto/mp4/mkv/webm）",
    )
    parser.add_argument(
        "--max-height",
        type=int,
        default=None,
        metavar="H",
        help="固定下载分辨率高度，如 1080",
    )
    parser.add_argument(
        "--max-bitrate-kbps",
        type=int,
        default=None,
        metavar="K",
        help="视频总码率上限（kbps），例如 3500",
    )
    parser.add_argument(
        "--audio-format",
        choices=("best", "mp3", "m4a", "opus", "wav", "flac"),
        default="best",
        help="音频格式（audio 模式下生效）",
    )
    parser.add_argument(
        "--audio-quality",
        type=int,
        default=None,
        choices=range(0, 11),
        metavar="Q",
        help="音频质量 0-10（audio 模式下生效，0 最佳）",
    )
    parser.add_argument(
        "--sponsorblock-remove",
        default="",
        help="SponsorBlock 移除类别（逗号分隔），例如 sponsor,selfpromo,intro,outro,interaction",
    )
    parser.add_argument(
        "--clean-video",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="纯净模式：自动移除常见广告/赞助片段（YouTube 有效）",
    )
    parser.add_argument("--concurrent-videos", type=int, default=3, help="并发下载视频数（1=串行）")
    parser.add_argument("--concurrent-fragments", type=int, default=8, help="单视频分片并发数（yt-dlp -N）")
    parser.add_argument(
        "--download-session-name",
        default="",
        help="下载任务目录名（会自动加时间戳并做文件名安全化）",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    try:
        args = parse_args(argv)
        ensure_binary(args.binary)

        args.workdir.mkdir(parents=True, exist_ok=True)
        queries = load_queries_from_inputs(args.query_file, args.query_text)
        try:
            extra_yt_args = shlex.split(args.yt_extra_args)
        except ValueError as exc:
            raise SystemExit(f"--yt-extra-args 解析失败: {exc}") from exc

        base = yt_dlp_base(args.binary, args.cookies_from_browser, args.cookies_file, extra_yt_args)

        if args.year_from is not None and args.year_to is not None and args.year_from > args.year_to:
            raise SystemExit("--year-from 不能大于 --year-to")

        scoring_cfg = ScoringConfig(
            vehicle_phrase=args.vehicle_phrase,
            min_duration=args.min_duration,
            year_from=args.year_from,
            year_to=args.year_to,
            lang_rules="both",
        )

        if args.download_from_urls_file is not None:
            print(f"[下载模式] 从 URL 文件读取: {args.download_from_urls_file}")
            urls = load_urls_file(args.download_from_urls_file)
            url_title_map = load_url_title_map_from_csv(args.workdir)
            items = [{"selected": True, "watch_url": u, "title": url_title_map.get(u, "")} for u in urls]
            archive_file = args.workdir / "download_archive.txt"
            sblock_remove = args.sponsorblock_remove.strip()
            if args.clean_video and not sblock_remove:
                sblock_remove = "sponsor,selfpromo,intro,outro,interaction"
            download_selected(
                binary=args.binary,
                items=items,
                download_dir=args.download_dir,
                archive_file=archive_file,
                cookies_from_browser=args.cookies_from_browser,
                cookies_file=args.cookies_file,
                extra_args=extra_yt_args,
                download_mode=args.download_mode,
                include_audio=args.include_audio,
                video_container=args.video_container,
                max_height=args.max_height,
                max_bitrate_kbps=args.max_bitrate_kbps,
                audio_format=args.audio_format,
                audio_quality=args.audio_quality,
                sponsorblock_remove=sblock_remove,
                concurrent_videos=args.concurrent_videos,
                concurrent_fragments=args.concurrent_fragments,
                download_session_name=args.download_session_name,
            )
            print(f"      下载目录: {args.download_dir}")
            print(f"      去重归档: {archive_file}")
            print("完成。")
            return 0

        print(f"[1/4] 搜索关键词数量: {len(queries)} | 车型短语: {scoring_cfg.vehicle_phrase!r}")
        raw_items = search_candidates(base, queries, args.search_limit, args.workdir)
        deduped = dedupe_by_video_id(raw_items)
        print(f"      原始候选: {len(raw_items)} | 去重后: {len(deduped)}")

        print(f"[2/4] 拉取详细元数据 | 并发: {max(1, int(args.metadata_workers or 1))}")
        detailed = fetch_detail_metadata(base, deduped, args.workdir, workers=args.metadata_workers)
        print(f"      详细元数据记录: {len(detailed)}")

        print("[3/4] 本地规则筛选")
        scored = filter_candidates(detailed, scoring_cfg)
        all_jsonl, selected_csv, selected_urls, all_csv = export_outputs(
            scored, args.workdir, full_csv=args.full_csv
        )
        selected_count = sum(1 for item in scored if item.get("selected"))
        print(f"      入选: {selected_count}")
        print(f"      JSONL: {all_jsonl}")
        print(f"      入选 CSV: {selected_csv}")
        if all_csv:
            print(f"      全量 CSV: {all_csv}")
        print(f"      URLs:  {selected_urls}")

        if args.download:
            print("[4/4] 开始下载选中视频")
            archive_file = args.workdir / "download_archive.txt"
            sblock_remove = args.sponsorblock_remove.strip()
            if args.clean_video and not sblock_remove:
                sblock_remove = "sponsor,selfpromo,intro,outro,interaction"
            download_selected(
                binary=args.binary,
                items=scored,
                download_dir=args.download_dir,
                archive_file=archive_file,
                cookies_from_browser=args.cookies_from_browser,
                cookies_file=args.cookies_file,
                extra_args=extra_yt_args,
                download_mode=args.download_mode,
                include_audio=args.include_audio,
                video_container=args.video_container,
                max_height=args.max_height,
                max_bitrate_kbps=args.max_bitrate_kbps,
                audio_format=args.audio_format,
                audio_quality=args.audio_quality,
                sponsorblock_remove=sblock_remove,
                concurrent_videos=args.concurrent_videos,
                concurrent_fragments=args.concurrent_fragments,
                download_session_name=args.download_session_name,
            )
            print(f"      下载目录: {args.download_dir}")
            print(f"      去重归档: {archive_file}")
        else:
            print("[4/4] 跳过下载。确认 CSV 后，追加 --download 即可正式下载。")

        print("完成。")
        return 0
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


