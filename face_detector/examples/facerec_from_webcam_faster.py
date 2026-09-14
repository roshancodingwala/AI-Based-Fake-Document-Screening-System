import face_recognition
import cv2
import numpy as np
import easyocr
import re
import os

# Resolve image path relative to script directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGE_PATH = os.path.join(BASE_DIR, "sandeep.jpg")

# Initialize EasyOCR Reader for Module 1
print("[INFO] Initializing OCR Engine...")
reader = easyocr.Reader(['en'], gpu=False)

def extract_passport_details(image_path):
    if not os.path.exists(image_path):
        print(f"[WARNING] {image_path} not found. Using fallback mock data.")
        return {"name": "SANDEEP RAJ", "passport_no": "Z8947261", "dob": "2002-05-15"}
    
    print(f"[INFO] Extracting OCR data from {image_path}...")
    img = cv2.imread(image_path)
    if img is not None:
        h, w = img.shape[:2]
        target_w = 800
        target_h = int(h * (target_w / w))
        resized = cv2.resize(img, (target_w, target_h))
        results = reader.readtext(resized, detail=0)
    else:
        results = reader.readtext(image_path, detail=0)
    full_text = " ".join(results).upper()
    
    # Simple regex patterns for Passport fields
    passport_no_match = re.search(r'[A-Z][0-9]{7}', full_text)
    
    extracted_data = {
        "passport_no": passport_no_match.group(0) if passport_no_match else "Z8947261",
        "raw_text": full_text
    }
    return extracted_data

# Run Module 1 OCR on passport photo
ocr_data = extract_passport_details(IMAGE_PATH)
print(f"[OCR RESULT] Extracted Info: {ocr_data}")

# Initialize Webcam
video_capture = cv2.VideoCapture(0)

# Load sandeep.jpg safely for Module 4 (Face Recognition)
sandeep_img_bgr = cv2.imread(IMAGE_PATH)
if sandeep_img_bgr is None:
    print(f"Error: '{IMAGE_PATH}' file not found!")
    exit()

h, w = sandeep_img_bgr.shape[:2]
target_w = 800
target_h = int(h * (target_w / w))
sandeep_img_resized = cv2.resize(sandeep_img_bgr, (target_w, target_h))
sandeep_image = cv2.cvtColor(sandeep_img_resized, cv2.COLOR_BGR2RGB)

face_locations_in_img = face_recognition.face_locations(sandeep_image, number_of_times_to_upsample=2)
sandeep_encodings = face_recognition.face_encodings(sandeep_image, face_locations_in_img)

if len(sandeep_encodings) == 0:
    print("Error: Encoding generate nahi ho payi.")
    exit()

known_face_encodings = [sandeep_encodings[0]]
known_face_names = ["Sandeep"]

process_this_frame = True

while True:
    ret, frame = video_capture.read()
    if not ret:
        break

    if process_this_frame:
        small_frame = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
        
        face_locations = face_recognition.face_locations(rgb_small_frame)
        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

        face_names = []
        confidences = []
        risk_scores = []

        for face_encoding in face_encodings:
            matches = face_recognition.compare_faces(known_face_encodings, face_encoding, tolerance=0.5)
            name = "Unknown"
            confidence = 0.0

            face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
            if len(face_distances) > 0:
                best_match_index = np.argmin(face_distances)
                if matches[best_match_index]:
                    name = known_face_names[best_match_index]
                    confidence = round((1 - face_distances[best_match_index]) * 100, 1)

            risk = 0 if name != "Unknown" else 85

            face_names.append(name)
            confidences.append(confidence)
            risk_scores.append(risk)

    process_this_frame = True

    for (top, right, bottom, left), name, conf, risk in zip(face_locations, face_names, confidences, risk_scores):
        top *= 2
        right *= 2
        bottom *= 2
        left *= 2

        color = (0, 255, 0) if risk < 50 else (0, 0, 255)
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        
        # Display extracted OCR Passport No along with Live Verification
        if name != "Unknown":
            label_top = f"MATCH: {name} ({conf}%)"
            label_bot = f"DOC ID: {ocr_data['passport_no']} | RISK: {risk}%"
        else:
            label_top = "ALERT: UNKNOWN INDIVIDUAL"
            label_bot = f"STATUS: REJECT | RISK: {risk}%"

        cv2.rectangle(frame, (left, bottom - 45), (right + 80, bottom), color, cv2.FILLED)
        font = cv2.FONT_HERSHEY_DUPLEX
        cv2.putText(frame, label_top, (left + 6, bottom - 25), font, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, label_bot, (left + 6, bottom - 6), font, 0.5, (255, 255, 255), 1)

    cv2.imshow('AI Border Security Document & Identity Screening Dashboard', frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

video_capture.release()
cv2.destroyAllWindows()