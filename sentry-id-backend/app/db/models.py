"""
ORM models for the SENTRY-ID prototype.

IMPORTANT: All data created by seed.py is synthetic/demo data. Nothing here
represents a real government identity database. In a production system,
the `Identity` and `Document` tables would instead be read-only views or
API calls into the authoritative government systems, never a local copy.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.db.database import Base


def _uuid() -> str:
    return uuid.uuid4().hex[:12]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Identity(Base):
    """A demo identity record used for 1:N face-similarity search."""

    __tablename__ = "identities"

    identity_id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)
    nationality = Column(String, nullable=True)
    dob = Column(String, nullable=True)
    # Stored as a comma-separated string of floats to avoid a pgvector/FAISS
    # dependency in the prototype DB layer — the real embedding index lives
    # in the vector store abstraction (see services/identity_service.py).
    face_embedding = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class Document(Base):
    __tablename__ = "documents"

    document_number = Column(String, primary_key=True)
    document_type = Column(String, nullable=False)
    holder_name = Column(String, nullable=False)
    nationality = Column(String, nullable=True)
    dob = Column(String, nullable=True)
    gender = Column(String, nullable=True)
    issue_date = Column(String, nullable=True)
    expiry_date = Column(String, nullable=True)
    identity_id = Column(String, ForeignKey("identities.identity_id"), nullable=True)
    status = Column(String, default="VALID")  # VALID, EXPIRED, REVOKED, BLACKLISTED
    blacklist_reason = Column(String, nullable=True)
    dna_fingerprint = Column(Text, nullable=True)
    fraud_family_id = Column(String, ForeignKey("fraud_families.fraud_family_id"), nullable=True)
    created_at = Column(DateTime, default=_utcnow)


class CheckpointEvent(Base):
    """A single verification event at a checkpoint, used for cross-checkpoint intel."""

    __tablename__ = "checkpoint_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    identity_id = Column(String, ForeignKey("identities.identity_id"), nullable=True)
    document_number = Column(String, ForeignKey("documents.document_number"), nullable=True)
    checkpoint_name = Column(String, nullable=False)
    city = Column(String, nullable=True)
    risk_level = Column(String, default="LOW")
    timestamp = Column(DateTime, default=_utcnow)
    notes = Column(String, nullable=True)


class FraudFamily(Base):
    """A cluster of documents sharing a suspicious common pattern/source."""

    __tablename__ = "fraud_families"

    fraud_family_id = Column(String, primary_key=True, default=_uuid)
    common_pattern = Column(String, nullable=False)
    suspicious_source = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    documents = relationship("Document", backref="fraud_family", foreign_keys=[Document.fraud_family_id])


class ConfirmedFraudCase(Base):
    """Officer-confirmed fraud case, stored as a future training example."""

    __tablename__ = "confirmed_fraud_cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_number = Column(String, nullable=False)
    fraud_type = Column(String, nullable=False)
    detected_features = Column(Text, nullable=True)  # JSON-encoded list
    officer_id = Column(String, nullable=False)
    officer_notes = Column(String, nullable=True)
    confirmed_at = Column(DateTime, default=_utcnow)


class SelfTestRecord(Base):
    __tablename__ = "self_test_records"

    test_id = Column(String, primary_key=True, default=lambda: f"T-{_uuid()}")
    manipulation_type = Column(String, nullable=False)
    expected_detection = Column(Boolean, nullable=False)
    predicted_detection = Column(Boolean, nullable=False)
    confidence = Column(Float, nullable=False)
    correct = Column(Boolean, nullable=False)
    created_at = Column(DateTime, default=_utcnow)


class VerificationRecord(Base):
    """The persisted result of a full /api/screen pipeline run."""

    __tablename__ = "verification_records"

    verification_id = Column(String, primary_key=True, default=lambda: f"VER-{_uuid()}")
    document_number = Column(String, nullable=True)
    identity_id = Column(String, nullable=True)
    checkpoint_name = Column(String, nullable=True)
    risk_score = Column(Integer, nullable=False)
    risk_level = Column(String, nullable=False)
    result_json = Column(Text, nullable=False)  # full pipeline result, JSON-encoded
    officer_id = Column(String, nullable=True)
    officer_decision = Column(String, nullable=True)  # CLEARED / SECONDARY / DENIED, set later
    created_at = Column(DateTime, default=_utcnow)


class BlockchainRecord(Base):
    """
    Append-only audit hash log.

    Deliberately stores ONLY a hash + outcome, never PII — see
    services/blockchain_service.py for the hashing logic and the
    explicit exclusion list.
    """

    __tablename__ = "blockchain_records"

    verification_id = Column(String, primary_key=True)
    document_hash = Column(String, nullable=False)
    result = Column(String, nullable=False)  # VERIFIED / FLAGGED
    status = Column(String, default="CONFIRMED")
    timestamp = Column(DateTime, default=_utcnow)
