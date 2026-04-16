from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from app.adapters.yt_dlp_adapter import yt_dlp_base
from app.core.filter_service import ScoringConfig, filter_candidates
from app.core.metadata_service import fetch_detail_metadata
from app.core.report_service import export_outputs
from app.core.search_service import dedupe_by_video_id, search_candidates
from app.tools.schemas import (
    FetchVideoDetailsInput,
    FetchVideoDetailsOutput,
    FilterVideosInput,
    FilterVideosOutput,
    PrepareDownloadListInput,
    PrepareDownloadListOutput,
    SearchVideosInput,
    SearchVideosOutput,
)


def _write_jsonl(path: Path, items: List[Dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for item in items:
            fh.write(json.dumps(item, ensure_ascii=False) + "\n")


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"未找到 JSONL 文件: {path}")
    out: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        out.append(json.loads(s))
    return out


def search_videos(input_data: SearchVideosInput) -> SearchVideosOutput:
    workdir = Path(input_data.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    base = yt_dlp_base(
        input_data.binary,
        input_data.cookies_from_browser or None,
        input_data.cookies_file or None,
        input_data.extra_args,
    )
    raw_items = search_candidates(base, input_data.queries, input_data.search_limit, workdir)
    deduped = dedupe_by_video_id(raw_items)
    deduped_path = workdir / "01b_deduped_candidates.jsonl"
    _write_jsonl(deduped_path, deduped)
    return SearchVideosOutput(
        raw_count=len(raw_items),
        deduped_count=len(deduped),
        raw_items_path=str(workdir / "01_search_candidates.jsonl"),
        deduped_items_path=str(deduped_path),
    )


def fetch_video_details_tool(input_data: FetchVideoDetailsInput) -> FetchVideoDetailsOutput:
    workdir = Path(input_data.workdir)
    base = yt_dlp_base(
        input_data.binary,
        input_data.cookies_from_browser or None,
        input_data.cookies_file or None,
        input_data.extra_args,
    )
    items = _load_jsonl(Path(input_data.items_path))
    detailed = fetch_detail_metadata(base, items, workdir, workers=input_data.workers)
    return FetchVideoDetailsOutput(
        detail_count=len(detailed),
        detailed_items_path=str(workdir / "02_detailed_candidates.jsonl"),
    )


def filter_videos_tool(input_data: FilterVideosInput) -> FilterVideosOutput:
    items = _load_jsonl(Path(input_data.items_path))
    cfg = ScoringConfig(
        topic_phrase=input_data.topic_phrase,
        topic_aliases=list(input_data.topic_aliases),
        min_duration=input_data.min_duration,
        year_from=input_data.year_from,
        year_to=input_data.year_to,
        lang_rules=input_data.lang_rules,
    )
    filtered = filter_candidates(items, cfg)
    scored_path = Path(input_data.items_path).with_name("03_scored_candidates.jsonl")
    _write_jsonl(scored_path, filtered)
    selected_count = sum(1 for item in filtered if item.get("selected"))
    return FilterVideosOutput(
        scored_count=len(filtered),
        selected_count=selected_count,
        scored_items_path=str(scored_path),
    )


def prepare_download_list(input_data: PrepareDownloadListInput) -> PrepareDownloadListOutput:
    items = _load_jsonl(Path(input_data.items_path))
    all_jsonl, selected_csv, selected_urls, all_csv = export_outputs(items, Path(input_data.workdir), input_data.full_csv)
    return PrepareDownloadListOutput(
        all_jsonl=str(all_jsonl),
        selected_csv=str(selected_csv),
        selected_urls=str(selected_urls),
        all_csv=str(all_csv or ""),
    )
