from __future__ import annotations

import shutil


def ensure_binary(binary: str) -> None:
    if shutil.which(binary) is None:
        raise SystemExit(
            f"未找到可执行文件: {binary}\n"
            "请先安装 yt-dlp，并确保它在 PATH 里，例如:\n"
            '  python -m pip install -U "yt-dlp[default]"\n'
            "另外建议安装 ffmpeg，以便合并音视频流。"
        )

