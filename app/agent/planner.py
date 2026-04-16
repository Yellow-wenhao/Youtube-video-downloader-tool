from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.core.models import TaskStep


@dataclass
class PlanDraft:
    title: str
    intent: str
    params: dict[str, Any] = field(default_factory=dict)
    steps: list[TaskStep] = field(default_factory=list)
    planner_name: str = ""
    planner_notes: list[str] = field(default_factory=list)


class PlannerError(RuntimeError):
    """Base error for planner failures."""


def planner_error_view(code: str) -> dict[str, Any]:
    mapping = {
        "planner_config_error": {
            "error_category": "config",
            "user_title": "Agent 配置不完整",
            "user_message": "当前无法连接到规划模型。",
            "user_recovery": "请先检查 Provider、Base URL、Model 和 API Key 是否已填写完整。",
            "user_actions": ["检查 Provider", "检查 Base URL", "检查模型名", "检查 API Key"],
        },
        "planner_connection_error": {
            "error_category": "connection",
            "user_title": "Agent 连接失败",
            "user_message": "当前无法连接到所选 LLM Provider。",
            "user_recovery": "请先测试连接，并检查网络、Base URL、代理或 API Key 是否有效。",
            "user_actions": ["测试连接", "检查网络", "检查 Base URL", "检查 API Key"],
        },
        "planner_response_error": {
            "error_category": "response_structure",
            "user_title": "模型返回内容无法解析",
            "user_message": "模型已返回内容，但当前结果不是稳定可执行的 JSON 计划。",
            "user_recovery": "可以重试一次；如果持续出现，请更换模型，或降低请求复杂度后再试。",
            "user_actions": ["重试", "更换模型", "简化请求"],
        },
        "planner_schema_error": {
            "error_category": "response_structure",
            "user_title": "模型返回计划结构不完整",
            "user_message": "模型已返回 JSON，但缺少安全执行所需的关键字段。",
            "user_recovery": "建议重试；如果持续出现，请更换模型，或把需求拆得更明确一些。",
            "user_actions": ["重试", "更换模型", "把请求写得更明确"],
        },
        "planner_unknown_error": {
            "error_category": "unknown",
            "user_title": "Agent 计划生成失败",
            "user_message": "规划阶段发生了未分类错误，当前无法继续执行。",
            "user_recovery": "请先重试；如果持续失败，请检查当前配置或改用其他模型。",
            "user_actions": ["重试", "检查配置", "更换模型"],
        },
    }
    return dict(mapping.get(code, mapping["planner_unknown_error"]))


class PlannerRuntimeError(PlannerError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        phase: str = "planning",
        user_message: str | None = None,
        user_title: str | None = None,
        user_recovery: str | None = None,
        user_actions: list[str] | None = None,
        error_category: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        mapped = planner_error_view(code)
        self.code = code
        self.phase = phase
        self.error_category = error_category or str(mapped.get("error_category") or "unknown")
        self.user_title = user_title or str(mapped.get("user_title") or "Agent 执行失败")
        self.user_message = user_message or str(mapped.get("user_message") or message)
        self.user_recovery = user_recovery or str(mapped.get("user_recovery") or "")
        self.user_actions = list(user_actions or mapped.get("user_actions") or [])
        self.details = details or {}

    def to_payload(self) -> dict[str, Any]:
        return {
            "kind": "planner_error",
            "code": self.code,
            "phase": self.phase,
            "message": str(self),
            "error_category": self.error_category,
            "user_title": self.user_title,
            "user_message": self.user_message,
            "user_recovery": self.user_recovery,
            "user_actions": self.user_actions,
            "details": self.details,
        }


class PlannerConfigurationError(PlannerRuntimeError):
    """Raised when the selected planner is unavailable or misconfigured."""

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code="planner_config_error",
            phase="planning",
            details=details,
        )


class PlannerConnectionError(PlannerRuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code="planner_connection_error",
            phase="planning",
            details=details,
        )


class PlannerResponseError(PlannerRuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code="planner_response_error",
            phase="planning",
            details=details,
        )


class PlannerSchemaError(PlannerRuntimeError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            code="planner_schema_error",
            phase="planning",
            details=details,
        )


@runtime_checkable
class AgentPlanner(Protocol):
    planner_name: str

    def build_plan(
        self,
        user_request: str,
        workdir: str | Path,
        defaults: dict[str, Any] | None = None,
    ) -> PlanDraft:
        ...


class FallbackPlanner(AgentPlanner):
    planner_name = "llm_with_legacy_fallback"

    def __init__(self, primary: AgentPlanner, fallback: AgentPlanner) -> None:
        self.primary = primary
        self.fallback = fallback

    def build_plan(
        self,
        user_request: str,
        workdir: str | Path,
        defaults: dict[str, Any] | None = None,
    ) -> PlanDraft:
        try:
            draft = self.primary.build_plan(user_request, workdir, defaults)
            if not draft.planner_name:
                draft.planner_name = getattr(self.primary, "planner_name", "llm")
            return draft
        except Exception as exc:
            reason = self._fallback_reason(exc)
            draft = self.fallback.build_plan(user_request, workdir, defaults)
            draft.planner_name = getattr(self.fallback, "planner_name", "legacy_rule_based")
            notes = list(draft.planner_notes or [])
            notes.append(reason)
            draft.planner_notes = notes
            return draft

    def _fallback_reason(self, exc: Exception) -> str:
        if isinstance(exc, PlannerRuntimeError):
            return (
                "LLM planner failed with "
                f"{exc.code}; legacy fallback was used only because "
                "YTBDLP_AGENT_PLANNER=llm_with_legacy_fallback was explicitly enabled."
            )
        return (
            "LLM planner raised an unexpected error; legacy fallback was used only because "
            "YTBDLP_AGENT_PLANNER=llm_with_legacy_fallback was explicitly enabled."
        )


LEGACY_PLANNER_MODES = {"legacy", "legacy_rule_based", "rule_based", "regex"}
EXPLICIT_FALLBACK_PLANNER_MODES = {"llm_with_legacy_fallback", "llm_then_legacy"}


def build_planner_from_mode(planner_mode: str) -> AgentPlanner:
    normalized = planner_mode.strip().lower() or "llm"

    if normalized == "llm":
        from app.agent.llm_planner import LLMPlanner

        return LLMPlanner()

    if normalized in LEGACY_PLANNER_MODES:
        from app.agent.legacy_rule_planner import LegacyRuleBasedPlanner

        return LegacyRuleBasedPlanner()

    if normalized in EXPLICIT_FALLBACK_PLANNER_MODES:
        from app.agent.legacy_rule_planner import LegacyRuleBasedPlanner
        from app.agent.llm_planner import LLMPlanner

        return FallbackPlanner(LLMPlanner(), LegacyRuleBasedPlanner())

    raise PlannerConfigurationError(
        "Unsupported planner mode: "
        f"{planner_mode}. Use YTBDLP_AGENT_PLANNER=llm, "
        "YTBDLP_AGENT_PLANNER=legacy_rule_based, or "
        "YTBDLP_AGENT_PLANNER=llm_with_legacy_fallback."
    )


def create_default_planner() -> AgentPlanner:
    planner_mode = os.environ.get("YTBDLP_AGENT_PLANNER", "llm").strip().lower() or "llm"
    return build_planner_from_mode(planner_mode)
