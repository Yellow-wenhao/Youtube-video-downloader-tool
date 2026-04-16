from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SearchVideosInput:
    queries: list[str] = field(default_factory=list)
    workdir: str = "."
    search_limit: int = 50
    binary: str = "yt-dlp"
    cookies_from_browser: str = ""
    cookies_file: str = ""
    extra_args: list[str] = field(default_factory=list)


@dataclass
class SearchVideosOutput:
    raw_count: int
    deduped_count: int
    raw_items_path: str
    deduped_items_path: str


@dataclass
class FetchVideoDetailsInput:
    workdir: str = "."
    items_path: str = ""
    workers: int = 1
    binary: str = "yt-dlp"
    cookies_from_browser: str = ""
    cookies_file: str = ""
    extra_args: list[str] = field(default_factory=list)


@dataclass
class FetchVideoDetailsOutput:
    detail_count: int
    detailed_items_path: str


@dataclass
class FilterVideosInput:
    items_path: str = ""
    topic_phrase: str = ""
    topic_aliases: list[str] = field(default_factory=list)
    min_duration: int = 120
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    lang_rules: str = "both"


@dataclass
class FilterVideosOutput:
    scored_count: int
    selected_count: int
    scored_items_path: str


@dataclass
class PrepareDownloadListInput:
    items_path: str = ""
    workdir: str = "."
    full_csv: bool = False


@dataclass
class PrepareDownloadListOutput:
    all_jsonl: str
    selected_csv: str
    selected_urls: str
    all_csv: str = ""


@dataclass
class BuildVectorIndexInput:
    items_path: str = ""
    index_path: str = ""
    dimensions: int = 384


@dataclass
class BuildVectorIndexOutput:
    index_path: str
    record_count: int
    backend: str = "hashing"


@dataclass
class KnnSearchInput:
    query: str = ""
    index_path: str = ""
    top_k: int = 20
    metric: str = "cosine"
    dimensions: int = 384
    items_path: str = ""
    output_path: str = ""
    score_threshold: float = 0.12


@dataclass
class KnnSearchOutput:
    results: list[dict[str, Any]]
    metric: str
    top_k: int
    scored_items_path: str = ""
    max_score: float = 0.0
    average_top_score: float = 0.0
    low_similarity_count: int = 0
    score_threshold: float = 0.12


@dataclass
class StartDownloadInput:
    workdir: str = "."
    task_id: str = ""
    download_dir: str = "."
    items_path: str = ""
    urls_file: str = ""
    binary: str = "yt-dlp"
    cookies_from_browser: str = ""
    cookies_file: str = ""
    extra_args: list[str] = field(default_factory=list)
    download_mode: str = "video"
    include_audio: bool = True
    video_container: str = "auto"
    max_height: Optional[int] = None
    max_bitrate_kbps: Optional[int] = None
    audio_format: str = "best"
    audio_quality: Optional[int] = None
    sponsorblock_remove: str = ""
    clean_video: bool = False
    concurrent_videos: int = 1
    concurrent_fragments: int = 4
    download_session_name: str = ""


@dataclass
class StartDownloadOutput:
    status: str
    session_dir: str = ""
    report_csv: str = ""
    failed_urls_file: str = ""


@dataclass
class RetryFailedDownloadsInput:
    workdir: str = "."
    task_id: str = ""
    download_dir: str = "."
    failed_urls_file: str = ""
    binary: str = "yt-dlp"
    cookies_from_browser: str = ""
    cookies_file: str = ""
    extra_args: list[str] = field(default_factory=list)
    download_mode: str = "video"
    include_audio: bool = True
    video_container: str = "auto"
    max_height: Optional[int] = None
    max_bitrate_kbps: Optional[int] = None
    audio_format: str = "best"
    audio_quality: Optional[int] = None
    sponsorblock_remove: str = ""
    concurrent_videos: int = 1
    concurrent_fragments: int = 4
    download_session_name: str = ""


@dataclass
class GetTaskStatusInput:
    workdir: str = "."
    session_dir: str = ""


@dataclass
class GetTaskStatusOutput:
    status: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class CheckRuntimeEnvInput:
    yt_dlp_binary: str = "yt-dlp"
    ffmpeg_binary: str = "ffmpeg"


@dataclass
class CheckRuntimeEnvOutput:
    yt_dlp_found: bool
    ffmpeg_found: bool
    yt_dlp_binary: str
    ffmpeg_binary: str
