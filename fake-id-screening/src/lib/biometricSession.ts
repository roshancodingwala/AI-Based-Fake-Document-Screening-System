export interface BiometricSession {
  alignedFaceB64: string;
  confidence: number | null;
  rotationAngle: number;
  faceCount: number;
  outputWidth: number;
  outputHeight: number;
  timestamp: string;
  sourceName?: string;
}

const STORAGE_KEY = "sentry_aligned_biometric_session";

export function saveBiometricSession(session: BiometricSession): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
  } catch (err) {
    console.warn("Failed to persist biometric session:", err);
  }
}

export function getBiometricSession(): BiometricSession | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as BiometricSession;
  } catch (err) {
    console.warn("Failed to load biometric session:", err);
    return null;
  }
}

export function clearBiometricSession(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (err) {
    console.warn("Failed to clear biometric session:", err);
  }
}

/**
 * Converts a base64 JPEG string into a File object suitable for FormData uploads.
 */
export function base64ToFile(base64Data: string, filename = "aligned_face.jpg"): File {
  const byteCharacters = atob(base64Data);
  const byteArrays = new Uint8Array(byteCharacters.length);
  for (let i = 0; i < byteCharacters.length; i++) {
    byteArrays[i] = byteCharacters.charCodeAt(i);
  }
  const blob = new Blob([byteArrays], { type: "image/jpeg" });
  return new File([blob], filename, { type: "image/jpeg" });
}
