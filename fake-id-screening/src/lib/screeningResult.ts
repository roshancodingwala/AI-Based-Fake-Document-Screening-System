import { sampleResult } from "../data/mockData";

export interface ParsedScreeningResult {
  isLive: boolean;
  verificationId: string;
  timestamp: string;
  document: {
    name: string;
    docNumber: string;
    nationality: string;
    dob: string;
    gender: string;
    issueDate: string;
    expiryDate: string;
    docType: string;
  };
  ai: {
    ocrConfidence: number;
    authenticity: number;
    tamperingStatus: string;
    faceMatchScore: number;
    identityMatch: string;
    blacklistStatus: string;
    riskScore: number;
    riskLevel: string;
  };
  reasons: string[];
  raw?: any;
}

export function getActiveScreeningResult(): ParsedScreeningResult {
  try {
    const rawStr = localStorage.getItem("sentry_screening_result");
    if (!rawStr) {
      return {
        isLive: false,
        verificationId: "VER-88231 (Demo)",
        timestamp: "2026-09-05 09:12 UTC",
        document: sampleResult.document,
        ai: {
          ...sampleResult.ai,
          riskLevel: sampleResult.ai.riskScore >= 70 ? "HIGH" : sampleResult.ai.riskScore >= 40 ? "MEDIUM" : "LOW",
        },
        reasons: sampleResult.reasons,
      };
    }

    const data = JSON.parse(rawStr);
    const ocrFields = data.ocr?.fields || {};
    const riskScore = data.risk?.risk_score ?? data.riskScore ?? 87;
    const riskLevel = data.risk?.risk_level ?? (riskScore >= 70 ? "HIGH" : riskScore >= 40 ? "MEDIUM" : "LOW");
    const tamperingDetected = data.tampering?.tampering_detected ?? true;
    const tamperingConfidence = data.tampering?.confidence ?? 75;
    const faceMatch = data.face?.similarity_score ?? data.faceMatchScore ?? 82.1;
    const ocrConf = data.ocr?.ocr_confidence ?? data.ocrConfidence ?? 98.4;
    const reasons = data.reasons && Array.isArray(data.reasons) && data.reasons.length > 0
      ? data.reasons
      : sampleResult.reasons;

    return {
      isLive: true,
      verificationId: data.verification_id || "VER-LIVE",
      timestamp: new Date().toISOString().replace("T", " ").slice(0, 19) + " UTC",
      document: {
        name: ocrFields.name || "Rahul Sharma",
        docNumber: ocrFields.document_number || data.document_number || "P123456",
        nationality: ocrFields.nationality || "India",
        dob: ocrFields.date_of_birth || "1991-04-12",
        gender: ocrFields.gender || "Male",
        issueDate: ocrFields.issue_date || "2021-03-01",
        expiryDate: ocrFields.expiry_date || "2031-02-28",
        docType: ocrFields.visa_number ? "Visa" : "Passport",
      },
      ai: {
        ocrConfidence: Number(ocrConf),
        authenticity: Math.max(10, Math.round(100 - Number(tamperingConfidence))),
        tamperingStatus: tamperingDetected ? "Possible Alteration Detected" : "No Alteration Detected",
        faceMatchScore: Number(faceMatch),
        identityMatch: data.identity_search?.match_status || "Match Checked",
        blacklistStatus: data.document_status?.status || "Clear",
        riskScore: Number(riskScore),
        riskLevel,
      },
      reasons,
      raw: data,
    };
  } catch (err) {
    console.warn("Failed to parse live screening result, falling back to demo:", err);
    return {
      isLive: false,
      verificationId: "VER-88231 (Demo)",
      timestamp: "2026-09-05 09:12 UTC",
      document: sampleResult.document,
      ai: {
        ...sampleResult.ai,
        riskLevel: sampleResult.ai.riskScore >= 70 ? "HIGH" : "MEDIUM",
      },
      reasons: sampleResult.reasons,
    };
  }
}

export function clearScreeningResult() {
  localStorage.removeItem("sentry_screening_result");
}
