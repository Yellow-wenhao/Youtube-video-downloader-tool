from __future__ import annotations

import importlib.util
from dataclasses import dataclass

from app.core.environment_service import resolve_runtime_binary


@dataclass(frozen=True)
class DependencyCheckResult:
    display_name: str
    target: str
    kind: str
    found: bool
    detail: str = ""


def inspect_startup_dependencies() -> list[DependencyCheckResult]:
    checks: list[DependencyCheckResult] = []
    module_targets = (
        ("langgraph", "langgraph"),
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("yt-dlp", "yt_dlp"),
    )
    for display_name, module_name in module_targets:
        spec = importlib.util.find_spec(module_name)
        checks.append(
            DependencyCheckResult(
                display_name=display_name,
                target=module_name,
                kind="python-module",
                found=spec is not None,
                detail="importable" if spec is not None else "missing module",
            )
        )

    yt_dlp_binary = resolve_runtime_binary("yt-dlp", fallback_names=("yt-dlp", "yt-dlp.exe"), prefer_bundled=False)
    checks.append(
        DependencyCheckResult(
            display_name="yt-dlp binary",
            target=yt_dlp_binary.requested or "yt-dlp",
            kind="runtime-binary",
            found=yt_dlp_binary.found,
            detail=yt_dlp_binary.resolved_path if yt_dlp_binary.found else "binary not found on PATH",
        )
    )
    return checks


def format_startup_dependency_report() -> tuple[bool, list[str]]:
    checks = inspect_startup_dependencies()
    ready = all(check.found for check in checks)
    lines = ["Environment self-check:"]
    for check in checks:
        status = "OK" if check.found else "MISSING"
        suffix = f" ({check.detail})" if check.detail else ""
        lines.append(f"[{status}] {check.display_name}{suffix}")
    return ready, lines


def print_startup_dependency_report() -> int:
    ready, lines = format_startup_dependency_report()
    for line in lines:
        print(line)
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(print_startup_dependency_report())
