"""
SmartTrip AI — Retrieval Engine Package (SCIF Phase 5).

Public surface:
    RetrievalEngine   — the single entry point every SCIF engine must use.
    RetrievalRequest  — typed input model.
    StructuredContext — typed output passed to Gemini.

No other module in the project should import from app.integrations.faiss_vector_store
or call app.integrations.embeddings.embed_text directly after this package
is wired.  All vector-search concerns are encapsulated here.
"""

from app.engines.retrieval_engine import RetrievalEngine
from app.engines.retrieval_models import (
    IndexType,
    QueryIntent,
    RetrievalRequest,
    RetrievalResult,
    RetrievedDocument,
    StructuredContext,
)

__all__ = [
    "RetrievalEngine",
    "IndexType",
    "QueryIntent",
    "RetrievalRequest",
    "RetrievalResult",
    "RetrievedDocument",
    "StructuredContext",
]
