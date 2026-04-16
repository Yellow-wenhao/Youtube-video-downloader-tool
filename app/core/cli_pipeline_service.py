from __future__ import annotations

import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence

from app.adapters.env_adapter import ensure_binary
from app.adapters.yt_dlp_adapter import yt_dlp_base
from app.core.app_paths import default_download_dir, default_workdir
from app.core.download_service import download_selected
from app.core.download_workspace_service import download_workspace_paths
from app.core.filter_service import ScoringConfig, filter_candidates
from app.core.metadata_service import fetch_detail_metadata
from app.core.report_service import export_outputs, load_url_title_map_from_csv, load_urls_file
from app.core.search_service import dedupe_by_video_id, search_candidates

DEFAULT_QUERIES = (
    "Python tutorial",
    "science documentary",
    "music live performance",
    "travel vlog",
    "technology review",
)


@dataclass(frozen=True)
class BatchCliOptions:
    binary: str = "yt-dlp"
    query_file: Path | None = None
    query_text: tuple[str, ...] = ()
    workdir: Path = default_workdir()
    download_dir: Path = default_download_dir()
    search_limit: int = 50
    metadata_workers: int = 1
    min_duration: int = 120
    topic_phrase: str = ""
    year_from: int | None = None
    year_to: int | None = None
    lang_rules: str = "both"
    full_csv: bool = False
    download: bool = False
    cookies_from_browser: str = ""
    cookies_file: str = ""
    download_from_urls_file: Path | None = None
    yt_extra_args: str = ""
    download_mode: str = "video"
    include_audio: bool = True
    video_container: str = "auto"
    max_height: int | None = None
    max_bitrate_kbps: int | None = None
    audio_format: str = "best"
    audio_quality: int | None = None
    sponsorblock_remove: str = ""
    clean_video: bool = False
    concurrent_videos: int = 3
    concurrent_fragments: int = 8
    download_session_name: str = ""


@dataclass(frozen=True)
class BatchCliResult:
    mode: str
    workdir: str
    download_dir: str
    archive_file: str
    query_count: int = 0
    raw_count: int = 0
    deduped_count: int = 0
    detail_count: int = 0
    selected_count: int = 0
    all_jsonl: str = ""
    selected_csv: str = ""
    selected_urls: str = ""
    all_csv: str = ""
    download_requested: bool = False


def load_queries(query_file: Path | None) -> list[str]:
    if query_file is None:
        return list(DEFAULT_QUERIES)
    queries: list[str] = []
    for line in query_file.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        queries.append(item)
    if not queries:
        raise SystemExit(f"关键词文件没有可用内容: {query_file}")
    return queries


def load_queries_from_inputs(query_file: Path | None, query_texts: Sequence[str] | None) -> list[str]:
    queries: list[str] = []
    for raw in query_texts or ():
        for line in str(raw or "").splitlines():
            item = line.strip()
            if item and not item.startswith("#"):
                queries.append(item)
    if queries:
        return queries
    return load_queries(query_file)


