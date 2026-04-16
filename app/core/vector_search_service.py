from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence


TOKEN_RE = re.compile(r"[0-9a-z]+|[\u4e00-\u9fff]+", re.IGNORECASE)

EMBEDDING_SYNONYMS = {
    "测评": "review",
    "评测": "review",
    "教程": "tutorial",
    "教学": "tutorial",
    "讲解": "explained",
    "纪录片": "documentary",
    "访谈": "interview",
    "演讲": "talk",
    "课程": "course",
    "新闻": "news",
    "实拍": "footage",
    "体验": "review",
    "对比": "comparison",
    "开箱": "unboxing",
    "音乐": "music",
    "现场": "live",
    "游戏": "gameplay",
    "旅行": "travel",
    "美食": "food",
}


@dataclass
class VideoVectorRecord:
    video_id: str
    title: str = ""
    watch_url: str = ""
    channel: str = ""
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    vector: list[float] = field(default_factory=list)


@dataclass
class VectorSearchResult:
    rank: int
    score: float
    video_id: str
    title: str
    watch_url: str
    channel: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class HashingTextEmbedder:
    """Dependency-free text embedder for local KNN.

    This is not a semantic BERT model. It is a stable hashing vectorizer that
    keeps the KNN pipeline runnable without external downloads. The interface is
    intentionally small so a BERT/sentence-transformer backend can replace it.
    """

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = max(32, int(dimensions or 384))

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = self._tokens(self._expand_synonyms(text))
        for token in tokens:
            idx = self._hash_to_index(token)
            sign = 1.0 if self._hash_to_index(f"{token}:sign", modulo=2) == 0 else -1.0
            vector[idx] += sign
        return l2_normalize(vector)

    def _tokens(self, text: str) -> list[str]:
        raw = [m.group(0).lower() for m in TOKEN_RE.finditer(text or "")]
        if not raw:
            return []
        grams = list(raw)
        for token in raw:
            if re.fullmatch(r"[\u4e00-\u9fff]+", token):
                grams.extend(token[i : i + 2] for i in range(max(0, len(token) - 1)))
                grams.extend(token[i : i + 3] for i in range(max(0, len(token) - 2)))
        grams.extend(f"{raw[i]} {raw[i + 1]}" for i in range(len(raw) - 1))
        return grams

    def _hash_to_index(self, token: str, modulo: int | None = None) -> int:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big", signed=False)
        return value % int(modulo or self.dimensions)

    def _expand_synonyms(self, text: str) -> str:
        expanded = text or ""
        additions: list[str] = []
        lowered = expanded.lower()
        for source, target in EMBEDDING_SYNONYMS.items():
            if source.lower() in lowered:
                additions.append(target)
        if additions:
            expanded = f"{expanded} {' '.join(additions)}"
        return expanded


def l2_normalize(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(float(x) * float(x) for x in vector))
    if norm <= 0:
        return [0.0 for _ in vector]
    return [float(x) / norm for x in vector]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return sum(float(x) * float(y) for x, y in zip(a, b))


def euclidean_distance(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return float("inf")
    return math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a, b)))


def video_text(item: dict[str, Any]) -> str:
    tags = item.get("tags") or item.get("tags_preview") or ""
    if isinstance(tags, list):
        tags_text = " ".join(str(tag) for tag in tags)
    else:
        tags_text = str(tags)
    return " ".join(
        part
        for part in [
            str(item.get("title") or ""),
            str(item.get("description") or item.get("description_preview") or ""),
            tags_text,
            str(item.get("channel") or ""),
        ]
        if part.strip()
    )


class JsonVectorStore:
    def __init__(self, index_path: str | Path) -> None:
        self.index_path = Path(index_path)
        self.records: list[VideoVectorRecord] = []

    def load(self) -> list[VideoVectorRecord]:
        if not self.index_path.exists():
            self.records = []
            return self.records
        payload = json.loads(self.index_path.read_text(encoding="utf-8"))
        self.records = [VideoVectorRecord(**record) for record in payload.get("records", [])]
        return self.records

    def save(self, records: Sequence[VideoVectorRecord]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "backend": "hashing",
            "records": [asdict(record) for record in records],
        }
        self.index_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.records = list(records)

    def upsert(self, records: Sequence[VideoVectorRecord]) -> None:
        existing = {record.video_id: record for record in self.load()}
        for record in records:
            existing[record.video_id] = record
        self.save(list(existing.values()))


class VectorSearchService:
    def __init__(self, embedder: HashingTextEmbedder | None = None) -> None:
        self.embedder = embedder or HashingTextEmbedder()

    def build_records(self, items: Iterable[dict[str, Any]]) -> list[VideoVectorRecord]:
        records: list[VideoVectorRecord] = []
        for item in items:
            video_id = str(item.get("video_id") or item.get("id") or "").strip()
            watch_url = str(item.get("watch_url") or item.get("webpage_url") or "").strip()
            if not video_id and watch_url:
                video_id = watch_url.rsplit("=", 1)[-1]
            if not video_id:
                continue
            text = video_text(item)
            records.append(
                VideoVectorRecord(
                    video_id=video_id,
                    title=str(item.get("title") or ""),
                    watch_url=watch_url,
                    channel=str(item.get("channel") or ""),
                    text=text,
                    metadata={
                        "duration": item.get("duration"),
                        "upload_date": item.get("upload_date"),
                        "best_rank": item.get("best_rank"),
                        "selected": item.get("selected"),
                    },
                    vector=self.embedder.embed(text),
                )
            )
        return records

    def build_index(self, items: Iterable[dict[str, Any]], index_path: str | Path) -> dict[str, Any]:
        records = self.build_records(items)
        store = JsonVectorStore(index_path)
        store.save(records)
        return {"index_path": str(Path(index_path)), "record_count": len(records), "backend": "hashing"}

    def search(
        self,
        query: str,
        index_path: str | Path,
        *,
        top_k: int = 20,
        metric: str = "cosine",
    ) -> list[VectorSearchResult]:
        store = JsonVectorStore(index_path)
        records = store.load()
        query_vector = self.embedder.embed(query)
        results: list[VectorSearchResult] = []
        for record in records:
            if metric == "euclidean":
                score = -euclidean_distance(query_vector, record.vector)
            else:
                score = cosine_similarity(query_vector, record.vector)
            results.append(
                VectorSearchResult(
                    rank=0,
                    score=score,
                    video_id=record.video_id,
                    title=record.title,
                    watch_url=record.watch_url,
                    channel=record.channel,
                    metadata=record.metadata,
                )
            )
        results.sort(key=lambda item: item.score, reverse=True)
        for idx, item in enumerate(results[:top_k], start=1):
            item.rank = idx
        return results[:top_k]
