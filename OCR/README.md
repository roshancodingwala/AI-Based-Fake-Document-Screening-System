# Module 1 — OCR & Document Validation (SIHL26188)

A decoupled, evidence-only pipeline that extracts the data from a
document image and scores how well that **data hangs together** — it never
produces a fraud/genuine verdict.

```
 sample_generator ─► preprocessing ─► ocr_extractor ─► mrz_parser ─► document_rules ─► score
 (synthetic images)  (deskew/CLAHE/   (PaddleOCR /      (ICAO 9303     (per-type STRATEGY:
                      threshold;       Mock; lazy        TD1/TD2/TD3,   channels + secure anchor
                      two-copy          import)          check digits)  + checksum; required
                      contract)                                          fields, formats, MRZ
                        │                                                  digits, cross-source,
                        └► barcode_extractor (zxingcpp→cv2: Aadhaar QR     blacklist lookup)
                            payload / DL smart-card barcode)  ▲
                                                 logical_validator (dates/plausibility)
```

Every layer returns `schemas.ValidationFlag`s (code + severity + officer-facing
message) or the engine's `DocumentValidationResult`. No layer raises verdicts.

## Modules

| File | Role |
|---|---|
| `schemas.py` | Contracts only: enums, `ExtractedField`, `MRZResult`, `ValidationFlag`, `DocumentValidationResult`, `DocumentTemplate`, `build_score_breakdown`. |
| `mrz_parser.py` | ICAO 9303 MRZ (TD1/TD2/TD3) parser; 7-3-1 modulus-10 check digits (per-field + composite); field offsets **verified against real Doc 9303 specimens**, not self-generated. |
| `logical_validator.py` | Calendar rules on extracted dates: expired (warning), impossible orderings (high = "likely OCR misread"), age plausibility. |
| `document_rules.py` | Data-driven type-aware checks driven by `DOCUMENT_STRATEGY` (which evidence channels each type carries, its **secure-anchor** machine-readable zone, and its checksum): required fields, document-number format (loose/illustrative; **PAN alone gets strict structural validation** — holder-status char, surname-initial cross-check, reverse-engineered mod-36 check char), MRZ compliance, cross-source (MRZ vs visual) consistency, Aadhaar Verhoeff checksum, **Aadhaar-QR / DL-barcode↔visual consistency** (number/DOB/name/gender, order-insensitive name compare), **side-aware anchor policy** (Aadhaar QR lives on the back: a declared front-only capture downgrades `secure_anchor_missing` to a neutral note), injected blacklist lookup. |
| `verhoeff.py` | Verhoeff checksum (the UIDAI algorithm for Aadhaar): a failing 12-digit checksum is HIGH evidence of mis-OCR or a fabricated number; a passing one is informational only (numbers are not secret). |
| `barcode_extractor.py` | Machine-readable channels: Aadhaar `aadhaar_qr` (decodes the zlib-compressed UIDAI XML, flags the digital-signature element) and DL `dl_barcode` (JSON / delimited state layouts, licence-number-shaped token). Decodes off the **forensic copy** with `zxingcpp` → `cv2.QRCodeDetector` fallback; a missing/exploding backend degrades to no barcodes, never an exception. |
| `preprocessing.py` | Deskew (Hough lines; angle convention verified empirically), CLAHE (calibrated for faint text), adaptive threshold. **Two-copy contract**: forensic copy (pixel-untouched) + OCR copies (`clahe_gray`, `ocr_ready`) are independent arrays. |
| `ocr_extractor.py` | `PaddleOCRExtractor` (lazy import — model download never blocks module import; missing backend degrades to `recognized=False`) and `MockOCRExtractor` (raster-derived lines for tests/demo). Reads only the OCR-facing copies. |
| `validation_engine.py` | Orchestration: preprocess → OCR → MRZ discovery → **barcode decode** → field assembly → classification → rules + logical → calibrated score with always-complete `score_breakdown`. Visual recognizer is line-aware (label on one line takes the next line as value, and only **value-shaped** lines at that — a `PHOTO` token beside a DoB row is never read as a date; fragmented Aadhaar numbers are x-sorted before joining). Barcode payloads merge into fields as `BARCODE`-source evidence. |
| `template_recognizer.py` | Structure-aware ROI OCR: registered `DocumentTemplate`s (fractional ROIs, calibrated against a real Aadhaar letter photo and the PAN/DL synthetic generators) are cropped and OCR'd per field, so a value comes out of its exact box instead of whole-page regexing. The engine runs it only when the classified type matches a template and merges results fill-first (name-type fields are fill-only — whole-page reads beat band crops on names). |
| `sample_generator.py` | Seeded synthetic passport/ID images (rendered MRZ band + printable text), Indian-style passport page, Aadhaar card generator with a **real scannable, signature-carrying UIDAI-style QR**, smart-card driving licence (JSON barcode + licence number) and PAN card layouts — no real documents needed. |

