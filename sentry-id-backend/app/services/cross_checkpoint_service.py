"""
Cross-checkpoint intelligence.

Looks at checkpoint history not just for the queried identity, but for the
whole cluster of identities linked through a shared fraud family (e.g. the
same person appearing under two different demo identities/documents). This
is what lets the system say "this suspicious pattern has been seen at 3
checkpoints" even though no single identity record was scanned 3 times.
"""
from sqlalchemy.orm import Session

from app.db.models import CheckpointEvent, Document
from app.schemas.intelligence import CheckpointHit, CrossCheckpointResponse


class CrossCheckpointService:
    def _cluster_identity_ids(self, db: Session, identity_id: str) -> set[str]:
        """All identity_ids linked to `identity_id` via a shared fraud family."""
        cluster = {identity_id}
        own_docs = db.query(Document).filter(Document.identity_id == identity_id).all()
        family_ids = {d.fraud_family_id for d in own_docs if d.fraud_family_id}

        for family_id in family_ids:
            siblings = db.query(Document).filter(Document.fraud_family_id == family_id).all()
            for sib in siblings:
                if sib.identity_id:
                    cluster.add(sib.identity_id)

        return cluster

    def get_history(self, db: Session, identity_id: str) -> CrossCheckpointResponse:
        cluster_ids = self._cluster_identity_ids(db, identity_id)

        events = (
            db.query(CheckpointEvent)
            .filter(CheckpointEvent.identity_id.in_(cluster_ids))
            .order_by(CheckpointEvent.timestamp.asc())
            .all()
        )

        history = [
            CheckpointHit(
                checkpoint_name=e.checkpoint_name,
                city=e.city,
                risk_level=e.risk_level,
                timestamp=e.timestamp,
                notes=e.notes,
            )
            for e in events
        ]

        distinct_checkpoints = {e.checkpoint_name for e in events}
        alert = len(distinct_checkpoints) >= 2 and any(e.risk_level in ("MEDIUM", "HIGH") for e in events)

        alert_message = None
        if alert:
            alert_message = (
                f"Same suspicious identity/document pattern detected across {len(distinct_checkpoints)} "
                f"checkpoints in the last 24 months. Recommend escalation to regional fraud unit."
            )

        return CrossCheckpointResponse(
            identity_id=identity_id,
            total_checkpoints=len(distinct_checkpoints),
            total_appearances=len(events),
            alert=alert,
            alert_message=alert_message,
            history=history,
        )


def get_cross_checkpoint_service() -> CrossCheckpointService:
    return CrossCheckpointService()

