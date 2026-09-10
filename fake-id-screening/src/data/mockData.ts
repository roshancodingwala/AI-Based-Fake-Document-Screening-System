// All data in this file is SIMULATED / DEMO data for prototype purposes only.

export type RiskLevel = "low" | "medium" | "high" | "critical";
export type StageStatus = "completed" | "processing" | "warning" | "failed" | "pending";

export interface VerificationRecord {
  id: string;
  name: string;
  docType: "Passport" | "Visa" | "National ID" | "Driving Licence" | "Permit";
  docNumber: string;
  nationality: string;
  checkpoint: string;
  timestamp: string;
  riskScore: number;
  riskLevel: RiskLevel;
  status: "Verified" | "Suspicious" | "High Risk" | "Blacklisted";
}

export const kpis = {
  totalChecked: 18542,
  verified: 16890,
  suspicious: 1204,
  highRisk: 318,
  multipleIdentity: 87,
  blacklisted: 43,
};

export const weeklyVolume = [
  { day: "Mon", checked: 2340, flagged: 112 },
  { day: "Tue", checked: 2510, flagged: 98 },
  { day: "Wed", checked: 2680, flagged: 140 },
  { day: "Thu", checked: 2420, flagged: 121 },
  { day: "Fri", checked: 2890, flagged: 165 },
  { day: "Sat", checked: 3120, flagged: 178 },
  { day: "Sun", checked: 2582, flagged: 133 },
];

export const riskDistribution = [
  { name: "Low", value: 14980, color: "#3FC079" },
  { name: "Medium", value: 2610, color: "#E8A93B" },
  { name: "High", value: 634, color: "#F0495A" },
  { name: "Critical", value: 318, color: "#9333EA" },
];

export const recentActivity: VerificationRecord[] = [
  { id: "VER-88231", name: "Rahul Sharma", docType: "Passport", docNumber: "P123456", nationality: "India", checkpoint: "Terminal 3 - Counter 4", timestamp: "2026-09-05 09:12", riskScore: 87, riskLevel: "high", status: "High Risk" },
  { id: "VER-88230", name: "Amina Yusuf", docType: "Visa", docNumber: "V-77281", nationality: "Nigeria", checkpoint: "Terminal 1 - Counter 1", timestamp: "2026-09-05 09:05", riskScore: 12, riskLevel: "low", status: "Verified" },
  { id: "VER-88229", name: "Liu Wei", docType: "National ID", docNumber: "ID-556213", nationality: "China", checkpoint: "Land Border - Gate C", timestamp: "2026-09-05 08:58", riskScore: 64, riskLevel: "medium", status: "Suspicious" },
  { id: "VER-88228", name: "Carlos Mendes", docType: "Driving Licence", docNumber: "DL-902314", nationality: "Brazil", checkpoint: "Terminal 2 - Counter 7", timestamp: "2026-09-05 08:41", riskScore: 5, riskLevel: "low", status: "Verified" },
  { id: "VER-88227", name: "Fatima Noor", docType: "Passport", docNumber: "P-664521", nationality: "Pakistan", checkpoint: "Terminal 3 - Counter 2", timestamp: "2026-09-05 08:30", riskScore: 95, riskLevel: "critical", status: "Blacklisted" },
  { id: "VER-88226", name: "James O'Connor", docType: "Permit", docNumber: "PM-11982", nationality: "Ireland", checkpoint: "Land Border - Gate A", timestamp: "2026-09-05 08:22", riskScore: 22, riskLevel: "low", status: "Verified" },
];

export const verificationPipelineStages = [
  { key: "upload", label: "Document Uploaded" },
  { key: "ocr", label: "OCR Extraction" },
  { key: "validation", label: "Document Validation" },
  { key: "tampering", label: "Tampering Detection" },
  { key: "face", label: "Face Verification" },
  { key: "identity", label: "Identity Search" },
  { key: "fraud", label: "Fraud Network Check" },
  { key: "risk", label: "Risk Assessment" },
];