## Design invariants (each enforced by a test)

1. **Evidence, never verdicts.** Expired = `warning`. Impossible date ordering = `high`, framed as "likely OCR misread". MRZ composite failure = `high`, framed as "OCR error, physical damage, OR alteration" — the evidence cannot tell these apart.
2. **Decoupling.** Rules never touch images; extraction never judges. `schemas` imports no OpenCV/OCR runtimes.
3. **UNKNOWN type is first-class.** An unrecognized document is scored with a named `UNKNOWN_TYPE_PENALTY`; it is never coerced into the nearest known type.
4. **Blacklist lookup is injected.** `None` → `info` "not configured"; exception/`None` result → `warning` "lookup failed", never silently swallowed and never treated as a clear.
5. **Two-copy preprocessing.** OCR consumes `clahe_gray`/`ocr_ready` only; the deskewed forensic copy (real pixel values) stays untouched for Module 2 tamper analysis.
6. **Graceful degradation.** A garbage image, timeout, or missing OCR backend yields a flagged result — not an exception.
7. **Verified, not assumed.** MRZ offsets/check digits are checked against real ICAO 9303 specimens; the deskew sign convention is pinned by tests on `getRotationMatrix2D`-rotated synthetics; `minAreaRect`'s angle (version-fragile, observed returning +80 for a −10° tilt on OpenCV 4.11) is deliberately not used.
8. **Per-type validation strategy.** Each document type reads through its own evidence channels (`DOCUMENT_STRATEGY`), each with a *secure-anchor* machine-readable zone it SHOULD carry — Aadhaar = UIDAI QR (+ Verhoeff), Driving Licence = smart-card barcode, Passport / Residence permit = MRZ, PAN / Voter / National ID have none. A missing anchor is a WARNING (capture failure, legacy variant, or forged copy — the evidence cannot tell these apart) and can never fire on a type that doesn't carry the zone, which is what kills false negatives. Because the Aadhaar QR physically lives on the back of the card, a caller-declared `input_sides='front'` downgrades the missing-zone flag to a neutral `anchor_not_verifiable` note — an honest front-only capture is never silently penalized. Machine-read payloads are checked against the OCR'd zone: agreement is informational, disagreement is HIGH evidence of alteration.
9. **Machine-read zones are decoded off the forensic copy.** Barcode/QR readers need true quiet zones and pixel-level contrast — they get the deskewed, pixel-untouched copy, never the thresholded OCR arrays.

## Scoring

`validation_score` (0-100) = data-coherence, computed as
`100 − flag_deductions − confidence_deductions − unknown_type_penalty`, with
named constants in `validation_engine.py` (HIGH 22 / WARNING 8 / INFO 0,
capped at 60 in flag band) and an always-present `score_breakdown`
(`flag_deductions`, `confidence_deductions`, `unknown_type_penalty`,
`remaining_points`). It deliberately ignores image authenticity and
face-match (Modules 2+).

