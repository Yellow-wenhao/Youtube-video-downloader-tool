from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.core.vector_search_service import HashingTextEmbedder, VectorSearchService
from app.tools.search_tools import _load_jsonl, _write_jsonl
from app.tools.schemas import BuildVectorIndexInput, BuildVectorIndexOutput, KnnSearchInput, KnnSearchOutput


def build_vector_index(input_data: BuildVectorIndexInput) -> BuildVectorIndexOutput:
    items = _load_jsonl(Path(input_data.items_path))
    index_path = input_data.index_path or str(Path(input_data.items_path).with_name("09_vector_index.json"))
    service = VectorSearchService(HashingTextEmbedder(dimensions=input_data.dimensions))
    result = service.build_index(items, index_path)
    return BuildVectorIndexOutput(
        index_path=result["index_path"],
        record_count=int(result["record_count"]),
        backend=str(result["backend"]),
    )


def knn_search(input_data: KnnSearchInput) -> KnnSearchOutput:
    service = VectorSearchService(HashingTextEmbedder(dimensions=input_data.dimensions))
    threshold = float(input_data.score_threshold if input_data.score_threshold is not None else 0.12)
    results = service.search(
        input_data.query,
        input_data.index_path,
        top_k=max(1, int(input_data.top_k or 20)),
        metric=input_data.metric or "cosine",
    )
    result_dicts = [asdict(result) for result in results]
    scored_items_path = ""
    low_similarity_count = 0

    if input_data.items_path:
        items_path = Path(input_data.items_path)
        output_path = Path(input_data.output_path) if input_data.output_path else items_path.with_name("02b_vector_scored_candidates.jsonl")
        score_by_video_id = {str(result.video_id): result for result in results}
        enriched: list[dict[str, Any]] = []
        for item in _load_jsonl(items_path):
            video_id = str(item.get("video_id") or item.get("id") or "").strip()
            match = score_by_video_id.get(video_id)
            vector_score = float(match.score) if match else 0.0
            if vector_score < threshold:
                low_similarity_count += 1
            next_item = dict(item)
            next_item["vector_score"] = round(vector_score, 6)
            next_item["vector_rank"] = int(match.rank) if match else None
            next_item["vector_metric"] = input_data.metric or "cosine"
            next_item["vector_threshold"] = threshold
            if match is None:
                next_item["vector_reason"] = "未进入语义 TopK，按低相似度处理"
            elif vector_score >= threshold:
                next_item["vector_reason"] = f"语义相似度通过: {vector_score:.3f}"
            else:
                next_item["vector_reason"] = f"语义相似度偏低: {vector_score:.3f} < {threshold:.3f}"
            enriched.append(next_item)
        _write_jsonl(output_path, enriched)
        scored_items_path = str(output_path)

    scores = [float(result.score) for result in results]
    return KnnSearchOutput(
        results=result_dicts,
        metric=input_data.metric or "cosine",
        top_k=max(1, int(input_data.top_k or 20)),
        scored_items_path=scored_items_path,
        max_score=max(scores) if scores else 0.0,
        average_top_score=(sum(scores) / len(scores)) if scores else 0.0,
        low_similarity_count=low_similarity_count,
        score_threshold=threshold,
    )
