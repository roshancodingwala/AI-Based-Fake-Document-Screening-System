"""
Seeds the prototype database with synthetic demo data.

The identities, documents and cases below are entirely fictional and are
shared with the companion frontend prototype purely so the two demos tell
the same story (Rahul Sharma / Rohan Kumar identity-shadow scenario, the
PB-2291 fraud cluster, etc). None of this is real government data.
"""
import json

from app.db.database import Base, SessionLocal, engine
from app.db.models import (
    CheckpointEvent,
    Document,
    FraudFamily,
    Identity,
    SelfTestRecord,
)


def _fake_embedding(seed: int, dim: int = 16) -> str:
    """Deterministic pseudo-embedding so demo similarity search is repeatable."""
    import random

    rnd = random.Random(seed)
    vec = [round(rnd.uniform(-1, 1), 4) for _ in range(dim)]
    return json.dumps(vec)


def seed_if_empty() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(Identity).count() > 0:
            return  # already seeded

        # --- Identities -----------------------------------------------------
        rahul = Identity(
            identity_id="IDN-RS001",
            name="Rahul Sharma",
            nationality="India",
            dob="1991-04-12",
            face_embedding=_fake_embedding(seed=1),
        )
        rohan = Identity(
            identity_id="ID78231",
            name="Rohan Kumar",
            nationality="India",
            dob="1990-11-30",
            # Intentionally close to `rahul`'s vector so the demo similarity
            # search surfaces a strong match, mirroring the frontend scenario.
            face_embedding=_fake_embedding(seed=1),
        )
        amina = Identity(identity_id="IDN-AY002", name="Amina Yusuf", nationality="Nigeria", dob="1994-02-20", face_embedding=_fake_embedding(2))
        liu = Identity(identity_id="IDN-LW003", name="Liu Wei", nationality="China", dob="1988-07-09", face_embedding=_fake_embedding(3))
        fatima = Identity(identity_id="IDN-FN004", name="Fatima Noor", nationality="Pakistan", dob="1996-01-15", face_embedding=_fake_embedding(4))
        db.add_all([rahul, rohan, amina, liu, fatima])
        db.flush()

        # --- Fraud family ----------------------------------------------------
        family = FraudFamily(
            fraud_family_id="PB-2291",
            common_pattern="Shared photo template & serial number range",
            suspicious_source="Unofficial print batch cluster PB-2291",
        )
        db.add(family)
        db.flush()

        # --- Documents --------------------------------------------------------
        docs = [
            Document(
                document_number="P123456",
                document_type="Passport",
                holder_name="Rahul Sharma",
                nationality="India",
                dob="1991-04-12",
                gender="Male",
                issue_date="2021-03-01",
                expiry_date="2031-02-28",
                identity_id="IDN-RS001",
                status="VALID",
                dna_fingerprint=json.dumps({"font": 0.91, "layout": 0.96, "compression": 0.88, "print_pattern": 0.97, "dimensions": 0.99, "security_features": 0.90, "photo_offset": 0.95}),
                fraud_family_id="PB-2291",
            ),
            Document(
                document_number="ID78231",
                document_type="National ID",
                holder_name="Rohan Kumar",
                nationality="India",
                dob="1990-11-30",
                gender="Male",
                issue_date="2019-06-01",
                expiry_date="2029-05-31",
                identity_id="ID78231",
                status="VALID",
                fraud_family_id="PB-2291",
            ),
            Document(
                document_number="V-77281",
                document_type="Visa",
                holder_name="Amina Yusuf",
                nationality="Nigeria",
                dob="1994-02-20",
                gender="Female",
                issue_date="2025-01-10",
                expiry_date="2027-01-09",
                identity_id="IDN-AY002",
                status="VALID",
            ),
            Document(
                document_number="ID-556213",
                document_type="National ID",
                holder_name="Liu Wei",
                nationality="China",
                dob="1988-07-09",
                gender="Male",
                issue_date="2020-03-01",
                expiry_date="2030-02-28",
                identity_id="IDN-LW003",
                status="VALID",
            ),
            Document(
                document_number="P-664521",
                document_type="Passport",
                holder_name="Fatima Noor",
                nationality="Pakistan",
                dob="1996-01-15",
                gender="Female",
                issue_date="2022-05-01",
                expiry_date="2032-04-30",
                identity_id="IDN-FN004",
                status="BLACKLISTED",
                blacklist_reason="BL-2214: Reported stolen document, filed 2025-08-01",
            ),
            # Related flagged documents used by the Document DNA endpoint
            Document(document_number="P-990211", document_type="Passport", holder_name="Demo Person A", status="VALID", fraud_family_id="PB-2291",
                      dna_fingerprint=json.dumps({"font": 0.90, "layout": 0.95, "compression": 0.86, "print_pattern": 0.96, "dimensions": 0.99, "security_features": 0.88, "photo_offset": 0.93})),
            Document(document_number="P-990873", document_type="Passport", holder_name="Demo Person B", status="VALID", fraud_family_id="PB-2291",
                      dna_fingerprint=json.dumps({"font": 0.89, "layout": 0.94, "compression": 0.85, "print_pattern": 0.95, "dimensions": 0.98, "security_features": 0.87, "photo_offset": 0.92})),
            Document(document_number="ID-772341", document_type="National ID", holder_name="Demo Person C", status="VALID", fraud_family_id="PB-2291",
                      dna_fingerprint=json.dumps({"font": 0.88, "layout": 0.93, "compression": 0.84, "print_pattern": 0.94, "dimensions": 0.97, "security_features": 0.86, "photo_offset": 0.91})),
            Document(document_number="P-991552", document_type="Passport", holder_name="Demo Person D", status="VALID", fraud_family_id="PB-2291",
                      dna_fingerprint=json.dumps({"font": 0.92, "layout": 0.97, "compression": 0.89, "print_pattern": 0.98, "dimensions": 0.99, "security_features": 0.91, "photo_offset": 0.96})),
        ]
        db.add_all(docs)
        db.flush()

        # --- Checkpoint history (cross-checkpoint intelligence demo) --------
        events = [
            CheckpointEvent(identity_id="ID78231", document_number="ID78231", checkpoint_name="Land Border Gate B", city="Amritsar", risk_level="LOW", notes="First seen as 'Rohan Kumar'"),
            CheckpointEvent(identity_id="ID78231", document_number="ID78231", checkpoint_name="Terminal 1", city="Mumbai", risk_level="MEDIUM", notes="Flagged for document mismatch"),
            CheckpointEvent(identity_id="IDN-RS001", document_number="P123456", checkpoint_name="Terminal 3", city="Delhi", risk_level="HIGH", notes="Presented as 'Rahul Sharma' with new passport"),
        ]
        db.add_all(events)

        # --- Self-test history --------------------------------------------
        tests = [
            SelfTestRecord(test_id="T-3391", manipulation_type="Photo Replacement", expected_detection=True, predicted_detection=True, confidence=96.4, correct=True),
            SelfTestRecord(test_id="T-3390", manipulation_type="Font Substitution", expected_detection=True, predicted_detection=True, confidence=91.2, correct=True),
            SelfTestRecord(test_id="T-3389", manipulation_type="MRZ Tampering", expected_detection=True, predicted_detection=True, confidence=98.7, correct=True),
            SelfTestRecord(test_id="T-3388", manipulation_type="Hologram Spoof", expected_detection=True, predicted_detection=False, confidence=54.1, correct=False),
            SelfTestRecord(test_id="T-3387", manipulation_type="Digital Re-scan Artefact", expected_detection=True, predicted_detection=True, confidence=88.9, correct=True),
        ]
        db.add_all(tests)

        db.commit()
    finally:
        db.close()