## Run

All phases are verified by an image-free unit suite with synthetic inputs:

```
python3 -m pytest tests/ -q
```

Demo (Python):

```python
import sys; sys.path.insert(0, ".")
from sample_generator import make_passport_image
from validation_engine import EngineOptions, ValidationEngine

SPECIMEN = (
    "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
    "L898902C<3UTO6908061F9406236ZE184226B<<<<<14",
)
specimen = make_passport_image(mrz_lines=SPECIMEN, seed=1)

# Fast, dependency-free path (mock reads the OCR copy):
result = ValidationEngine().validate_image(specimen.image)
print(result.document_type, result.validation_score)

# Real OCR path (first run downloads PP-OCR models; paddleocr installed):
from ocr_extractor import PaddleOCRExtractor
result = ValidationEngine(
    EngineOptions(ocr_extractor=PaddleOCRExtractor())
).validate_image(specimen.image)
```

Ready-made samples (drag & drop onto `run_image.py`, or pass on the CLI). All are regenerated
by the generators (`make_*_image`); Aadhaar and DL ship with scannable machine-readable zones:

| File | What it demonstrates |
|---|---|
| `indian_passport_sample.png` | Clean Indian-style passport: `passport`, MRZ found, ~100 |
| `aadhaar_sample.png` | Clean Aadhaar card (no real QR in this shipped file, so the anchor-warning fires): `aadhaar`, Verhoeff pass, ~92 |
| `aadhaar_tampered.png` | Altered number (no QR present): `aadhaar_checksum_failed` HIGH, ~70 (incl. the `secure_anchor_missing` warning) |
| `sample_aadhaar_qr.png` | Aadhaar card with a real sealed UIDAI-style QR: `aadhaar_qr` channel decoded, payload signed + Verhoeff-verified, ~100 |
| `sample_dl.png` | Smart-card driving licence with a JSON barcode: `dl_barcode` channel matches the printed licence number, ~100 |
| `sample_pan.png` | PAN card: `pan_card` with alphanumeric number + DOB from the registered template, ~100 |
| `synthetic_passport_valid.png` | Valid-expiry passport, ~92 |
| `synthetic_passport.png` | Expired specimen, ~84 (expired warning) |

Runtime dependencies beyond the README-documented stack: `zxing-cpp` (preferred QR/barcode
decoder) and `qrcode` (sample generator + QR round-trip tests). Both install via pip and
degrade gracefully — `cv2.QRCodeDetector` remains the fallback decoder.

## What remains unverified / calibration TODOs

- **Document-number formats** in `document_rules.py` are loose and
  *illustrative* for all types **except PAN**, which now has strict structural
  validation (position constraints, holder-status code, surname-initial
  cross-check, and a reverse-engineered mod-36 check char). The remaining
  loose patterns must be validated against each issuing authority's real
  numbering scheme before production use.
- **Scoring constants** (deduction amounts, CLAHE clip, Hough parameters,
  plausibility ages, type-hint weights) are starting values calibrated on
  synthetic inputs — tune against a labelled corpus of real checkpoint
  photos.
- **Century inference** for 2-digit MRZ years is a documented heuristic
  (DOB biases to past; expiry to nearest century).
- **Visual-zone recognizer** is a label→value regex fallback; production uses
  template ROIs (`schema.DocumentTemplate`, fractional coordinates) via
  `template_recognizer.py`. The paper-Aadhaar-letter and the PAN/DL synthetic
  layouts are calibrated; every new fixed layout needs its own template and a
  photo to tune against.
- **Aadhaar QR signature** detection only flags the *presence* of UIDAI's
  signature element; real verification needs UIDAI's public key and belongs
  to a trusted verifier stage (a deliberately softer guarantee).
- **DL barcode layout** is best-effort — states encode different payloads;
  the licence-number-shaped token is what cross-source rules rely on.
- Real PaddleOCR quality (models) has not been end-to-end tuned against
  sample scans.