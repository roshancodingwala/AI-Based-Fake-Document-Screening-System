"""Interactive manual checker: pick a document type, get its exact evidence
checks. Usage: python manual_check.py <image_path> [--backend paddle|mock]

Menu (type-based, each maps to the checks THAT type can carry):
    1  Aadhaar          OCR + QR validation
                        (asks which side this photo is -- front, back or full
                         card -- then offers to upload the OTHER side's photo
                         path so the UIDAI QR (which lives on the BACK) is
                         decoded and cross-checked against the printed fields.
                         A front-only check turns "missing QR" into a neutral
                         note instead of evidence. Verhoeff on printed + QR
                         number, QR<->visual cross-check on number/DoB/name/
                         gender, secure-anchor presence)
    2  Passport         MRZ + OCR
                        (ICAO TD1/TD2/TD3 parse, 7-3-1 check digits incl.
                         composite, MRZ<->visual cross-check, expiry)
    3  Driving Licence  OCR + template + barcode
                        (smart-card barcode, licence-number format,
                         barcode<->visual cross-check, validity)
    4  PAN              OCR + format validation
                        (PAN number format, required fields; no machine
                         anchor exists on PAN)
    5  Miscellaneous    full auto pipeline (self-detected type)
    6  quit

The real OCR backend (paddle) is the default and is needed for the visual
side to be readable; use --backend mock for an instant offline pass where
only QR and MRZ produce results (visual fields classify as unknown).
"""

import argparse
import sys

sys.path.insert(0, ".")

import cv2

from ocr_extractor import PaddleOCRExtractor
from schemas import DocumentType
from validation_engine import EngineOptions, ValidationEngine


#: document-type menu -> which channels validate it.
#: (forced_type, skip_mrz, skip_barcodes)
TYPE_MODES = {
    "1": (DocumentType.AADHAAR, True, False),          # OCR + QR
    "2": (DocumentType.PASSPORT, False, True),         # MRZ + OCR
    "3": (DocumentType.DRIVING_LICENSE, True, False),  # OCR + barcode + template
    "4": (DocumentType.PAN_CARD, True, True),          # OCR + format
    "5": (None, False, False),                         # miscellaneous: full auto
}

TYPE_LABELS = {
    "1": "Aadhaar          OCR + QR (Verhoeff, anchor, cross-check)",
    "2": "Passport         MRZ + OCR (check digits, cross-check)",
    "3": "Driving Licence  OCR + barcode + template",
    "4": "PAN              OCR + format validation",
    "5": "Miscellaneous    full auto pipeline",
}

#: side prompt choice -> EngineOptions.input_sides value ('' = auto/unknown).
_SIDE_HELP = {
    "1": ("front", "front only -- the QR lives on the back, so \"missing QR\" "
                   "becomes a neutral note, NOT evidence"),
    "2": ("back", "back only / the UIDAI QR is in frame -- full anchor check"),
    "3": ("both", "both sides / full card -- full anchor check"),
    "4": ("", "not sure -- keep default behaviour (missing QR stays a warning)"),
}

_SIDE_PROMPT = (
    "\n which side(s) does this photo show?"
    "\n   1  front only (Aadhaar QR is on the back)"
    "\n   2  back only (UIDAI QR visible)"
    "\n   3  both sides / full card"
    "\n   4  not sure / auto"
    "\n> "
)


def prompt_sides() -> str:
    """Ask which physical side(s) the photo shows (Aadhaar's QR is on back)."""
    while True:
        try:
            choice = input(_SIDE_PROMPT).strip().lower()
        except (EOFError, KeyboardInterrupt):
            return ""
        if choice in _SIDE_HELP:
            side, hint = _SIDE_HELP[choice]
            if side:
                print(f" >> noted: {hint} ({side})")
            return side
        print(" !! choose 1-4")


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
    print("=" * 62)
    print(f" document type : {result.document_type.value} "
          f"(confidence {result.classification_confidence:.2f})")
    print(f" MRZ found     : {'yes' if result.mrz_found else 'no'}")
    print_qr_payload(result)
    print(f" score         : {result.validation_score}/100")
    print(f" breakdown     : {result.score_breakdown}")
    print_ledger(result)
    if result.barcodes:
        for b in result.barcodes:
            print(f" machine zone  : {b.channel}")
    if result.fields:
        for f in result.fields:
            v = (f.value[:40] + "…") if len(f.value) > 41 else f.value
            print(f" field         : {f.name}={v!r} [{f.source.value}]")
    high = [f for f in result.flags if f.severity.value == "high"]
    warnings = [f for f in result.flags if f.severity.value == "warning"]
    print(f" findings      : {len(high)} high, {len(warnings)} warning, "
          f"{len(result.flags) - len(high) - len(warnings)} info")
    for flag in high + warnings:
        print(f"   [{flag.severity.value.upper()}] {flag.code}")
        print(f"      {flag.message}")
    print(" note: score = data-coherence; NOT a fraud verdict.")
    print("=" * 62)