export const sampleResult = {
  document: {
    name: "Rahul Sharma",
    docNumber: "P123456",
    nationality: "India",
    dob: "1991-04-12",
    gender: "Male",
    issueDate: "2021-03-01",
    expiryDate: "2031-02-28",
    docType: "Passport",
  },
  ai: {
    ocrConfidence: 98.4,
    authenticity: 61,
    tamperingStatus: "Possible Alteration Detected",
    faceMatchScore: 82.1,
    identityMatch: "Partial Match Found",
    blacklistStatus: "Not Listed",
    riskScore: 87,
  },
  reasons: [
    "Photo region shows compression artefacts inconsistent with the rest of the page, suggesting possible photo substitution.",
    "Date of birth on the document does not match the date of birth linked to this face in a prior verification record.",
    "A separate identity record was found with 96.2% facial similarity under a different name and document number.",
    "This document's visual layout pattern matches 7 previously flagged fraudulent passports from the same issuing batch range.",
  ],
};

export const identityShadow = {
  current: { name: "Rahul Sharma", docType: "Passport", docNumber: "P123456", photoLabel: "Current Capture" },
  related: { name: "Rohan Kumar", docType: "National ID", docNumber: "ID78231", photoLabel: "Archived Record - 2023" },
  similarity: 96.2,
  status: "Possible Multiple Identity",
  matchedOn: ["Facial geometry", "Ear structure", "Voice print (partial)"],
  history: [
    { date: "2023-11-02", event: "First seen as 'Rohan Kumar' at Land Border Gate B", risk: "low" },
    { date: "2024-06-18", event: "Flagged for document mismatch at Terminal 1", risk: "medium" },
    { date: "2026-09-05", event: "Presented as 'Rahul Sharma' with new passport", risk: "high" },
  ],
};

export const fraudNetwork = {
  connectedCases: 6,
  commonPattern: "Shared photo template & serial number range",
  suspiciousSource: "Batch cluster PB-2291 (unofficial print shop signature)",
  checkpointsInvolved: ["Terminal 3", "Land Border Gate B", "Terminal 1"],
  nodes: [
    { id: "personA", label: "Rahul Sharma", type: "person" },
    { id: "passA", label: "Passport P123456", type: "document" },
    { id: "pattern", label: "Suspicious Pattern PB-2291", type: "pattern" },
    { id: "passB", label: "ID ID78231", type: "document" },
    { id: "personB", label: "Rohan Kumar", type: "person" },
    { id: "checkpoint1", label: "Terminal 3", type: "checkpoint" },
    { id: "checkpoint2", label: "Land Border Gate B", type: "checkpoint" },
    { id: "case1", label: "Case #FN-2291", type: "case" },
  ],
  edges: [
    ["personA", "passA"],
    ["passA", "pattern"],
    ["pattern", "passB"],
    ["passB", "personB"],
    ["personA", "checkpoint1"],
    ["personB", "checkpoint2"],
    ["pattern", "case1"],
  ],
};

export const documentDNA = {
  matchScore: 94,
  summary: "Similar pattern detected in 7 previously flagged documents.",
  factors: [
    { name: "Font signature", score: 91 },
    { name: "Layout grid", score: 96 },
    { name: "Image compression profile", score: 88 },
    { name: "Print pattern (microtext)", score: 97 },
    { name: "Document dimensions", score: 99 },
    { name: "Security feature placement", score: 90 },
    { name: "Photo placement offset", score: 95 },
  ],
  relatedDocuments: [
    { id: "P-990211", flaggedOn: "2025-02-11", match: 96 },
    { id: "P-990873", flaggedOn: "2025-05-22", match: 93 },
    { id: "ID-772341", flaggedOn: "2025-08-04", match: 91 },
    { id: "P-991552", flaggedOn: "2026-01-17", match: 95 },
  ],
};

