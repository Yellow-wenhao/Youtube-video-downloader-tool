# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- `README.md` with full project overview, usage, packaging, FAQ, and roadmap.
- `LICENSE` (MIT).
- `CONTRIBUTING.md` with contribution workflow and PR/Issue guidance.

## [0.1.0] - 2026-03-20

### Added
- PySide6 desktop GUI for YouTube search/filter/download workflow.
- Queue-based workflow:
  - Step A: search & metadata collection
  - Step B: filter and URL extraction
  - Step C: queue download execution
- Real-time progress UI:
  - metadata progress
  - queue progress
  - current video progress
- Concurrent download task cards (multi-thread status panel).
- Download report generation: `07_download_report.csv`.
- Failed URL collection and retry support.
- Resume last unfinished download task support.
- Tool maintenance panel:
  - check yt-dlp / ffmpeg version status
  - update yt-dlp
  - update ffmpeg
- Packaging scripts and PyInstaller support for Windows executable distribution.

### Changed
- Refactored GUI layout for clearer tab structure and improved usability.
- Switched search input to direct single-line query text mode.
- Renamed and clarified directory semantics (video info directory vs download directory).
- Optimized startup experience:
  - background async tool check
  - lazy thumbnail loading only on visible list items
- Simplified download report columns to:
  - `video_id`, `title`, `watch_url`, `失败原因`, `上传时间`

### Fixed
- Fixed startup duplicate-window issue in packaged builds caused by wrong interpreter resolution.
- Fixed packaged app backend script resolution (`myvi_yt_batch.py` bundled with app).
- Fixed CSV Chinese display compatibility via UTF-8 BOM export.
- Fixed multiple progress display and queue state synchronization issues.
- Fixed repeated failure/retry edge behaviors and improved concise failure logging.
- Fixed ffmpeg/yt-dlp version check display logic and fallback behavior.

### Security
- Clarified legal/compliance usage boundary in project documentation.

[Unreleased]: https://github.com/Yellow-wenhao/Youtube-video-downloader-tool/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Yellow-wenhao/Youtube-video-downloader-tool/releases/tag/v0.1.0