def prompt_aadhaar_side() -> str:
    """Ask which side the current photo is (Aadhaar's QR is on the back)."""
    print(" which side is THIS photo?")
    print("   1  front")
    print("   2  back (the UIDAI QR side)  -- the front will be required,"
          "\n      because a back photo alone carries no holder identity")
    print("   3  one photo already shows both / full card")
    while True:
        try:
            choice = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return ""
        if choice == "1":
            return "front"
        if choice == "2":
            return "back"
        if choice == "3":
            return "both"
        print(" !! choose 1-3")


def prompt_companion(other_side: str, current: str, required: bool) -> object:
    """Ask for the OTHER side's photo path.

    * ``required=False``: optional companion (front-only check). Returns the
      image, or None when skipped with Enter.
    * ``required=True``: mandatory companion (back-only is not validatable
      -- the holder's identity lives on the front). Returns the image, or
      None when the user backs out with 'x'.
    """
    if required:
        print(f"\n The {other_side.upper()} side is REQUIRED -- a back-only Aadhaar "
              "photo carries no holder name/DOB/address; only the front does.")
        while True:
            print(f" type the {other_side.upper()} side photo path (or 'x' "
                  "to go back to the side choice):")
            try:
                path = input("> ").strip().strip('"')
            except (EOFError, KeyboardInterrupt):
                return None
            if path.lower() in ("x", "back", "cancel", "quit") or not path:
                return None
            image = cv2.imread(path)
            if image is not None:
                print(f" >> front loaded: {path}")
                return image
            print(f" !! could not read '{path}' -- try again")
    print(f"\n add the {other_side.upper()} side photo too?")
    print(f" (type its path, or just press Enter to run the {current.upper()} alone)")
    try:
        path = input("> ").strip().strip('"')
    except (EOFError, KeyboardInterrupt):
        return None
    if not path:
        return None
    image = cv2.imread(path)
    if image is None:
        print(f" !! could not read '{path}' -- continuing as single "
              f"{current}-only check")
        return None
    print(f" >> companion loaded: {path}")
    return image


def build_engine(backend: str, forced_type, skip_mrz, skip_barcodes, input_sides=""):
    opts = EngineOptions(
        skip_mrz=skip_mrz,
        skip_barcodes=skip_barcodes,
        input_sides=input_sides,
    )
    if backend == "paddle":
        opts.ocr_extractor = PaddleOCRExtractor()
    return ValidationEngine(opts), forced_type


def run_checks(backend: str, image, choice: str, input_sides: str = "",
               companion=None):
    if choice not in TYPE_MODES:
        print(f" !! unknown choice '{choice}' (use 1-5)")
        return None
    forced_type, skip_mrz, skip_barcodes = TYPE_MODES[choice]
    label = TYPE_LABELS[choice].split("  ")[0]
    side_note = f", sides={input_sides}" if input_sides else ""
    duo = " + companion (other side)" if companion is not None else ""
    print(f"\n>>> running: {label} checks{side_note}{duo}")
    engine, forced = build_engine(backend, forced_type, skip_mrz, skip_barcodes,
                                  input_sides=input_sides)
    try:
        result = engine.validate_best_effort(
            image, forced_type=forced, companion_bgr=companion,
        )
        print_report(result)
        return result
    except Exception as exc:
        print(f" !! check failed: {type(exc).__name__}: {exc}")
        return None