export const documentHistory = [
  { date: "2021-03-01", title: "Document Issued", detail: "Passport P123456 issued by regional passport office.", risk: "low" },
  { date: "2021-04-15", title: "First Verified", detail: "First verification at Terminal 1 on outbound travel.", risk: "low" },
  { date: "2022-09-02", title: "Checkpoint A", detail: "Routine verification at Land Border Gate A, no issues.", risk: "low" },
  { date: "2024-06-18", title: "Checkpoint B", detail: "Verification at Terminal 1, minor OCR mismatch noted.", risk: "medium" },
  { date: "2025-02-11", title: "Suspicious Activity", detail: "Related document pattern flagged in fraud network PB-2291.", risk: "high" },
  { date: "2026-09-05", title: "Current Verification", detail: "High risk score assigned, escalated to officer review.", risk: "critical" },
];

export const checkpointIntel = {
  alert: true,
  chain: [
    { name: "Terminal 3", city: "Delhi", hits: 3, lastSeen: "2026-09-05 09:12" },
    { name: "Land Border Gate B", city: "Amritsar", hits: 2, lastSeen: "2024-06-18 14:02" },
    { name: "Terminal 1", city: "Mumbai", hits: 1, lastSeen: "2023-11-02 07:40" },
  ],
  message: "Same suspicious identity cluster (PB-2291) detected across 3 checkpoints in the last 24 months.",
};

export const selfTestHistory = [
  { id: "T-3391", testType: "Photo Replacement", detected: true, confidence: 96.4, date: "2026-09-04" },
  { id: "T-3390", testType: "Font Substitution", detected: true, confidence: 91.2, date: "2026-09-04" },
  { id: "T-3389", testType: "MRZ Tampering", detected: true, confidence: 98.7, date: "2026-09-03" },
  { id: "T-3388", testType: "Hologram Spoof", detected: false, confidence: 54.1, date: "2026-09-03" },
  { id: "T-3387", testType: "Digital Re-scan Artefact", detected: true, confidence: 88.9, date: "2026-09-02" },
];

export const alerts = [
  { id: "AL-9931", severity: "critical", title: "Multiple Identity Detected", detail: "Rahul Sharma linked to archived identity Rohan Kumar (96.2% match).", time: "09:12 AM" },
  { id: "AL-9930", severity: "high", title: "Possible Document Tampering", detail: "Photo region compression mismatch on Passport P123456.", time: "09:11 AM" },
  { id: "AL-9929", severity: "critical", title: "Blacklisted Document", detail: "Passport P-664521 matches blacklist entry BL-2214.", time: "08:30 AM" },
  { id: "AL-9928", severity: "medium", title: "Expired Document", detail: "Permit PM-77120 expired on 2026-07-01.", time: "08:15 AM" },
  { id: "AL-9927", severity: "high", title: "Fraud Pattern Match", detail: "Document DNA match of 94% with cluster PB-2291.", time: "08:02 AM" },
  { id: "AL-9926", severity: "critical", title: "Cross-Checkpoint Alert", detail: "Identity cluster PB-2291 seen at 3 checkpoints in 24 months.", time: "07:48 AM" },
];

export const blockchainRecords = [
  { verId: "VER-10291", hash: "8A72C1F4E9B0...91FC", timestamp: "2026-09-05 09:12:04 UTC", result: "VERIFIED", status: "Confirmed" },
  { verId: "VER-10290", hash: "3E9A7D21B6C4...22AB", timestamp: "2026-09-05 09:05:51 UTC", result: "VERIFIED", status: "Confirmed" },
  { verId: "VER-10289", hash: "F1B4E8A2D905...77CE", timestamp: "2026-09-05 08:58:12 UTC", result: "FLAGGED", status: "Confirmed" },
  { verId: "VER-10288", hash: "0C6D2F9A11E3...45D9", timestamp: "2026-09-05 08:41:37 UTC", result: "VERIFIED", status: "Confirmed" },
];

export const officer = {
  name: "Officer Priya Nair",
  id: "OFC-20481",
  rank: "Senior Immigration Officer",
  post: "Terminal 3, Delhi International Border Control",
  email: "priya.nair@borderauth.gov",
};
