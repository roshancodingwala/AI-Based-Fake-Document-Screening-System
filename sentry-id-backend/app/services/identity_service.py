"""
Identity shadow search: 1:N similarity search against the demo identity index.

`VectorIndex` is the swap point for FAISS/Qdrant in production — the
prototype uses a linear numpy scan, which is fine at demo scale (a handful
of identities) but would not scale to a real population register.

To wire in FAISS:
    - Build an `IndexFlatIP` (or IVF for larger scale) over normalized
      embeddings at startup, `index.add(embeddings)`, and `index.search(query, k)`.
To wire in Qdrant:
    - Use the Qdrant client to upsert embeddings with identity_id payloads,
      then `client.search(collection_name, query_vector, limit=k)`.
Either way, keep returning `IdentityMatch` objects so `IdentitySearchResponse`
and the router are unaffected.
"""
import json
from abc import ABC, abstractmethod

import numpy as np
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Identity
from app.schemas.identity import IdentityMatch, IdentitySearchResponse


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


class IdentitySearchService(ABC):
    @abstractmethod
    def search(self, db: Session, identity_id: str, top_k: int = 3) -> IdentitySearchResponse:
        ...


class DemoIdentitySearchService(IdentitySearchService):
    def search(self, db: Session, identity_id: str, top_k: int = 3) -> IdentitySearchResponse:
        settings = get_settings()

        query_identity = db.query(Identity).filter(Identity.identity_id == identity_id).first()
        if query_identity is None or not query_identity.face_embedding:
            return IdentitySearchResponse(possible_multiple_identity=False, matches=[])

        query_vec = np.array(json.loads(query_identity.face_embedding))

        candidates = (
            db.query(Identity)
            .filter(Identity.identity_id != identity_id, Identity.face_embedding.isnot(None))
            .all()
        )

        scored: list[tuple[float, Identity]] = []
        for candidate in candidates:
            vec = np.array(json.loads(candidate.face_embedding))
            if vec.shape != query_vec.shape:
                continue
            scored.append((_cosine(query_vec, vec), candidate))

        scored.sort(key=lambda pair: pair[0], reverse=True)

        matches = [
            IdentityMatch(
                identity_id=cand.identity_id,
                name=cand.name,
                similarity=round(max(sim, 0.0), 4),
                requires_officer_review=sim >= settings.identity_review_threshold,
            )
            for sim, cand in scored[:top_k]
            if sim >= settings.identity_match_threshold
        ]

        return IdentitySearchResponse(
            possible_multiple_identity=len(matches) > 0,
            matches=matches,
        )


def get_identity_search_service() -> IdentitySearchService:
    return DemoIdentitySearchService()
