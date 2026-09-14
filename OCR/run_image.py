"""CLI: insert a photo, get the Module-1 data-coherence score.

Usage:
    python run_image.py <image_path...> [--ocr mock|paddle] [--mrz <lines>]

DRAG-AND-DROP: on Windows you can drop one or more document photos straight
onto run_image.py (or its shortcut) -- each is validated in turn and the
console window stays open until you press Enter.

Default OCR backend is 'paddle' (real OCR; first run downloads the PP-OCR
models and may take a while). Use `--ocr mock` for an instant, dependency-free
pass that only exercises the machine-readable halves (QR / MRZ).

If a photo's MRZ is hard to read, validate MRZ lines directly and skip OCR:
    --mrz "P<...44 chars" "second line"
"""

import argparse
import sys

sys.path.insert(0, ".")

import cv2

from ocr_extractor import PaddleOCRExtractor
from template_recognizer import DEFAULT_TEMPLATES
from validation_engine import EngineOptions, ValidationEngine


def build_engine(ocr_backend: str, mrz_lines: list[str]):
    options = EngineOptions()
    if ocr_backend == "paddle":
        options.ocr_extractor = PaddleOCRExtractor()
        # Structure-aware ROI OCR needs a real OCR backend to read the
        # per-field crops; stick to the free-text recognizer under mock.
        options.templates = DEFAULT_TEMPLATES
    return ValidationEngine(options), mrz_lines


def run_from_disk(engine, path: str):
    image = cv2.imread(path)
    if image is None:
        raise SystemExit(f"could not read image: {path}")
    return engine.validate_image(image)


def print_ledger(result):
    print(" points ledger             (start 100.0, every named deduction)")
    print("   sev      pts      why                          -> balance")
    for entry in result.score_ledger:
        code = entry["code"]
        if code == "remaining_points":
            print(f"   -        -       remaining_points            -> {entry['balance']:>6.1f}")
            continue
        sev = entry["severity"].upper()[:4]
        pts = entry["deduction"]
        print(f"   {sev:<8} {-pts:>5.1f}    {code:<28} -> {entry['balance']:>6.1f}")
        print(f"            {entry['reason'][:70]}")


#: Aadhaar QR payload keys -> human-readable labels (A2 display).
_QR_FIELD_LABELS = (
    ("uid", "Aadhaar no"), ("name", "Name"), ("gender", "Gender"),
    ("dob", "DoB"), ("yob", "YoB"), ("co", "CO"), ("house", "House"),
    ("street", "Street"), ("lm", "Landmark"), ("loc", "Locality"),
    ("vtc", "VTC"), ("subdist", "Sub-district"), ("dist", "District"),
    ("state", "State"), ("pc", "PIN"), ("phone", "Phone"), ("email", "Email"),
)


def print_qr_payload(result):
    """Show the UIDAI-typed QR ground truth next to the OCR result."""
    for barcode in result.barcodes:
        if barcode.channel != "aadhaar_qr" or not barcode.data:
            continue
        print(" QR payload   (machine-typed ground truth from the UIDAI QR):")
        for key, label in _QR_FIELD_LABELS:
            value = barcode.data.get(key)
            if value:
                print(f"   {label:<13}: {value}")
        if barcode.signature_present:
            print("   signature   : UIDAI signature element PRESENT")
        else:
            print("   signature   : no signature element in payload")


def print_report(result):
    print("=" * 60)
    print(f" document type : {result.document_type.value} "
          f"(confidence {result.classification_confidence:.2f})")
    print(f" MRZ found     : {'yes' if result.mrz_found else 'no'}")
    print_qr_payload(result)
    print(f" score         : {result.validation_score}/100")
    print(f" breakdown     : {result.score_breakdown}")
    print_ledger(result)
    high = [f for f in result.flags if f.severity.value == "high"]
    warnings = [f for f in result.flags if f.severity.value == "warning"]
    print(f" findings      : {len(high)} high, {len(warnings)} warning, "
          f"{len(result.flags) - len(high) - len(warnings)} info")
    for flag in high + warnings:
        print(f"   [{flag.severity.value.upper()}] {flag.code}")
        print(f"      {flag.message}")
    print(" note: score measures whether the extracted DATA hangs together;")
    print("       it is NOT a fraud verdict and ignores image/face forensics.")
    print("=" * 60)


def main(argv):
    parser = argparse.ArgumentParser(
        description="Drop any document photo on this script to score it.",
    )
    parser.add_argument("paths", nargs="*",
                        help="document photo(s) to validate (BGR/jpg/png)")
    parser.add_argument("--ocr", choices=("mock", "paddle"), default="paddle",
                        help="OCR backend (default: paddle, real OCR; use mock for offline)")
    parser.add_argument("--mrz", nargs="+", default=None,
                        help="skip OCR and validate these MRZ lines directly")
    args = parser.parse_args(argv)

    if not args.paths and args.mrz is None:
        parser.error("drop an image onto this script, or use --mrz <lines>")

    engine, mrz_lines = build_engine(args.ocr, args.mrz or [])
    if mrz_lines:
        print_report(engine.validate_mrz_lines(mrz_lines))
    for path in args.paths:
        print(f"\nfile: {path}")
        print_report(run_from_disk(engine, path))

    # Keep the window open when launched by double-click / drag-and-drop.
    try:
        sys.stdin.isatty() and input("\nPress Enter to close...")
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main(sys.argv[1:])