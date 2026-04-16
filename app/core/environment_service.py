from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from app.core.app_paths import bundled_tool_path, runtime_mode


@dataclass(frozen=True)
class ResolvedRuntimeBinary:
    requested: str
    resolved_path: str = ""
    found: bool = False
    source: str = "missing"


@dataclass(frozen=True)
class RuntimeEnvironmentStatus:
    yt_dlp_binary: str
    ffmpeg_binary: str
    yt_dlp_found: bool
    ffmpeg_found: bool
    yt_dlp_resolved_path: str = ""
    ffmpeg_resolved_path: str = ""
    yt_dlp_source: str = "missing"
    ffmpeg_source: str = "missing"


def _is_explicit_path(value: str) -> bool:
    return any(token in value for token in ("\\", "/", ":"))


def resolve_runtime_binary(
    binary: str,
    *,
    fallback_names: tuple[str, ...] = (),
    prefer_bundled: bool | None = None,
) -> ResolvedRuntimeBinary:
    requested = (binary or "").strip()
    if not requested:
        requested = fallback_names[0] if fallback_names else ""

    if prefer_bundled is None:
        prefer_bundled = runtime_mode() == "release"

    if requested and _is_explicit_path(requested):
        candidate = Path(requested).expanduser()
        if candidate.exists():
            return ResolvedRuntimeBinary(
                requested=requested,
                resolved_path=str(candidate.resolve()),
                found=True,
                source="explicit",
            )
        return ResolvedRuntimeBinary(requested=requested)

    names = []
    for name in (requested, *fallback_names):
        text = (name or "").strip()
        if text and text not in names:
            names.append(text)

    if prefer_bundled:
        for name in names:
            candidate = bundled_tool_path(name)
            if candidate is not None:
                return ResolvedRuntimeBinary(
                    requested=requested or name,
                    resolved_path=str(candidate.resolve()),
                    found=True,
                    source="bundled",
                )

    for name in names:
        resolved = shutil.which(name) or ""
        if resolved:
            return ResolvedRuntimeBinary(
                requested=requested or name,
                resolved_path=resolved,
                found=True,
                source="path",
            )

    return ResolvedRuntimeBinary(requested=requested or (names[0] if names else ""))


def inspect_runtime_environment(
    yt_dlp_binary: str = "yt-dlp",
    ffmpeg_binary: str = "ffmpeg",
) -> RuntimeEnvironmentStatus:
    yt_dlp = resolve_runtime_binary(
        yt_dlp_binary,
        fallback_names=("yt-dlp", "yt-dlp.exe"),
    )
    ffmpeg = resolve_runtime_binary(
        ffmpeg_binary,
        fallback_names=("ffmpeg", "ffmpeg.exe"),
    )
    return RuntimeEnvironmentStatus(
        yt_dlp_binary=yt_dlp.requested or yt_dlp_binary,
        ffmpeg_binary=ffmpeg.requested or ffmpeg_binary,
        yt_dlp_found=yt_dlp.found,
        ffmpeg_found=ffmpeg.found,
        yt_dlp_resolved_path=yt_dlp.resolved_path,
        ffmpeg_resolved_path=ffmpeg.resolved_path,
        yt_dlp_source=yt_dlp.source,
        ffmpeg_source=ffmpeg.source,
    )


def ffmpeg_location(binary: str = "ffmpeg") -> str:
    resolved = resolve_runtime_binary(binary, fallback_names=("ffmpeg", "ffmpeg.exe"))
    if not resolved.found or not resolved.resolved_path:
        return ""
    return str(Path(resolved.resolved_path).resolve().parent)


def release_bundle_available() -> bool:
    yt_dlp = resolve_runtime_binary("yt-dlp", fallback_names=("yt-dlp", "yt-dlp.exe"), prefer_bundled=True)
    ffmpeg = resolve_runtime_binary("ffmpeg", fallback_names=("ffmpeg", "ffmpeg.exe"), prefer_bundled=True)
    return yt_dlp.source == "bundled" and ffmpeg.source == "bundled"
