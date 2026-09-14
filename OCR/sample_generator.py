"""Synthetic sample generator for demos and tests (no real documents needed).

Produces deterministic, passport-like document images:

  * patterned 'paper' background (the low-contrast case CLAHE targets),
  * a photo placeholder and printed text fields (real glyphs via
    ``cv2.putText`` so a real OCR backend like PaddleOCR can be demoed),
  * an optional MRZ band at the bottom. When ``mrz_lines`` are supplied they
    are rendered as monospaced glyphs, so an OCR pass can in principle read
    them back; each character sits in a fixed cell matching ICAO's fixed
    column widths.

Everything is driven by integer seeds -- same seed, same image. The generator
also returns the ground-truth text lines it rendered so a caller can check
whether an OCR pass recovered them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import cv2
import numpy as np

#: Printable MRZ alphabet (ICAO subset) -- anything else is replaced by '<'.
MRZ_CHARS: str = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"
#: MRZ glyph cell size (px) and scale for the rendered band.
_MRZ_CELL_W: int = 22
_MRZ_CELL_H: int = 34
_MRZ_FONT_SCALE: float = 0.9


@dataclass
class SyntheticSample:
    """A generated document image plus ground-truth metadata."""

    image: np.ndarray
    seed: int
    width: int
    height: int
    mrz_lines: list[str] = field(default_factory=list)
    visual_lines: list[str] = field(default_factory=list)


def _patterned_paper(
    width: int,
    height: int,
    background: int,
    seed: int,
    scatter: int = 18,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.full((height, width), background, np.uint8)
    for _ in range(int(width * height / 9000)):
        x0 = int(rng.integers(0, width - 130))
        y0 = int(rng.integers(0, height - 90))
        val = int(rng.integers(max(0, background - scatter), min(255, background + 12)))
        cv2.rectangle(img, (x0, y0), (x0 + 130, y0 + 90), val, -1)
    return img


def _put_text_line(
    img: np.ndarray,
    text: str,
    x: int,
    y: int,
    scale: float = 0.9,
    thickness: int = 1,
) -> None:
    """Draw a light-gray 'printed value' text line (OCR-testable)."""
    cv2.putText(
        img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale,
        (30, 30, 30), thickness, cv2.LINE_AA,
    )


def render_mrz_line(
    line: str, cell_w: int = _MRZ_CELL_W, cell_h: int = _MRZ_CELL_H
) -> np.ndarray:
    """Render one MRZ line as monospaced glyphs on a light background."""
    safe = "".join(ch if ch in MRZ_CHARS else "<" for ch in line)
    width = len(safe) * cell_w
    img = np.full((cell_h + 12, width), 245, np.uint8)
    for i, ch in enumerate(safe):
        x = i * cell_w + (cell_w // 2 - 8)
        cv2.putText(
            img, ch, (x, cell_h), cv2.FONT_HERSHEY_SIMPLEX,
            _MRZ_FONT_SCALE, (25, 25, 25), 1, cv2.LINE_AA,
        )
    return img


def make_passport_image(
    *,
    mrz_lines: Optional[Sequence[str]] = None,
    seed: int = 0,
    width: int = 1080,
    height: int = 720,
    background: int = 208,
    date_of_birth: str = "06/08/1969",
    date_of_expiry: Optional[str] = None,
) -> SyntheticSample:
    """Generate a passport-like page with optional rendered MRZ band.

    ``date_of_birth`` / ``date_of_expiry`` drive the printed visual zone and
    default to the classic expired ICAO specimen (1969-08-06). Pass explicit
    dates that match the MRZ you embed so the synthetic document is internally
    consistent (visual vs. MRZ agreement is part of the checks).
    """
    mrz = list(mrz_lines) if mrz_lines else []

    img = _patterned_paper(width, height, background, seed)

    # header
    hdr_y = 78
    cv2.rectangle(img, (40, 30), (width - 40, hdr_y + 14), (185, 185, 185), -1)
    _put_text_line(img, f"REPUBLIC OF UTOPIA  SEED {seed:04d}", 60, hdr_y + 10, 1.0, 2)
    _put_text_line(img, "PASSPORT", width // 2 - 60, hdr_y + 48, 1.2, 2)

    # photo placeholder
    cv2.rectangle(img, (60, hdr_y + 90), (300, hdr_y + 330), (160, 160, 160), -1)
    cv2.rectangle(img, (70, hdr_y + 100), (290, hdr_y + 320), (120, 120, 120), 2)

    # printed fields (visual zone, DD/MM/YYYY like real passports)
    visual = [
        "NAME:  ERIKSSON ANNA MARIA",
        "FATHER:  ERIKSSON OLOF",
        f"DATE OF BIRTH: {date_of_birth}",
        "PLACE OF BIRTH:  UTOPIA",
    ]
    if date_of_expiry:
        visual.append(f"DATE OF EXPIRY: {date_of_expiry}")
    y = hdr_y + 90
    for i, line_text in enumerate(visual):
        yy = y + 46 + i * 58
        cv2.rectangle(img, (340, yy - 28), (width - 60, yy + 8), (196, 196, 196), -1)
        _put_text_line(img, line_text, 352, yy, 1.0, 2)

    if mrz:
        band_w = max(len(ln) for ln in mrz)
        strips = []
        for ln in mrz:
            cell_img = render_mrz_line(ln)
            padded = np.full((cell_img.shape[0], band_w * _MRZ_CELL_W), 245, np.uint8)
            start_x = ((band_w - len(ln)) * _MRZ_CELL_W) // 2
            padded[:, start_x:start_x + cell_img.shape[1]] = cell_img
            strips.append(padded)
        band = np.vstack(strips)
        h, w = band.shape
        y0 = height - h - 24
        img[y0:y0 + h, :w] = band

    return SyntheticSample(
        image=img,
        seed=seed,
        width=width,
        height=height,
        mrz_lines=mrz,
        visual_lines=visual,
    )


def _mrz_date_field(value: str) -> str:
    """Convert a DD/MM/YYYY (or YYYY-MM-DD) date to the 6-char MRZ YYMMDD."""
    import datetime as _dt

    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            d = _dt.datetime.strptime(value, fmt)
            return f"{d.year % 100:02d}{d.month:02d}{d.day:02d}"
        except ValueError:
            continue
    raise ValueError(f"Unsupported date format: {value!r}")


def make_indian_passport_image(
    *,
    seed: int = 5,
    width: int = 1100,
    height: int = 760,
    blank_photo: bool = True,
    watermarked: bool = True,
    surname: str = "SINGH",
    given_names: str = "ARJUN KUMAR",
    passport_number: str = "AB1234567",
    nationality: str = "INDIAN",
    date_of_birth: str = "15/08/1995",
    sex: str = "M",
    place_of_birth: str = "DELHI",
    date_of_issue: str = "28/11/2022",
    date_of_expiry: str = "27/11/2032",
    authority: str = "RPO DELHI",
) -> SyntheticSample:
    """Generate an Indian-style passport data page shaped like a real TD3
    passport (machine-readable zone, blank photo box, field grid).

    Layout, MRZ geometry and check-digit placement follow ICAO Doc 9303 /
    the public DIAC sample sheet; every value is fictional specimen data and
    the result is watermarked SPECIMEN. The photo area is left blank.
    """
    from PIL import Image, ImageDraw, ImageFont

    import os as _os

    _FONT_DIR = _os.path.join(_os.environ.get("WINDIR", "C:\\Windows"), "Fonts")

    def font(name: str, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(_os.path.join(_FONT_DIR, name), size)

    # ---- MRZ lines (TD3) with valid ICAO check digits --------------------
    from mrz_parser import compute_check_digit

    name_fill = surname.replace(" ", "<") + "<<" + given_names.upper().replace(" ", "<")
    name39 = (name_fill + "<" * 39)[:39]
    line1 = "P<IND" + name39

    doc = passport_number[:9].ljust(9, "<")
    c1 = compute_check_digit(doc)
    dob = _mrz_date_field(date_of_birth)
    c2 = compute_check_digit(dob)
    exp = _mrz_date_field(date_of_expiry)
    c3 = compute_check_digit(exp)
    personal = "<" * 14  # no personal number on Indian passports -> fillers
    core = doc + str(c1) + "IND" + dob + str(c2) + sex + exp + str(c3) + personal
    # composite digit sits in the final column; its data covers positions
    # 1-10, 14-20, 22-43 (Doc 9303), i.e. everything up to the last index.
    comp = compute_check_digit(core)
    line2 = core + str(comp) + str(compute_check_digit(core + str(comp)))
    # document number check digit -> doc + its check (Doc 9303 line 2 col 44)

    # ---- page --------------------------------------------------------------
    img = Image.new("RGB", (width, height), (246, 244, 238))
    draw = ImageDraw.Draw(img)
    ink = (24, 28, 34)
    gray = (128, 128, 128)

    f_head = font("calibri.ttf", 46)
    f_title = font("calibri.ttf", 30)
    f_label = font("arial.ttf", 15)
    f_value = font("arialbd.ttf", 20)
    f_mrz = font("courbd.ttf", 38)

    # header band
    draw.rectangle((0, 0, width, 118), fill=(26, 45, 90))
    # generic emblem placeholder (roundel, not the national emblem)
    ex, ey = 92, 62
    draw.ellipse((ex - 34, ey - 34, ex + 34, ey + 34), outline=(214, 190, 120), width=4)
    draw.ellipse((ex - 24, ey - 24, ex + 24, ey + 24), outline=(214, 190, 120), width=2)
    for a in range(0, 360, 30):
        import math as _m

        x1 = ex + int(30 * _m.cos(_m.radians(a)))
        y1 = ey + int(30 * _m.sin(_m.radians(a)))
        x2 = ex + int(36 * _m.cos(_m.radians(a)))
        y2 = ey + int(36 * _m.sin(_m.radians(a)))
        draw.line((x1, y1, x2, y2), fill=(214, 190, 120), width=2)
    draw.text((ex + 60, 22), "REPUBLIC OF INDIA", font=f_head, fill=(240, 240, 240))
    draw.text((ex + 60, 76), "PASSPORT", font=f_title, fill=(240, 240, 240))

    # left column field grid
    labels = [
        ("TYPE", "P", 2), ("CODE", "IND", None),
        ("PASSPORT NO.", passport_number, 2),
        ("SURNAME", surname, 1),
        ("GIVEN NAMES", given_names, 1),
        ("NATIONALITY", nationality, 1),
        ("DATE OF BIRTH", date_of_birth, 1),
        ("SEX", sex, 1),
        ("PLACE OF BIRTH", place_of_birth, 1),
        ("DATE OF ISSUE", date_of_issue, 1),
        ("DATE OF EXPIRY", date_of_expiry, 1),
        ("AUTHORITY", authority, 1),
    ]
    x0, y0 = 70, 175
    row_h = 52
    col_w = 340
    for i, (label, value, span) in enumerate(labels):
        row = i
        x = x0 + (1 if isinstance(span, int) else 0) * col_w
        yy = y0 + row * row_h
        draw.text((x, yy + 2), label, font=f_label, fill=gray)
        draw.text((x, yy + 20), value, font=f_value, fill=ink)

    # blank photo box (top-right)
    px0, py0 = width - 320, 165
    draw.rectangle((px0, py0, px0 + 260, py0 + 330), outline=(90, 90, 96), width=2)
    if blank_photo:
        draw.text((px0 + 96, py0 + 150), "PHOTO", font=f_label, fill=(150, 150, 155))

    # signature strip
    draw.line((x0, y0 + 12 * row_h + 24, x0 + 300, y0 + 12 * row_h + 24),
              fill=(80, 80, 80), width=1)
    draw.text((x0, y0 + 12 * row_h + 30), "HOLDER SIGNATURE / THUMB IMPRESSION",
              font=f_label, fill=gray)

    if watermarked:
        _apply_watermark(img, "SPECIMEN", font("calibri.ttf", 64))

    # ---- MRZ band (bottom, ICAO geometry) --------------------------------
    band_l, band_r = 55, width - 55
    cell_w = (band_r - band_l) / 44.0
    band_y = height - 2 * int(cell_w * 1.5) - 42
    for k, ln in enumerate((line1, line2)):
        yy = band_y + k * int(cell_w * 1.5)
        for j, ch in enumerate(ln):
            draw.text((band_l + int(j * cell_w) + 2, yy + 4),
                      ch, font=f_mrz, fill=(15, 15, 15))

    img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    return SyntheticSample(
        image=img,
        seed=seed,
        width=width,
        height=height,
        mrz_lines=[line1, line2],
        visual_lines=[
            f"SURNAME: {surname}",
            f"GIVEN NAMES: {given_names}",
            f"PASSPORT NO: {passport_number}",
            f"DATE OF BIRTH: {date_of_birth}",
            f"SEX: {sex}",
            f"DATE OF EXPIRY: {date_of_expiry}",
        ],
    )


def _apply_watermark(img: Image.Image, text: str, font) -> None:
    """Paste a faint rotated ``text`` across the image (keeps samples clearly
    non-authentic while preserving the underlying layout)."""
    from PIL import Image, ImageDraw

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.text((img.size[0] // 2 - 130, img.size[1] // 2), text, font=font,
           fill=(150, 150, 150, 80))
    overlay = overlay.rotate(30, expand=False)
    flat = Image.new("RGB", img.size, (150, 150, 150))
    img.paste(flat, (0, 0), overlay)


def _render_qr_pil(payload_bytes: bytes, target_px: int = 220) -> "Image.Image":
    """Render a scannable QR (black on white) via the ``qrcode`` library."""
    import qrcode
    from PIL import Image as _PILImage

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4,
        border=4,
    )
    qr.add_data(payload_bytes)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    if img.width != target_px:
        img = img.resize((target_px, target_px), _PILImage.Resampling.LANCZOS)
    return img


def _aadhaar_qr_payload(
    uid: str, name: str, gender: str, dob: str, address: str, pincode: str
) -> bytes:
    """Build a UIDAI-style ``PrintLetterBarcodeData`` XML, zlib-compressed.

    The layout mirrors the real UIDAI QR (compressed XML). The ``signature``
    is a synthetic placeholder so the payload exercises the
    ``signature_present`` evidence path -- real verification needs UIDAI's
    public key and belongs to a trusted verifier.
    """
    import zlib

    xml = (
        '<PrintLetterBarcodeData uid="{}" name="{}" gender="{}" yob="{}" '
        'dob="{}" co="RODAN" house="H.NO 42" street="KHANPUR" lm="KHANPUR" '
        'loc="RODAN" vtc="RODAN" subdist="RODAN" dist="SONIPAT" state="HARYANA" '
        'pc="{}" signature="a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718'
        '293a4b5c6d7e8f90"/>'.format(
            uid, name, gender, dob[:4], dob, pincode
        )
    )
    return zlib.compress(xml.encode("utf-8"))


def make_aadhaar_image(
    *,
    seed: int = 11,
    width: int = 1140,
    height: int = 720,
    blank_photo: bool = True,
    watermarked: bool = True,
    full_name: str = "SINGH ARJUN KUMAR",
    aadhaar_prefix: str = "23456789012",
    aadhaar_number: Optional[str] = None,
    date_of_birth: str = "15/08/1995",
    sex: str = "MALE",
    address: str = "H.NO 42, KHANPUR RODAN, HARYANA",
    include_qr: bool = True,
) -> SyntheticSample:
    """Generate an Aadhaar-card-style image (National ID, no MRZ).

    The printed 12-digit number is completed with its Verhoeff check digit, so
    the checksum evidence path is exercisable. Layout is an illustration of
    the UIDAI card structure: government header, blank photo box, name/DoB/
    sex, grouped number, and (when ``include_qr``) a REAL scannable QR that a
    barcode reader decodes into the UIDAI-style payload -- so the ``aadhaar_qr``
    channel is exercisable even with the mock OCR backend. Faint SPECIMEN
    watermark by default; all values are fictional.
    """
    from PIL import Image, ImageDraw, ImageFont

    import os as _os

    _FONT_DIR = _os.path.join(_os.environ.get("WINDIR", "C:\\Windows"), "Fonts")

    def font(name: str, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(_os.path.join(_FONT_DIR, name), size)

    from verhoeff import make_aadhaar_number

    if aadhaar_number is not None:
        if len(str(aadhaar_number)) != 12 or not str(aadhaar_number).isdigit():
            raise ValueError("aadhaar_number must be exactly 12 digits")
        number = str(aadhaar_number)
    else:
        number = make_aadhaar_number(aadhaar_prefix)
    if len(number) != 12:
        raise ValueError("Aadhaar prefix must be 11 digits")
    grouped = f"{number[0:4]} {number[4:8]} {number[8:12]}"

    img = Image.new("RGB", (width, height), (250, 248, 244))
    draw = ImageDraw.Draw(img)

    # tricolor + government header
    stripe_h = 14
    for x, color in ((0, (255, 103, 31)), (130, (255, 255, 255)),
                     (260, (19, 136, 8))):
        draw.rectangle((x, 26, x + 130, 26 + stripe_h), fill=color)
    f_head = font("calibri.ttf", 40)
    f_sub = font("arial.ttf", 22)
    draw.text((430, 20), "Government of India", font=f_head, fill=(24, 28, 34))
    draw.text((430, 72), "Unique Identification Authority of India",
              font=f_sub, fill=(110, 110, 115))

    # photo box (blank)
    px0, py0 = 60, 150
    draw.rectangle((px0, py0, px0 + 250, py0 + 330), outline=(90, 90, 96), width=2)
    if blank_photo:
        draw.text((px0 + 96, py0 + 150), "PHOTO", font=font("arial.ttf", 15),
                  fill=(150, 150, 155))

    # fields
    f_label = font("arial.ttf", 15)
    f_value = font("arialbd.ttf", 22)
    x0, y0 = 380, 160
    for label, value in [
        ("NAME", full_name), ("DoB", date_of_birth),
        ("SEX", sex), ("ADDRESS", address),
    ]:
        draw.text((x0, y0), label, font=f_label, fill=(110, 110, 115))
        draw.text((x0, y0 + 22), value, font=f_value, fill=(24, 28, 34))
        y0 += 78

    # your aadhaar number + big grouped digits
    draw.text((x0, y0 + 6), "Your Aadhaar Number", font=f_label, fill=(110, 110, 115))
    f_num = font("courbd.ttf", 44)
    draw.text((x0 + 2, y0 + 34), grouped, font=f_num, fill=(15, 15, 15))

    if watermarked:
        _apply_watermark(img, "SPECIMEN", font("calibri.ttf", 64))

    # real scannable UIDAI-style QR (top-right), pasted AFTER the watermark
    # so the quiet zone stays crisp for machine reading.
    qx, qy = width - 330, 150
    if include_qr:
        qr_img = _render_qr_pil(_aadhaar_qr_payload(
            number, full_name, sex, date_of_birth, address, "131303"
        ))
        img.paste(qr_img, (qx, qy))
    else:
        # decorative QR placeholder (generic grid, non-functional)
        cell, n = 5, 26
        qr = Image.new("RGB", (n * cell, n * cell), (255, 255, 255))
        d2 = ImageDraw.Draw(qr)
        for r in range(n):
            for c in range(n):
                if (r * 7 + c * 13 + seed) % 5 < 2:
                    d2.rectangle((c * cell, r * cell, c * cell + cell, r * cell + cell),
                                 fill=(20, 20, 20))
        for (r0, c0) in ((0, 0), (0, n - 7), (n - 7, 0)):
            for r in range(7):
                for c in range(7):
                    if r in (0, 6) or c in (0, 6) or 2 <= r <= 4 and 2 <= c <= 4:
                        d2.rectangle((c0 * cell + c * cell, r0 * cell + r * cell,
                                      c0 * cell + c * cell + cell, r0 * cell + r * cell + cell),
                                     fill=(20, 20, 20))
        img.paste(qr, (qx, qy))

    img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    return SyntheticSample(
        image=img,
        seed=seed,
        width=width,
        height=height,
        mrz_lines=[],
        visual_lines=[
            "UNIQUE IDENTIFICATION AUTHORITY OF INDIA",
            f"NAME: {full_name}",
            f"DOB: {date_of_birth}",
            f"SEX: {sex}",
            f"AADHAAR NUMBER: {grouped}",
        ],
    )


def make_keyword_id_image(
    *, keyword: str = "VOTER ID",
    headline: str = "ELECTION COMMISSION OF UTOPIA",
    seed: int = 3,
    width: int = 900,
    height: int = 600,
) -> SyntheticSample:
    """ID-card-like image carrying recognizer keywords (for type-hint demo)."""
    img = _patterned_paper(width, height, 212, seed)
    _put_text_line(img, headline, 120, 90, 1.1, 2)
    cv2.rectangle(img, (70, 130), (420, 360), (165, 165, 165), -1)
    cv2.rectangle(img, (80, 140), (410, 350), (120, 120, 120), 2)
    _put_text_line(img, keyword, 480, 200, 1.3, 2)
    _put_text_line(img, "CARD NUMBER: UTV1234567", 480, 260, 1.0, 2)
    return SyntheticSample(
        image=img, seed=seed, width=width, height=height,
        visual_lines=[headline, keyword],
    )


def make_pan_card_image(
    *,
    seed: int = 17,
    width: int = 900,
    height: int = 600,
    watermarked: bool = True,
    full_name: str = "SINGH ARJUN KUMAR",
    father_name: str = "SINGH SURESH KUMAR",
    pan_number: str = "ABCDE1234F",
    date_of_birth: str = "15/08/1995",
) -> SyntheticSample:
    """Generate a PAN-card-letter-style image (income-tax department).

    Standard paper-PAN layout: Income Tax header, a large Permanent Account
    Number, then a Name / Father's Name / Date of Birth grid. All values are
    fictional; the PAN number follows the canonical ``XXXXX1234X`` shape.
    """
    from PIL import Image, ImageDraw, ImageFont

    import os as _os

    _FONT_DIR = _os.path.join(_os.environ.get("WINDIR", "C:\\Windows"), "Fonts")

    def font(name: str, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(_os.path.join(_FONT_DIR, name), size)

    img = Image.new("RGB", (width, height), (248, 246, 241))
    draw = ImageDraw.Draw(img)
    ink = (24, 28, 34)
    gray = (110, 110, 115)

    # header band
    draw.rectangle((0, 0, width, 96), fill=(30, 42, 84))
    f_head = font("calibri.ttf", 40)
    f_sub = font("arial.ttf", 20)
    draw.text((width // 2 - 150, 16), "GOVT. OF INDIA", font=f_head, fill=(240, 240, 240))
    draw.text((width // 2 - 168, 62), "INCOME TAX DEPARTMENT", font=f_sub, fill=(214, 190, 120))

    # permanent account number (large, centered)
    f_label = font("arial.ttf", 22)
    draw.text((270, 132), "Permanent Account Number", font=f_label, fill=gray)
    f_pan = font("courbd.ttf", 52)
    draw.text((330, 178), pan_number, font=f_pan, fill=ink)

    # name/father/dob grid
    f_value = font("arialbd.ttf", 26)
    x_label, x_value = 200, 440
    for label, value, y in (
        ("Name", full_name, 330),
        ("Father's Name", father_name, 410),
        ("Date of Birth", date_of_birth, 490),
    ):
        draw.text((x_label, y), label, font=f_label, fill=gray)
        draw.text((x_value, y), value, font=f_value, fill=ink)

    draw.line((200, 550, 700, 550), fill=(80, 80, 80), width=1)
    draw.text((200, 556), "Applicant's Signature", font=f_label, fill=gray)

    if watermarked:
        _apply_watermark(img, "SPECIMEN", font("calibri.ttf", 64))

    img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    return SyntheticSample(
        image=img,
        seed=seed,
        width=width,
        height=height,
        mrz_lines=[],
        visual_lines=[
            "INCOME TAX DEPARTMENT",
            f"PERMANENT ACCOUNT NUMBER: {pan_number}",
            f"NAME: {full_name}",
            f"FATHER'S NAME: {father_name}",
            f"DATE OF BIRTH: {date_of_birth}",
        ],
    )


def make_driving_license_image(
    *,
    seed: int = 21,
    width: int = 1100,
    height: int = 690,
    watermarked: bool = True,
    full_name: str = "SINGH ARJUN KUMAR",
    date_of_birth: str = "15/08/1995",
    blood_group: str = "B+",
    address: str = "H.NO 42, KHANPUR RODAN, HARYANA",
    licence_number: str = "MH0120300567890",
    date_of_expiry: str = "27/11/2032",
    authority: str = "RTO MUMBAI WEST",
    include_barcode: bool = True,
) -> SyntheticSample:
    """Generate a smart-card driving licence style image.

    Layout follows the new-style Indian DL card: Licence title and transport
    mark, photo box, right-column Name/DoB/Blood group/Address, then the
    Licence No. (STATE(2)-RTO(2)-YEAR(4)-SERIAL(7+) shape) and validity
    dates. All values are fictional specimen data, watermarked SPECIMEN.
    """
    from PIL import Image, ImageDraw, ImageFont

    import os as _os

    _FONT_DIR = _os.path.join(_os.environ.get("WINDIR", "C:\\Windows"), "Fonts")

    def font(name: str, size: int) -> ImageFont.FreeTypeFont:
        return ImageFont.truetype(_os.path.join(_FONT_DIR, name), size)

    img = Image.new("RGB", (width, height), (246, 244, 238))
    draw = ImageDraw.Draw(img)
    ink = (24, 28, 34)
    gray = (110, 110, 115)

    # header
    draw.rectangle((0, 0, width, 112), fill=(26, 45, 90))
    f_title = font("calibri.ttf", 40)
    f_head = font("calibri.ttf", 22)
    draw.text((60, 20), "UNION OF INDIA", font=f_head, fill=(214, 190, 120))
    draw.text((60, 56), "DRIVING LICENCE", font=f_title, fill=(240, 240, 240))

    # blank photo box (left)
    px0, py0 = 60, 140
    draw.rectangle((px0, py0, px0 + 300, py0 + 330), outline=(90, 90, 96), width=2)
    draw.text((px0 + 120, py0 + 150), "PHOTO", font=f_head, fill=(150, 150, 155))

    # right column field grid
    f_label = font("arial.ttf", 24)
    f_value = font("arialbd.ttf", 28)
    f_address = font("arialbd.ttf", 24)
    x0 = 470
    y0 = 140
    for label, value, is_address in (
        ("Name", full_name, False),
        ("Date of Birth", date_of_birth, False),
        ("Blood Group", blood_group, False),
        ("Address", address, True),
    ):
        draw.text((x0, y0), label, font=f_label, fill=gray)
        draw.text((x0, y0 + 30), value, font=f_address if is_address else f_value, fill=ink)
        y0 += 96 + (18 if is_address else 0)

    # license number row
    y_row = 620
    draw.text((80, y_row), "Licence No.", font=f_label, fill=gray)
    draw.text((270, y_row - 2), licence_number, font=font("courbd.ttf", 34), fill=ink)
    draw.text((760, y_row), "Valid till", font=f_label, fill=gray)
    draw.text((900, y_row - 2), date_of_expiry, font=font("courbd.ttf", 34), fill=ink)
    draw.text((80, y_row + 46), "Authority: " + authority, font=f_label, fill=gray)

    if watermarked:
        _apply_watermark(img, "SPECIMEN", font("calibri.ttf", 64))

    # real scannable 2D barcode (top-right), after the watermark so the
    # reading zone stays crisp. Content is a JSON blob the DL parser
    # extracts the licence number from (state layouts vary in the wild).
    if include_barcode:
        import json

        payload = json.dumps(
            {
                "licenceNo": licence_number,
                "name": full_name,
                "dob": date_of_birth,
            }
        ).encode("utf-8")
        img.paste(_render_qr_pil(payload, target_px=170), (880, 130))

    img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    return SyntheticSample(
        image=img,
        seed=seed,
        width=width,
        height=height,
        mrz_lines=[],
        visual_lines=[
            "DRIVING LICENCE",
            f"NAME: {full_name}",
            f"DATE OF BIRTH: {date_of_birth}",
            f"BLOOD GROUP: {blood_group}",
            f"LICENCE NUMBER: {licence_number}",
            f"VALID TILL: {date_of_expiry}",
        ],
    )


def write_sample(sample: SyntheticSample, path: str) -> str:
    """Persist a synthetic sample as PNG (directory must exist)."""
    import os

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    cv2.imwrite(path, sample.image)
    return path