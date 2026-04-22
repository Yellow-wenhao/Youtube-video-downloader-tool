# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.5] - 2026-04-22

### Changed
- Polished the public repository surface by removing internal collaboration documents from the root and tightening the top-level file set.
- Reworked the README into a clearer product-facing homepage with distinct paths for end users and developers.

### Fixed
- Prepared a fresh tagged release after the previous `v0.1.4` GitHub release was published without bundled Windows artifacts.

## [0.1.4] - 2026-04-21

### Added
- LangGraph-based agent runtime as the primary orchestration path, including checkpoint-backed resume behavior.
- Web execution insight, failure recovery actions, and a local-only graph debug view for development.
- Release smoke coverage for launcher/runtime startup and Web agent API availability.

### Changed
- Standardized development, test, and release guidance around the Miniconda `base` environment.
- Updated the Windows release build path to reuse local `yt-dlp` / `ffmpeg` binaries when available and to enforce a single release version source.
- Promoted the browser workspace to the clear primary product surface while keeping migration-era documents as historical references.

### Fixed
- Normalized release packaging to include LangGraph runtime dependencies explicitly in PyInstaller outputs.
- Cleaned release and TODO documentation encoding inconsistencies that previously rendered Chinese text incorrectly.

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
  - `video_id`, `title`, `watch_url`, `failure_reason`, `upload_time`

### Fixed
- Fixed startup duplicate-window issue in packaged builds caused by wrong interpreter resolution.
- Fixed packaged app backend script resolution (historical batch CLI wrapper bundled with app).
- Fixed CSV Chinese display compatibility via UTF-8 BOM export.
- Fixed multiple progress display and queue state synchronization issues.
- Fixed repeated failure/retry edge behaviors and improved concise failure logging.
- Fixed ffmpeg/yt-dlp version check display logic and fallback behavior.

### Security
- Clarified legal/compliance usage boundary in project documentation.

[Unreleased]: https://github.com/Yellow-wenhao/Youtube-video-downloader-tool/compare/v0.1.5...HEAD
[0.1.5]: https://github.com/Yellow-wenhao/Youtube-video-downloader-tool/releases/tag/v0.1.5
[0.1.4]: https://github.com/Yellow-wenhao/Youtube-video-downloader-tool/releases/tag/v0.1.4
[0.1.0]: https://github.com/Yellow-wenhao/Youtube-video-downloader-tool/releases/tag/v0.1.0
