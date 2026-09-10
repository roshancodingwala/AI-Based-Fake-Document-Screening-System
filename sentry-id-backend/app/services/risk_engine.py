"""
Combines every upstream signal into a single explainable 0-100 risk score.

The weighting below is a prototype heuristic, not a calibrated model. In
production this combination step is exactly where a trained model (e.g. a
gradient-boosted tree over the same feature set) would replace hand-set
weights — keeping the same `RiskFactor` breakdown for explainability is
important either way, since officers need to see *why* a score is high,
never just the number.
"""
from app.core.config import get_settings
from app.schemas.risk import RiskCalculateRequest, RiskCalculateResponse, RiskFactor

# (factor name, weight out of 100)
WEIGHTS = {
    "document_validation": 10,
    "tampering": 20,
    "face_match": 10,
    "identity_search": 20,
    "document_status": 15,
    "document_dna": 10,
    "cross_checkpoint": 5,
    "fraud_network": 10,
}


class RiskEngine:
    def calculate(self, request: RiskCalculateRequest) -> RiskCalculateResponse:
        settings = get_settings()
        factors: list[RiskFactor] = []
        total = 0.0

        if request.validation is not None:
            contribution = 0.0 if request.validation.is_valid else WEIGHTS["document_validation"]
            contribution += min(len(request.validation.warnings) * 2, WEIGHTS["document_validation"] / 2)
            contribution = min(contribution, WEIGHTS["document_validation"])
            total += contribution
            factors.append(RiskFactor(
                factor="Document Validation", weight=WEIGHTS["document_validation"], contribution=round(contribution, 1),
                detail="Failed required-field/date validation" if not request.validation.is_valid else "Passed with warnings" if request.validation.warnings else "Passed",
            ))

        if request.tampering is not None:
            contribution = request.tampering.confidence * WEIGHTS["tampering"]
            total += contribution
            factors.append(RiskFactor(
                factor="Tampering Detection", weight=WEIGHTS["tampering"], contribution=round(contribution, 1),
                detail=f"Status {request.tampering.status} ({request.tampering.confidence:.0%} confidence)",
            ))

        if request.face is not None:
            contribution = 0.0 if request.face.match else WEIGHTS["face_match"] * (1 - request.face.similarity_score)
            total += contribution
            factors.append(RiskFactor(
                factor="Face Verification", weight=WEIGHTS["face_match"], contribution=round(contribution, 1),
                detail=f"Similarity {request.face.similarity_score:.0%}, match={request.face.match}",
            ))

        if request.identity_search is not None:
            contribution = WEIGHTS["identity_search"] if request.identity_search.possible_multiple_identity else 0.0
            total += contribution
            top_match = request.identity_search.matches[0] if request.identity_search.matches else None
            factors.append(RiskFactor(
                factor="Identity Search", weight=WEIGHTS["identity_search"], contribution=round(contribution, 1),
                detail=f"Possible link to {top_match.identity_id} ({top_match.similarity:.0%})" if top_match else "No related identity found",
            ))

        if request.document_status is not None:
            status_weight = {"BLACKLISTED": 1.0, "REVOKED": 0.9, "EXPIRED": 0.4, "VALID": 0.0, "UNKNOWN": 0.3}
            contribution = status_weight.get(request.document_status.status, 0.3) * WEIGHTS["document_status"]
            total += contribution
            factors.append(RiskFactor(
                factor="Document Status", weight=WEIGHTS["document_status"], contribution=round(contribution, 1),
                detail=f"Status: {request.document_status.status}",
            ))

        if request.document_dna is not None:
            contribution = (request.document_dna.similarity_score / 100) * WEIGHTS["document_dna"] if request.document_dna.related_documents else 0.0
            total += contribution
            factors.append(RiskFactor(
                factor="Document DNA", weight=WEIGHTS["document_dna"], contribution=round(contribution, 1),
                detail=request.document_dna.summary,
            ))

        if request.cross_checkpoint is not None:
            contribution = WEIGHTS["cross_checkpoint"] if request.cross_checkpoint.alert else 0.0
            total += contribution
            factors.append(RiskFactor(
                factor="Cross-Checkpoint Intelligence", weight=WEIGHTS["cross_checkpoint"], contribution=round(contribution, 1),
                detail=request.cross_checkpoint.alert_message or "No cross-checkpoint pattern detected",
            ))

        if request.fraud_network is not None:
            # Scale by how many connected cases were found, capped at the factor's weight.
            contribution = min(request.fraud_network.connected_cases * 1.5, WEIGHTS["fraud_network"]) if request.fraud_network.connected_cases > 1 else 0.0
            total += contribution
            factors.append(RiskFactor(
                factor="Fraud Network", weight=WEIGHTS["fraud_network"], contribution=round(contribution, 1),
                detail=f"{request.fraud_network.connected_cases} connected document(s)" + (f" via {request.fraud_network.common_pattern}" if request.fraud_network.common_pattern else ""),
            ))

        risk_score = int(round(min(total, 100)))

        if risk_score <= settings.risk_low_max:
            risk_level = "LOW"
        elif risk_score <= settings.risk_medium_max:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"

        return RiskCalculateResponse(risk_score=risk_score, risk_level=risk_level, factors=factors)


def get_risk_engine() -> RiskEngine:
    return RiskEngine()
