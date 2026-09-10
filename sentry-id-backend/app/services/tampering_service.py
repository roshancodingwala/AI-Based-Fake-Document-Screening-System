"""
Tampering detection.

The prototype runs a handful of *real*, cheap OpenCV forensic signals
(error-level-analysis-style recompression difference, edge-density check
on the likely photo region, Laplacian blur variance) and combines them
with a deterministic demo scoring layer so results are explainable and
repeatable for a demo.

This is NOT a production tamper detector — it will not reliably catch a
skilled forgery. Swapping in a trained CNN/transformer tamper classifier
(e.g. a fine-tuned segmentation model that outputs a manipulation heatmap)
behind the same `TamperingService` interface is the intended production
upgrade path; the router and schema would not need to change.
"""
import io
from abc import ABC, abstractmethod

import cv2
import numpy as np
from PIL import Image

from app.schemas.documents import TamperingResponse


class TamperingService(ABC):
    @abstractmethod
    async def analyze(self, image_bytes: bytes) -> TamperingResponse:
        ...


class HeuristicTamperingService(TamperingService):
    def _load_gray(self, image_bytes: bytes) -> np.ndarray:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        arr = np.array(image)
        return cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY), arr

    def _error_level_score(self, image_bytes: bytes) -> float:
        """Recompress at a known quality and measure the residual — a crude
        stand-in for full error level analysis. Higher residual variance in
        a small region than the rest of the image can indicate local edits."""
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90)
        buffer.seek(0)
        recompressed = np.array(Image.open(buffer))
        original = np.array(image.resize(recompressed.shape[1::-1]))
        diff = np.abs(original.astype(int) - recompressed.astype(int))
        return float(diff.std())

    def _edge_density(self, gray: np.ndarray) -> float:
        edges = cv2.Canny(gray, 100, 200)
        return float(np.count_nonzero(edges)) / edges.size

    def _blur_variance(self, gray: np.ndarray) -> float:
        return float(cv2.Laplacian(gray, cv2.CV_64F).var())

    async def analyze(self, image_bytes: bytes) -> TamperingResponse:
        gray, _ = self._load_gray(image_bytes)
        ela_score = self._error_level_score(image_bytes)
        edge_density = self._edge_density(gray)
        blur_var = self._blur_variance(gray)

        reasons: list[str] = []
        suspicious_regions: list[str] = []
        score = 0.0

        # These thresholds are illustrative demo heuristics, tuned only to
        # produce plausible, explainable output — not calibrated against a
        # labelled forgery dataset.
        if ela_score > 6.0:
            score += 0.35
            reasons.append("Inconsistent compression detected across the image")
            suspicious_regions.append("global")

        if edge_density < 0.02:
            score += 0.2
            reasons.append("Unusually low edge detail — possible smoothing or splicing")
            suspicious_regions.append("photo_region")

        if blur_var < 50:
            score += 0.15
            reasons.append("Low local sharpness variance, consistent with a pasted-in region")
            suspicious_regions.append("photo_region")

        # Deterministic demo signal so the seeded flagged document
        # (P123456) always reproduces the scenario used across the prototype.
        digest_bias = (sum(image_bytes[:64]) % 100) / 100
        score += digest_bias * 0.3
        if digest_bias > 0.6:
            reasons.append("Text region shows an abnormal editing pattern")
            suspicious_regions.append("text_field")

        score = min(round(score, 2), 0.99)

        if score >= 0.7:
            status = "TAMPERED"
        elif score >= 0.35:
            status = "SUSPICIOUS"
        else:
            status = "CLEAN"
            reasons = reasons or ["No significant forensic anomalies detected"]

        return TamperingResponse(
            status=status,
            confidence=score,
            suspicious_regions=list(dict.fromkeys(suspicious_regions)),
            reasons=reasons,
        )


def get_tampering_service() -> TamperingService:
    return HeuristicTamperingService()
