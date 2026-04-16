from __future__ import annotations

import os
import sys
from pathlib import Path


PRODUCT_NAME = "YouTube Downloader"
APP_DIR_NAME = "YouTube Downloader"
RUNTIME_MODE_ENV = "YTBDLP_RUNTIME_MODE"
RUNTIME_PORT_ENV = "YTBDLP_RUNTIME_PORT"
APP_VERSION_ENV = "YTBDLP_APP_VERSION"
DEFAULT_RUNTIME_PORT = 8765
DEFAULT_IDLE_TIMEOUT_SECONDS = 15 * 60
RELEASE_LAUNCHER_EXE_NAME = "youtube-downloader.exe"
RELEASE_SERVICE_EXE_NAME = "youtube-downloader-service.exe"


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def is_frozen_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def runtime_mode() -> str:
    value = os.environ.get(RUNTIME_MODE_ENV, "").strip().lower()
    if value in {"dev", "release"}:
        return value
    return "release" if is_frozen_app() else "dev"


def runtime_port(default: int = DEFAULT_RUNTIME_PORT) -> int:
    try:
        return int(os.environ.get(RUNTIME_PORT_ENV, "").strip() or default)
    except (TypeError, ValueError):
        return int(default)


def app_version(default: str = "0.1.0") -> str:
    return os.environ.get(APP_VERSION_ENV, "").strip() or default


def runtime_root() -> Path:
    if is_frozen_app():
        return Path(sys.executable).resolve().parent
    return project_root()


def bundled_resource_root() -> Path:
    meipass = getattr(sys, "_MEIPASS", "")
    if meipass:
        return Path(meipass)
    return runtime_root()


def bundled_tools_dir() -> Path:
    return runtime_root() / "vendor" / "bin"


def app_data_root() -> Path:
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
        if local_app_data:
            return Path(local_app_data) / APP_DIR_NAME
        return Path.home() / "AppData" / "Local" / APP_DIR_NAME

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR_NAME

    xdg_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
    if xdg_data_home:
        return Path(xdg_data_home) / APP_DIR_NAME.lower().replace(" ", "-")
    return Path.home() / ".local" / "share" / APP_DIR_NAME.lower().replace(" ", "-")


def logs_dir() -> Path:
    return app_data_root() / "logs"


def runtime_state_dir() -> Path:
    return app_data_root() / "runtime"


def runtime_metadata_path() -> Path:
    return runtime_state_dir() / "runtime.json"


def default_workdir() -> Path:
    return app_data_root() / "workspace"


def user_downloads_root() -> Path:
    if os.name == "nt":
        user_profile = os.environ.get("USERPROFILE", "").strip()
        if user_profile:
            return Path(user_profile) / "Downloads"
    return Path.home() / "Downloads"


def default_download_dir(workdir: str | Path | None = None) -> Path:
    del workdir
    return user_downloads_root() / PRODUCT_NAME


def bundled_tool_path(tool_name: str) -> Path | None:
    text = (tool_name or "").strip()
    if not text:
        return None

    candidates = [text]
    path = Path(text)
    if os.name == "nt" and not path.suffix:
        candidates.insert(0, f"{text}.exe")

    for candidate in candidates:
        bundled = bundled_tools_dir() / candidate
        if bundled.exists():
            return bundled
    return None


def web_service_log_path() -> Path:
    return logs_dir() / "web-service.log"
