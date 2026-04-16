#!/usr/bin/env python3
"""
Backward-compatible CLI adapter for the generic YouTube batch pipeline.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.cli_pipeline_service import BatchCliOptions, run_batch_cli
from app.core.app_paths import default_download_dir, default_workdir


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="按关键词搜索 YouTube，元数据筛选后可选批量下载（主题由 --topic-phrase 指定）"
    )
    parser.add_argument("--binary", default="yt-dlp", help="yt-dlp 可执行文件名或路径")
    parser.add_argument("--query-file", type=Path, help="关键词文件，每行一个搜索词，# 行为注释")
    parser.add_argument(
        "--query-text",
        action="append",
        default=[],
        help="直接输入查询词（可重复传入；若提供则优先于 --query-file）",
    )
    parser.add_argument("--workdir", type=Path, default=default_workdir(), help="中间结果输出目录")
    parser.add_argument("--download-dir", type=Path, default=default_download_dir(), help="视频下载目录")
    parser.add_argument("--search-limit", type=int, default=50, help="每个关键词抓取的搜索结果条数")
    parser.add_argument("--metadata-workers", type=int, default=1, help="第 2 步元数据抓取并发数（1=串行）")
    parser.add_argument("--min-duration", type=int, default=120, help="最低时长（秒），低于则降分且通常不入选")
    parser.add_argument(
        "--topic-phrase",
        default="",
        help="可选：主题匹配短语（为空时不按主题词过滤）",
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


def _options_from_args(args: argparse.Namespace) -> BatchCliOptions:
    return BatchCliOptions(
        binary=args.binary,
        query_file=args.query_file,
        query_text=tuple(args.query_text or ()),
        workdir=args.workdir,
        download_dir=args.download_dir,
        search_limit=args.search_limit,
        metadata_workers=args.metadata_workers,
        min_duration=args.min_duration,
        topic_phrase=args.topic_phrase,
        year_from=args.year_from,
        year_to=args.year_to,
        lang_rules=args.lang_rules,
        full_csv=args.full_csv,
        download=args.download,
        cookies_from_browser=args.cookies_from_browser or "",
        cookies_file=args.cookies_file or "",
        download_from_urls_file=args.download_from_urls_file,
        yt_extra_args=args.yt_extra_args,
        download_mode=args.download_mode,
        include_audio=args.include_audio,
        video_container=args.video_container,
        max_height=args.max_height,
        max_bitrate_kbps=args.max_bitrate_kbps,
        audio_format=args.audio_format,
        audio_quality=args.audio_quality,
        sponsorblock_remove=args.sponsorblock_remove,
        clean_video=args.clean_video,
        concurrent_videos=args.concurrent_videos,
        concurrent_fragments=args.concurrent_fragments,
        download_session_name=args.download_session_name,
    )


def main(argv: Sequence[str]) -> int:
    try:
        args = parse_args(argv)
        run_batch_cli(_options_from_args(args))
        return 0
    except RuntimeError as exc:
        print(f"[ERROR] {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
