from __future__ import annotations

import os
from pathlib import Path


APP_NAME = "YTBDLP"


def app_data_root() -> Path:
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            return Path(local_app_data) / APP_NAME
        return Path.home() / "AppData" / "Local" / APP_NAME

    if os.sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME

    xdg_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg_data_home:
        return Path(xdg_data_home) / APP_NAME.lower()
    return Path.home() / ".local" / "share" / APP_NAME.lower()


def default_workdir() -> Path:
    return app_data_root() / "workspace"


def default_download_dir(workdir: str | Path | None = None) -> Path:
    base = Path(workdir) if workdir else default_workdir()
    return base / "downloads"
