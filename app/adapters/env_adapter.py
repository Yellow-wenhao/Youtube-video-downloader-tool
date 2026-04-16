from __future__ import annotations

from app.core.environment_service import resolve_runtime_binary


def ensure_binary(binary: str) -> None:
    resolved = resolve_runtime_binary(binary, fallback_names=(binary, f"{binary}.exe"))
    if not resolved.found:
        raise SystemExit(
            f"未找到可执行文件: {binary}\n"
            "请确认发布包内置工具完整，或者先安装 yt-dlp 并确保它在 PATH 里，例如:\n"
            '  python -m pip install -U "yt-dlp[default]"\n'
            "另外建议安装 ffmpeg，以便合并音视频流。"
        )
