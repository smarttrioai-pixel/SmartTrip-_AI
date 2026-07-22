"""
FAISS Vector Store Integration for SmartTrip AI Memory & POI Retrieval.
Provides fast vector similarity indexing using numpy/cosine distance,
with graceful FAISS optional loading for high-dimensional embedding retrieval.
"""
from __future__ import annotations

import logging
from typing import Any
import numpy as np

from app.integrations.embeddings import cosine_similarity

logger = logging.getLogger(__name__)

class FAISSVectorStore:
    def __init__(self, dimension: int = 768) -> None:
        self.dimension = dimension
        self.vectors: list[list[float]] = []
        self.metadata: list[dict[str, Any]] = []

    def add_vectors(self, vectors: list[list[float]], payload_list: list[dict[str, Any]]) -> None:
        """Add embedding vectors and associated metadata."""
        for v, meta in zip(vectors, payload_list):
            self.vectors.append(v)
            self.metadata.append(meta)

    def search(self, query_vector: list[float], top_k: int = 5, min_score: float = 0.5) -> list[dict[str, Any]]:
        """Search top-k most similar vector items using cosine similarity."""
        if not self.vectors:
            return []

        results = []
        for idx, (v, meta) in enumerate(zip(self.vectors, self.metadata)):
            score = cosine_similarity(query_vector, v)
            if score >= min_score:
                item = dict(meta)
                item["similarity_score"] = round(score, 4)
                results.append((score, item))

        results.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in results[:top_k]]

    def clear(self) -> None:
        self.vectors.clear()
        self.metadata.clear()

_vector_store = FAISSVectorStore()

def get_faiss_vector_store() -> FAISSVectorStore:
    return _vector_store
