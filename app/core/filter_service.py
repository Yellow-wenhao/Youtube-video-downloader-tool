from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

WEAK_QUERY_TERMS = {
    "review",
    "reviews",
    "walkaround",
    "walk",
    "around",
    "test",
    "drive",
    "driving",
    "interior",
    "exterior",
    "footage",
    "video",
    "videos",
    "comparison",
    "compare",
    "vs",
    "first",
    "look",
    "launch",
    "体验",
    "测评",
    "评测",
    "实拍",
    "对比",
    "视频",
    "教程",
    "教学",
    "讲解",
    "纪录片",
    "访谈",
    "开箱",
}


CONTENT_HINT_PATTERNS = [
    r"\breview\b",
    r"\btutorial\b",
    r"\bhow\s*to\b",
    r"\bexplained\b",
    r"\bdocumentary\b",
    r"\binterview\b",
    r"\bunboxing\b",
    r"\bcomparison\b",
    r"\bguide\b",
    r"教程",
    r"教学",
    r"讲解",
    r"纪录片",
    r"访谈",
    r"开箱",
    r"对比",
]


def _compile_patterns(patterns: Sequence[str]) -> List[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


CONTENT_HINT_RE = _compile_patterns(CONTENT_HINT_PATTERNS)


@dataclass
class ScoreResult:
    selected: bool
    manual_review: bool
    score: int
    reasons: List[str]
    positive_hits: str = ""
    negative_hits: str = ""
    content_hits: str = ""


@dataclass
class ScoringConfig:
    topic_phrase: str
    topic_aliases: List[str]
    min_duration: int
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    lang_rules: str = "both"


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return " ".join(normalize_text(v) for v in value)
    return str(value).strip()


def parse_upload_year(upload_date: Any) -> Optional[int]:
    s = normalize_text(upload_date)
    if len(s) >= 4 and s[:4].isdigit():
        y = int(s[:4])
        if 1990 <= y <= 2100:
            return y
    return None


def topic_match_flags(text: str, phrase: str) -> Tuple[bool, bool, bool]:
    p = phrase.strip().lower()
    tokens = core_match_tokens(p)
    if not tokens:
        return False, False, False
    exact = p in text
    matched = matched_tokens(text, tokens)
    loose = len(matched) >= required_match_count(tokens)
    any_tok = bool(matched)
    return exact, loose, any_tok


def split_match_tokens(value: str) -> List[str]:
    return re.findall(r"[0-9a-z]+|[\u4e00-\u9fff]+", (value or "").lower())


def core_match_tokens(value: str) -> List[str]:
    raw_tokens = split_match_tokens(value)
    if not raw_tokens:
        return []
    core = [tok for tok in raw_tokens if tok not in WEAK_QUERY_TERMS]
    if core:
        return core
    return raw_tokens


def matched_tokens(text: str, tokens: Sequence[str]) -> List[str]:
    base = (text or "").lower()
    hits: List[str] = []
    for tok in tokens:
        if tok and tok in base and tok not in hits:
            hits.append(tok)
    return hits


def required_match_count(tokens: Sequence[str]) -> int:
    size = len(tokens)
    if size <= 1:
        return 1
    if size <= 3:
        return 2
    return 3


def query_match_in_title_desc(text_td: str, query_hits: Sequence[str]) -> Tuple[bool, List[str], List[str]]:
    matched: List[str] = []
    matched_core_tokens: List[str] = []
    base = (text_td or "").strip().lower()
    if not base:
        return False, matched, matched_core_tokens
    for raw in query_hits or []:
        q = normalize_text(raw).lower()
        if not q:
            continue
        if q in base:
            matched.append(raw)
            for token in core_match_tokens(q):
                if token in base and token not in matched_core_tokens:
                    matched_core_tokens.append(token)
            continue
        tokens = core_match_tokens(q)
        hits = matched_tokens(base, tokens)
        if tokens and len(hits) >= required_match_count(tokens):
            matched.append(raw)
            for token in hits:
                if token not in matched_core_tokens:
                    matched_core_tokens.append(token)
    uniq: List[str] = []
    seen: set[str] = set()
    for m in matched:
        if m in seen:
            continue
        seen.add(m)
        uniq.append(m)
    return bool(uniq), uniq, matched_core_tokens


def hits_join(hits: List[str], max_len: int = 500) -> str:
    s = "; ".join(hits[:40])
    return s if len(s) <= max_len else s[: max_len - 3] + "..."


def contains_any(text: str, patterns: Sequence[re.Pattern[str]]) -> Tuple[bool, List[str]]:
    hits: List[str] = []
    for pat in patterns:
        if pat.search(text):
            hits.append(pat.pattern)
    return bool(hits), hits


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def score_candidate(item: Dict[str, Any], cfg: ScoringConfig) -> ScoreResult:
    phrase = (cfg.topic_phrase or "").strip()

    if item.get("detail_error"):
        return ScoreResult(
            selected=False,
            manual_review=False,
            score=-99,
            reasons=[f"详细元数据提取失败: {normalize_text(item.get('detail_error'))}"],
        )

    title = normalize_text(item.get("title"))
    description = normalize_text(item.get("description"))
    tags = normalize_text(item.get("tags"))
    text_td = " ".join([title, description]).lower()
    text = " ".join([title, description, tags]).lower()

    reasons: List[str] = []
    has_vector_score = "vector_score" in item
    vector_score = safe_float(item.get("vector_score"), 0.0)
    vector_threshold = safe_float(item.get("vector_threshold"), 0.08)
    semantic_ok = has_vector_score and vector_score >= vector_threshold
    if has_vector_score:
        vector_rank = item.get("vector_rank")
        rank_text = f"，TopK 排名 {vector_rank}" if vector_rank not in (None, "") else ""
        if semantic_ok:
            reasons.append(f"语义相似度: 通过（{vector_score:.3f} >= {vector_threshold:.3f}{rank_text}）")
        else:
            reasons.append(f"语义相似度: 偏低（{vector_score:.3f} < {vector_threshold:.3f}{rank_text}）")

    query_hits = item.get("query_hits") or []
    if not isinstance(query_hits, list):
        query_hits = [normalize_text(query_hits)]
    query_ok, matched_queries, matched_query_tokens = query_match_in_title_desc(text_td, query_hits)
    query_token_hit_count = len(matched_query_tokens)
    if query_ok:
        reasons.append(f"关键词核心匹配: 通过（命中 {query_token_hit_count} 个核心词）")
    else:
        reasons.append("关键词核心匹配: 不通过（标题/描述未命中核心词）")

    topic_ok = True
    topic_aliases = [phrase] + [normalize_text(alias) for alias in (cfg.topic_aliases or []) if normalize_text(alias)]
    topic_aliases = [alias for alias in topic_aliases if alias]
    if topic_aliases:
        alias_matches: List[str] = []
        for alias in topic_aliases:
            exact, loose, any_tok = topic_match_flags(text, alias)
            if exact or loose:
                alias_matches.append(alias)
        topic_ok = bool(alias_matches)
        if topic_ok:
            reasons.append(f"主题核心词检查: 通过（命中 {normalize_text(alias_matches[0])}）")
        else:
            reasons.append("主题核心词检查: 未命中")
    else:
        reasons.append("主题核心词检查: 未设置，跳过")

    has_content_hint, content_hits = contains_any(text, CONTENT_HINT_RE)
    if has_content_hint:
        reasons.append(f"命中内容类型线索 {len(content_hits)} 个")

    upload_year = parse_upload_year(item.get("upload_date"))
    year_ok = True
    year_unknown = False
    if cfg.year_from is not None or cfg.year_to is not None:
        if upload_year is None:
            year_unknown = True
            reasons.append("已设年份区间但无上传日期，降权保留")
        else:
            if cfg.year_from is not None and upload_year < cfg.year_from:
                year_ok = False
                reasons.append(f"上传年 {upload_year} < {cfg.year_from}")
            if cfg.year_to is not None and upload_year > cfg.year_to:
                year_ok = False
                reasons.append(f"上传年 {upload_year} > {cfg.year_to}")

    duration = item.get("duration")
    duration_ok = True
    if isinstance(duration, (int, float)):
        reasons.append(f"时长: {int(duration)}s")
        if duration < cfg.min_duration:
            duration_ok = False
            reasons.append(f"时长不足: {int(duration)}s < {cfg.min_duration}s")
    else:
        reasons.append("缺少时长信息")

    live_status = normalize_text(item.get("live_status")).lower()
    if item.get("is_live") or item.get("was_live") or live_status in {"is_live", "was_live", "post_live", "is_upcoming"}:
        reasons.append("直播/直播回放/待开始")

    availability = normalize_text(item.get("availability")).lower()
    if availability in {"private", "premium_only", "subscriber_only", "needs_auth"}:
        reasons.append(f"可用性受限: {availability}")

    restricted = availability in {"private", "premium_only", "subscriber_only", "needs_auth"}
    live_blocked = bool(item.get("is_live") or item.get("was_live"))

    score = 0
    if has_vector_score:
        score += int(round(vector_score * 100))
        if semantic_ok:
            score += 5
        else:
            score -= 4
    if query_ok:
        score += 2 if has_vector_score else 4
    if topic_ok:
        score += 2 if has_vector_score else 4
    if has_content_hint:
        score += 1
    if duration is None or duration_ok:
        score += 1
    if year_ok and not year_unknown:
        score += 1
    if item.get("best_rank") is not None:
        try:
            rank = int(item.get("best_rank") or 999999)
            if rank <= 5:
                score += 2
            elif rank <= 20:
                score += 1
        except Exception:
            pass
    if not query_ok:
        score -= 1
    if not topic_ok:
        score -= 1
    if year_unknown:
        score -= 1
    if not year_ok:
        score -= 4
    if not duration_ok:
        score -= 3
    if restricted or live_blocked:
        score -= 99

    hard_blocked = restricted or live_blocked or not year_ok or not duration_ok
    lexical_strong = bool(query_ok and topic_ok)
    lexical_very_strong = bool((query_ok and topic_ok and query_token_hit_count >= 1) or query_token_hit_count >= 2)
    if has_vector_score:
        selected = not hard_blocked and (
            (semantic_ok and (score >= 8))
            or (lexical_very_strong and (score >= 8))
            or (lexical_strong and has_content_hint and (score >= 7))
        )
    else:
        selected = (score >= 3) and not hard_blocked
    if selected:
        if has_vector_score and not semantic_ok and lexical_very_strong:
            reasons.append(f"词面强匹配兜底入选: {score}")
        else:
            reasons.append(f"语义优先评分入选: {score}" if has_vector_score else f"软评分入选: {score}")
    else:
        reasons.append(f"语义优先评分未入选: {score}" if has_vector_score else f"软评分未入选: {score}")

    return ScoreResult(
        selected=selected,
        manual_review=False,
        score=score,
        reasons=reasons,
        positive_hits=hits_join(matched_query_tokens),
        negative_hits="",
        content_hits=hits_join(content_hits),
    )


def filter_candidates(items: Sequence[Dict[str, Any]], cfg: ScoringConfig) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    for item in items:
        scored = score_candidate(item, cfg)
        enriched = dict(item)
        enriched["selected"] = scored.selected
        enriched["manual_review"] = scored.manual_review
        enriched["score"] = scored.score
        enriched["reasons"] = " | ".join(scored.reasons)
        enriched["positive_hits"] = scored.positive_hits
        enriched["negative_hits"] = scored.negative_hits
        enriched["content_hits"] = scored.content_hits
        enriched["topic_phrase"] = cfg.topic_phrase.strip()
        enriched["upload_year"] = parse_upload_year(item.get("upload_date"))
        tags_list = item.get("tags") or []
        if isinstance(tags_list, list):
            enriched["tags_preview"] = "; ".join(str(t) for t in tags_list)[:500]
        else:
            enriched["tags_preview"] = normalize_text(tags_list)[:500]
        enriched["description_preview"] = normalize_text(item.get("description"))[:400]
        filtered.append(enriched)

    if filtered and not any(item.get("selected") for item in filtered):
        has_vector_pipeline = any("vector_score" in item for item in filtered)
        fallback_pool = [
            item
            for item in filtered
            if int(item.get("score") or -999) > -50
            and (
                not has_vector_pipeline
                or safe_float(item.get("vector_score"), 0.0) >= safe_float(item.get("vector_threshold"), 0.08) * 0.35
                or "关键词核心匹配: 通过" in str(item.get("reasons") or "")
                or "主题核心词检查: 通过" in str(item.get("reasons") or "")
            )
            and "可用性受限" not in str(item.get("reasons") or "")
            and "直播/直播回放/待开始" not in str(item.get("reasons") or "")
            and "上传年 " not in str(item.get("reasons") or "")
        ]
        fallback_pool.sort(
            key=lambda x: (
                safe_float(x.get("vector_score"), 0.0),
                int(x.get("score") or -999),
                -int(x.get("best_rank") or 999999),
            ),
            reverse=True,
        )
        for item in fallback_pool[: min(10, len(fallback_pool))]:
            item["selected"] = True
            item["manual_review"] = True
            item["score"] = max(int(item.get("score") or 0), 1)
            reason = str(item.get("reasons") or "")
            item["reasons"] = f"{reason} | YouTube召回兜底入选（建议人工复核）"

    filtered.sort(
        key=lambda x: (
            bool(x.get("selected")),
            safe_float(x.get("vector_score"), 0.0),
            int(x.get("score") or -999),
            -int(x.get("best_rank") or 999999),
        ),
        reverse=True,
    )
    return filtered
