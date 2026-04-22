from __future__ import annotations

import argparse
import copy
import os
import sys
from pathlib import Path

import uvicorn
from uvicorn.config import LOGGING_CONFIG

from app.core.app_paths import (
    APP_VERSION_ENV,
    RUNTIME_MODE_ENV,
    RUNTIME_PORT_ENV,
    app_version,
    web_service_log_path,
)


def _configure_release_stdio(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stream = log_path.open("a", encoding="utf-8", buffering=1)
    sys.stdout = stream
    sys.stderr = stream


def _file_handler_config(*, formatter: str, log_path: Path) -> dict:
    return {
        "class": "logging.FileHandler",
        "formatter": formatter,
        "filename": str(log_path),
        "encoding": "utf-8",
    }


def _release_log_config(log_path: Path) -> dict:
    config = copy.deepcopy(LOGGING_CONFIG)
    config["handlers"]["default"] = _file_handler_config(formatter="default", log_path=log_path)
    config["handlers"]["access"] = _file_handler_config(formatter="access", log_path=log_path)
    return config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Background web service entrypoint for YouTube Downloader")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--version", default=app_version())
    args = parser.parse_args(argv)

    os.environ[RUNTIME_MODE_ENV] = "release"
    os.environ[RUNTIME_PORT_ENV] = str(args.port)
    os.environ[APP_VERSION_ENV] = args.version

    log_path = web_service_log_path()
    _configure_release_stdio(log_path)

    config = uvicorn.Config(
        "app.web.main:app",
        host=args.host,
        port=args.port,
        reload=False,
        log_config=_release_log_config(log_path),
    )
    server = uvicorn.Server(config)
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
