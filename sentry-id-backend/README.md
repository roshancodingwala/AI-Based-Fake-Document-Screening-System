# SENTRY-ID Backend (Prototype)

FastAPI backend for the AI-Based Fake Identity & Document Screening System.
This is the companion backend for the `sentry-id-prototype` React frontend.

**Everything in this service is a prototype.** All identities, documents and
fraud cases are synthetic (see `app/db/seed.py`). Every AI-labelled response
includes `"is_simulated": true`. No real government data is used or stored.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

The database (SQLite by default) is created and seeded automatically on
first startup. Interactive API docs: http://127.0.0.1:8000/docs

Every request needs the header `X-API-Key: demo-officer-key-12345` (or
whatever you set `SENTRY_API_KEY` to in `.env`).

Run the test suite:
```bash
PYTHONPATH=. pytest tests/ -v
```

## Seeded demo scenario

The seed data reproduces the same "identity shadow" story used in the
frontend prototype:

- `IDN-RS001` — **Rahul Sharma**, holds Passport `P123456`
- `ID78231` — **Rohan Kumar**, holds National ID `ID78231`, biometrically
  near-identical to Rahul Sharma in the demo face index
- Both documents belong to fraud family `PB-2291` ("shared photo template
  & serial number range"), along with 4 other flagged demo documents
- `P-664521` (Fatima Noor) is seeded as `BLACKLISTED`

Try `POST /api/screen` with `identity_id=IDN-RS001` and any test image to
see the full pipeline flag the identity-shadow + fraud-network + document
DNA signals together.

## Architecture

```
routers/        FastAPI route handlers (thin — validate input, call a service)
services/       Business/AI logic, one module per pipeline stage
schemas/        Pydantic request/response models
db/             SQLAlchemy models + seed data
core/           Config, API-key auth, logging
utils/          Shared helpers (upload validation)
```

Every AI-labelled service (`ocr_service.py`, `tampering_service.py`,
`face_service.py`, `identity_service.py`) is written as an abstract
interface (`OCRService`, `FaceService`, ...) with a `Demo*`/`Heuristic*`
implementation behind a `get_*_service()` factory function. **This is the
intended extension point** — swap the factory's return value for a real
implementation without touching routers or schemas. Each service module's
docstring says exactly which library and call to use:

| Service | Prototype implementation | Production swap-in |
|---|---|---|
| OCR | Deterministic synthetic fields | PaddleOCR (`paddleocr`, `paddlepaddle`) |
| Tampering | Real OpenCV heuristics (ELA-style residual, edge density, blur variance) + demo scoring | Trained CNN/segmentation tamper classifier |
| Face verification | Hashed pseudo-embeddings, cosine similarity | InsightFace / ArcFace (`insightface`, `onnxruntime`) |
| Identity search | Linear numpy scan over demo embeddings | FAISS (`faiss-cpu`) or Qdrant (`qdrant-client`) |
| Fraud network | NetworkX graph over demo relational data | Same NetworkX API, or a graph DB (Neo4j/Neptune) at scale |

The heavier ML libraries (PaddleOCR, PyTorch, InsightFace, FAISS) are
listed but commented out in `requirements.txt` since they're multi-GB and
need GPU/ONNX setup not available in a typical prototype sandbox.

## API modules

All routes are prefixed as shown and require the `X-API-Key` header.

| Module | Endpoint |
|---|---|
| OCR | `POST /api/documents/ocr` |
| Validation | `POST /api/documents/validate` |
| Tampering | `POST /api/documents/tampering` |
| Face verification | `POST /api/face/verify` |
| Identity shadow | `POST /api/identity/search` |
| Document status | `GET /api/documents/status/{document_number}` |
| Document DNA | `POST /api/documents/dna` |
| Fraud family | `POST /api/fraud/family` |
| Cross-checkpoint intel | `GET /api/intelligence/cross-checkpoint/{identity_id}` |
| Fraud network | `GET /api/fraud/network/{identity_id}` |
| Fraud pattern learning | `POST /api/fraud/confirmed` |
| Self-testing AI | `POST /api/ai/self-test`, `GET /api/ai/self-test/history` |
| Risk engine | `POST /api/risk/calculate` |
| Full pipeline | `POST /api/screen` |
| Blockchain audit | `GET /api/blockchain/records` |
| Officer decision | `POST /api/verification/{verification_id}/decision` |

`POST /api/screen` runs the entire pipeline (OCR → validation → tampering →
face → identity search → document status → document DNA → cross-checkpoint
→ fraud network → risk score) in one call, persists a `VerificationRecord`,
and writes a hash-only audit row to the blockchain table.

## Security notes (prototype-level, not production-ready)

- Static API key auth only — replace with OAuth2/OIDC + RBAC before real use.
- Uploads are restricted by content-type allow-list and a 10MB size limit
  (`app/utils/file_validation.py`).
- The blockchain audit table stores **only** a hash of the outcome, never
  names, document numbers, or photos (`app/services/blockchain_service.py`).
- `sentry_id.audit` logger records every security-relevant event (auth
  failures, rejected uploads, officer decisions, confirmed fraud cases) —
  wire this to a real SIEM in production.
- CORS is wide open (`allow_origins=["*"]`) for local frontend development —
  lock this to the deployed frontend origin before shipping.
- SQLite is used for zero-setup local development; set `SENTRY_DATABASE_URL`
  to a Postgres DSN for anything beyond a laptop demo.

## Connecting the frontend

The companion React frontend expects a base URL (e.g. `http://localhost:8000`)
and the `X-API-Key` header on every request. CORS is already open for local
development, so pointing `fetch`/`axios` calls at this server should work
with no additional configuration.