def run_menu(backend: str, image, sides_flag: str) -> None:
    """Interactive per-file loop: pick type (and side for Aadhaar) and run."""
    print("   (0 = rerun last type)")

    last_choice = None
    last_sides = ""
    last_companion = None
    while True:
        print("-" * 62)
        print(" which document is this?")
        for key, label in TYPE_LABELS.items():
            print(f"   {key}  {label}")
        print("   6  quit")
        try:
            choice = input("> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        rerun = False
        if choice in ("6", "q", "quit", "exit"):
            break
        if choice == "0":
            choice = last_choice
            rerun = True
        if choice not in TYPE_MODES:
            print(" !! choose 1-5 (or 0 to rerun, 6 to quit)")
            continue
        last_choice = choice
        companion = None
        sides = sides_flag
        if choice == "1" and sides == "auto":
            if rerun and last_sides:
                sides = last_sides
                companion = last_companion
                if companion is not None:
                    sides = "both"  # companion present = dual-side check
                    print(" >> reusing last companion image")
                else:
                    print(f" >> reusing side note: {sides}")
            else:
                # Aadhaar side selection: front-only is allowed alone; a
                # back-only photo is NOT validatable and demands the front.
                while True:
                    award_side = prompt_aadhaar_side() or ""
                    if award_side == "both":
                        sides, companion = "both", None
                        last_sides, last_companion = "both", None
                        break
                    if award_side == "front":
                        companion = prompt_companion("back", "front", required=False)
                        sides = "both" if companion is not None else "front"
                        last_sides, last_companion = sides, companion
                        break
                    # back: the front is mandatory
                    companion = prompt_companion("front", "back", required=True)
                    if companion is not None:
                        sides, last_sides = "both", "both"
                        last_companion = companion
                        break
                    # user backed out of supplying the front -> re-ask side
                    print("\n !! A back-only Aadhaar photo can't be checked -- "
                          "the front is required (name/DOB/address live there, "
                          "not on the back).")
        run_checks(backend, image, choice, input_sides=sides, companion=companion)


def load_image(path: str, label: str):
    image = cv2.imread(path)
    if image is None:
        raise SystemExit(f"could not read {label} image: {path}")
    return image


def run_headless(args) -> int:
    """Non-interactive Aadhaar run: --front/--back, no menus."""
    if args.back and not args.front:
        print(" !! back-only Aadhaar can't be validated -- the front is"
              " required (the holder's name/DOB/address live there, not on"
              " the back). Pass --front too.")
        return 1
    primary = load_image(args.front or args.back,
                         "front" if args.front else "back")
    companion = load_image(args.back, "back") if args.back else None
    sides = "both" if companion is not None else "front"
    opts = EngineOptions(input_sides=sides)
    if args.backend == "paddle":
        opts.ocr_extractor = PaddleOCRExtractor()
    engine = ValidationEngine(opts)
    result = engine.validate_best_effort(
        primary, forced_type=DocumentType.AADHAAR, companion_bgr=companion,
    )
    print_report(result)
    return 0


def main(argv):
    parser = argparse.ArgumentParser(
        description="Manually check one document photo by type.",
    )
    parser.add_argument("path", nargs="?", help="document photo (BGR/jpg/png)")
    parser.add_argument("--front", help="Aadhaar FRONT photo (headless run: no menus)")
    parser.add_argument("--back", help="Aadhaar BACK photo (used with --front; "
                                       "back alone is refused)")
    parser.add_argument("--backend", choices=("paddle", "mock"), default="paddle",
                        help="OCR backend (default: paddle = real OCR; use mock for offline)")
    parser.add_argument("--type", choices=list(TYPE_MODES), default=None,
                        help="skip the menu and run this type's checks once (1-5)")
    parser.add_argument("--sides", choices=("auto", "front", "back", "both"), default="auto",
                        help="which side(s) the image shows (default auto/unknown). "
                             "Aadhaar QR lives on the back: 'front' turns a missing "
                             "QR into a neutral note, not evidence")
    args = parser.parse_args(argv)

    if args.front or args.back:
        sys.exit(run_headless(args))

    if args.path is None:
        parser.error("give a photo path, or use --front/--back for headless Aadhaar")

    image = load_image(args.path, "document")
    print(f"loaded: {args.path}  (backend: {args.backend}, sides: {args.sides})")

    if args.type:
        run_checks(args.backend, image, args.type, input_sides=args.sides)
        return
    run_menu(args.backend, image, args.sides)

    print("quitiinngggg")


if __name__ == "__main__":
    main(sys.argv[1:])