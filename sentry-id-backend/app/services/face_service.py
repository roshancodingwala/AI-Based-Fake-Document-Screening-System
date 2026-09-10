"""
Face verification (document photo vs. live capture).

To wire in real InsightFace/ArcFace:
    1. `pip install insightface onnxruntime`
    2. In a `InsightFaceService(FaceService)`, load `insightface.app.FaceAnalysis`,
       run `.get(image)` on both images to get 512-d embeddings, and compare
       with cosine similarity.
    3. Return the same `FaceVerifyResponse` shape so nothing downstream changes.

The demo implementation below hashes both images into a stable
pseudo-embedding so the same pair of test images always produces the same
similarity score, which is important for a reproducible demo.
"""
import hashlib
from abc import ABC, abstractmethod

from app.schemas.face import FaceVerifyResponse

MATCH_THRESHOLD = 0.72


def _pseudo_embedding(image_bytes: bytes, dim: int = 32) -> list[float]:
    digest = hashlib.sha256(image_bytes).digest()
    # Repeat/trim the digest bytes into `dim` floats in [-1, 1]
    values = [(digest[i % len(digest)] / 127.5) - 1 for i in range(dim)]
    return values


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class FaceService(ABC):
    @abstractmethod
    async def verify(self, document_photo: bytes, live_photo: bytes) -> FaceVerifyResponse:
        ...


class DemoFaceService(FaceService):
    async def verify(self, document_photo: bytes, live_photo: bytes) -> FaceVerifyResponse:
        emb_a = _pseudo_embedding(document_photo)
        emb_b = _pseudo_embedding(live_photo)
        raw_similarity = _cosine_similarity(emb_a, emb_b)

        # Map cosine similarity (which skews high for random hash vectors)
        # into a realistic-looking 0-1 face match range for the demo.
        similarity = round(0.5 + (raw_similarity * 0.5), 3)
        similarity = max(0.0, min(similarity, 0.999))

        return FaceVerifyResponse(
            similarity_score=similarity,
            match=similarity >= MATCH_THRESHOLD,
            confidence=round(min(0.99, 0.6 + similarity * 0.4), 3),
        )


def get_face_service() -> FaceService:
    return DemoFaceService()
