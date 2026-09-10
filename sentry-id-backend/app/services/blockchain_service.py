"""
Prototype "blockchain" audit record.

This is a simple hash-chained append-only log, not a real distributed
ledger — it demonstrates the *data-minimisation* pattern (hash only,
never PII) that a real blockchain-audit integration should follow. Only
the verification ID, a hash of the outcome, and the result label are ever
written here; names, document numbers and photos never touch this table.
"""
import hashlib

from sqlalchemy.orm import Session

from app.db.models import BlockchainRecord


class BlockchainService:
    def record(self, db: Session, verification_id: str, outcome_summary: str, result: str) -> BlockchainRecord:
        # Hash only a non-reversible summary of the *outcome*, never the
        # underlying document fields.
        document_hash = hashlib.sha256(outcome_summary.encode("utf-8")).hexdigest().upper()

        record = BlockchainRecord(
            verification_id=verification_id,
            document_hash=document_hash,
            result=result,
            status="CONFIRMED",
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record


def get_blockchain_service() -> BlockchainService:
    return BlockchainService()
