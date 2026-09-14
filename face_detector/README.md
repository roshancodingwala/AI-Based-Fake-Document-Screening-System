# AI-Based Fake Identity & Document Screening System

An automated multi-module AI solution for border checkpoint security, real-time identity verification, metadata tampering inspection, and automated risk scoring.

## System Architecture & Modules
- **Module 1 (OCR Extraction):** Automated text parsing (Passport ID, DOB) via EasyOCR.
- **Module 2 (Document Validation):** Immigration database lookup & blacklist checking.
- **Module 3 (Tampering Detection):** EXIF metadata audit for software alterations (Photoshop/Canva).
- **Module 4 (Face Verification):** Deep Learning (ResNet-29) 128-d vector face embedding matching with real-time confidence scores.
- **Audit Engine:** Automated PDF verification report generation.

## Execution Command
```bash
python3 facerec_from_webcam_faster.py