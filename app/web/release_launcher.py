from __future__ import annotations

import argparse
import ctypes
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from app.core.app_paths import (
    APP_VERSION_ENV,
    DEFAULT_RUNTIME_PORT,
    PRODUCT_NAME,
    RELEASE_SERVICE_EXE_NAME,
    RUNTIME_MODE_ENV,
    RUNTIME_PORT_ENV,
    is_frozen_app,
    project_root,
    runtime_metadata_path,
    runtime_root,
)


def _show_message(title: str, message: str) -> None:
    if os.name == "nt":
        try:
            ctypes.windll.user32.MessageBoxW(None, message, title, 0x00000040)
            return
        except Exception:
            pass
    print(f"{title}\n{message}")


def _load_runtime_metadata() -> dict[str, object]:
    path = runtime_metadata_path()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _runtime_url(port: int) -> str:
    return f"http://127.0.0.1:{int(port)}"


def _healthcheck(url: str, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=timeout) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


def _is_existing_runtime_alive() -> tuple[bool, str]:
    metadata = _load_runtime_metadata()
    port = int(metadata.get("port") or 0)
    if port <= 0:
        return False, ""
    url = _runtime_url(port)
    return _healthcheck(url), url


def _choose_port(preferred: int = DEFAULT_RUNTIME_PORT) -> int:
    for candidate in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", candidate))
            port = sock.getsockname()[1]
        if port:
            return int(port)
    return int(preferred)


def _service_command(port: int, version: str) -> list[str]:
    if is_frozen_app():
        service_exe = runtime_root() / RELEASE_SERVICE_EXE_NAME
        return [str(service_exe), "--host", "127.0.0.1", "--port", str(port), "--version", version]
    return [sys.executable, "-m", "app.web.service_entry", "--host", "127.0.0.1", "--port", str(port), "--version", version]


def _launch_service(command: list[str], *, version: str, port: int) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env[RUNTIME_MODE_ENV] = "release"
    env[RUNTIME_PORT_ENV] = str(port)
    env[APP_VERSION_ENV] = version

    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    return subprocess.Popen(
        command,
        cwd=str(project_root() if not is_frozen_app() else runtime_root()),
        env=env,
        startupinfo=startupinfo,
        creationflags=creationflags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def _wait_for_runtime(url: str, timeout_seconds: float = 20.0) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _healthcheck(url, timeout=1.2):
            return True
        time.sleep(0.35)
    return False


def _open_browser(url: str) -> bool:
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch the local YouTube Downloader web workspace")
    parser.add_argument("--version", default=os.environ.get(APP_VERSION_ENV, "0.1.0"))
    args = parser.parse_args(argv)

    alive, existing_url = _is_existing_runtime_alive()
    if alive and existing_url:
        if not _open_browser(existing_url):
            _show_message(PRODUCT_NAME, f"本地服务已经在运行，但浏览器没有自动打开。\n\n请手动访问：\n{existing_url}")
        return 0

    port = _choose_port()
    url = _runtime_url(port)
    command = _service_command(port, args.version)
    service_path = Path(command[0])
    if is_frozen_app() and not service_path.exists():
        _show_message(PRODUCT_NAME, f"未找到后台服务程序：\n{service_path}\n\n请重新下载完整的发布包后再试。")
        return 1

    try:
        _launch_service(command, version=args.version, port=port)
    except Exception as exc:
        _show_message(PRODUCT_NAME, f"后台服务启动失败：\n{exc}")
        return 1

    if not _wait_for_runtime(url):
        _show_message(PRODUCT_NAME, f"后台服务未能在预期时间内启动。\n\n你可以稍后手动访问：\n{url}")
        return 1

    if not _open_browser(url):
        _show_message(PRODUCT_NAME, f"后台服务已经启动，但浏览器没有自动打开。\n\n请手动访问：\n{url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