def run_batch_cli(
    options: BatchCliOptions,
    *,
    emit: Callable[[str], None] | None = None,
) -> BatchCliResult:
    log = emit or print
    ensure_binary(options.binary)
    options.workdir.mkdir(parents=True, exist_ok=True)

    queries = load_queries_from_inputs(options.query_file, options.query_text)
    try:
        extra_yt_args = shlex.split(options.yt_extra_args)
    except ValueError as exc:
        raise SystemExit(f"--yt-extra-args 解析失败: {exc}") from exc

    base = yt_dlp_base(
        options.binary,
        options.cookies_from_browser or None,
        options.cookies_file or None,
        extra_yt_args,
    )

    if options.year_from is not None and options.year_to is not None and options.year_from > options.year_to:
        raise SystemExit("--year-from 不能大于 --year-to")

    scoring_cfg = ScoringConfig(
        topic_phrase=options.topic_phrase,
        topic_aliases=[],
        min_duration=options.min_duration,
        year_from=options.year_from,
        year_to=options.year_to,
        lang_rules=options.lang_rules or "both",
    )
    archive_file = download_workspace_paths(
        options.workdir,
        params={"download_dir": str(options.download_dir)},
    ).archive_file

    if options.download_from_urls_file is not None:
        log(f"[下载模式] 从 URL 文件读取: {options.download_from_urls_file}")
        urls = load_urls_file(options.download_from_urls_file)
        url_title_map = load_url_title_map_from_csv(options.workdir)
        items = [{"selected": True, "watch_url": url, "title": url_title_map.get(url, "")} for url in urls]
        _run_download(options, items, archive_file, extra_yt_args)
        log(f"      下载目录: {options.download_dir}")
        log(f"      去重归档: {archive_file}")
        log("完成。")
        return BatchCliResult(
            mode="download_only",
            workdir=str(options.workdir),
            download_dir=str(options.download_dir),
            archive_file=str(archive_file),
            query_count=len(queries),
            selected_count=len(items),
            download_requested=True,
        )

    log(f"[1/4] 搜索关键词数量: {len(queries)} | 主题短语: {scoring_cfg.topic_phrase!r}")
    raw_items = search_candidates(base, queries, options.search_limit, options.workdir)
    deduped = dedupe_by_video_id(raw_items)
    log(f"      原始候选: {len(raw_items)} | 去重后: {len(deduped)}")

    log(f"[2/4] 拉取详细元数据 | 并发: {max(1, int(options.metadata_workers or 1))}")
    detailed = fetch_detail_metadata(base, deduped, options.workdir, workers=options.metadata_workers)
    log(f"      详细元数据记录: {len(detailed)}")

    log("[3/4] 本地规则筛选")
    scored = filter_candidates(detailed, scoring_cfg)
    all_jsonl, selected_csv, selected_urls, all_csv = export_outputs(
        scored,
        options.workdir,
        full_csv=options.full_csv,
    )
    selected_count = sum(1 for item in scored if item.get("selected"))
    log(f"      入选: {selected_count}")
    log(f"      JSONL: {all_jsonl}")
    log(f"      入选 CSV: {selected_csv}")
    if all_csv:
        log(f"      全量 CSV: {all_csv}")
    log(f"      URLs:  {selected_urls}")

    if options.download:
        log("[4/4] 开始下载选中视频")
        _run_download(options, scored, archive_file, extra_yt_args)
        log(f"      下载目录: {options.download_dir}")
        log(f"      去重归档: {archive_file}")
    else:
        log("[4/4] 跳过下载。确认 CSV 后，追加 --download 即可正式下载。")

    log("完成。")
    return BatchCliResult(
        mode="search_pipeline",
        workdir=str(options.workdir),
        download_dir=str(options.download_dir),
        archive_file=str(archive_file),
        query_count=len(queries),
        raw_count=len(raw_items),
        deduped_count=len(deduped),
        detail_count=len(detailed),
        selected_count=selected_count,
        all_jsonl=str(all_jsonl),
        selected_csv=str(selected_csv),
        selected_urls=str(selected_urls),
        all_csv=str(all_csv) if all_csv else "",
        download_requested=options.download,
    )


def _run_download(
    options: BatchCliOptions,
    items: Sequence[dict],
    archive_file: Path,
    extra_yt_args: Sequence[str],
) -> None:
    sponsorblock_remove = (options.sponsorblock_remove or "").strip()
    if options.clean_video and not sponsorblock_remove:
        sponsorblock_remove = "sponsor,selfpromo,intro,outro,interaction"
    download_selected(
        binary=options.binary,
        items=items,
        download_dir=options.download_dir,
        archive_file=archive_file,
        cookies_from_browser=options.cookies_from_browser or None,
        cookies_file=options.cookies_file or None,
        extra_args=extra_yt_args,
        download_mode=options.download_mode,
        include_audio=options.include_audio,
        video_container=options.video_container,
        max_height=options.max_height,
        max_bitrate_kbps=options.max_bitrate_kbps,
        audio_format=options.audio_format,
        audio_quality=options.audio_quality,
        sponsorblock_remove=sponsorblock_remove,
        concurrent_videos=options.concurrent_videos,
        concurrent_fragments=options.concurrent_fragments,
        download_session_name=options.download_session_name,
    )
