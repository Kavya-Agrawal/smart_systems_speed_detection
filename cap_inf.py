"""
cap_inf.py — Camera + ALPR inference module (imported by rpi_detector.py)
=========================================================================
Provides: init_alpr, init_vehicle_detector, grab_snapshot, run_alpr_on_frame,
          detect_vehicles, draw_annotations, save_capture, print_results
"""

import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

try:
    from fast_alpr import ALPR
except ImportError:
    print("ERROR: fast-alpr not installed. Run: pip install 'fast-alpr[onnx]'")
    sys.exit(1)

try:
    from ultralytics import YOLO
    HAS_ULTRALYTICS = True
except ImportError:
    HAS_ULTRALYTICS = False
    YOLO = None


CAPTURES_DIR = Path("captures")
LOG_FILE = Path("detections.csv")
VEHICLE_CLASSES = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def init_alpr() -> ALPR:
    print("[*] Loading ALPR models...")
    alpr = ALPR(
        detector_model="yolo-v9-t-384-license-plate-end2end",
        ocr_model="global-plates-mobile-vit-v2-model",
    )
    print("[+] ALPR models loaded.")
    return alpr


def init_vehicle_detector() -> "YOLO | None":
    if not HAS_ULTRALYTICS:
        print("[!] ultralytics not installed — vehicle filtering disabled.")
        print("    Install with: pip install ultralytics")
        return None
    print("[*] Loading YOLOv8n vehicle detector...")
    model = YOLO("yolov8n.pt")
    print("[+] Vehicle detector loaded.")
    return model


def grab_snapshot(base_url: str) -> np.ndarray | None:
    shot_url = f"{base_url}/shot.jpg"
    cap = cv2.VideoCapture(shot_url)
    ret, frame = cap.read()
    cap.release()
    return frame if ret else None


def detect_vehicles(model: YOLO, frame: np.ndarray, conf_thresh: float = 0.35) -> list[dict]:
    results = model(frame, verbose=False, conf=conf_thresh)
    vehicles = []
    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            if cls_id in VEHICLE_CLASSES:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                vehicles.append({
                    "class": VEHICLE_CLASSES[cls_id],
                    "confidence": float(box.conf[0]),
                    "bbox": (int(x1), int(y1), int(x2), int(y2)),
                })
    return vehicles


def plate_inside_vehicle(plate_bbox, vehicle_bbox, margin: float = 0.1) -> bool:
    px1, py1, px2, py2 = plate_bbox
    vx1, vy1, vx2, vy2 = vehicle_bbox
    vw, vh = vx2 - vx1, vy2 - vy1
    vx1 -= int(vw * margin)
    vy1 -= int(vh * margin)
    vx2 += int(vw * margin)
    vy2 += int(vh * margin)
    plate_cx = (px1 + px2) / 2
    plate_cy = (py1 + py2) / 2
    return vx1 <= plate_cx <= vx2 and vy1 <= plate_cy <= vy2


def run_alpr_on_frame(
    alpr: ALPR,
    vehicle_model: YOLO,
    frame: np.ndarray,
    require_vehicle: bool = True,
) -> tuple[list[dict], list[dict]]:
    """
    Returns (plate_detections, vehicle_detections).
    Each plate dict: plate, confidence, char_confidences,
    det_confidence, bbox, vehicle_class, vehicle_confidence.
    """
    vehicles = detect_vehicles(vehicle_model, frame) if (require_vehicle and vehicle_model) else []
    results = alpr.predict(frame)
    detections = []

    if results:
        for det in results:
            plate_bb = det.detection.bounding_box
            plate_bbox_tuple = (plate_bb.x1, plate_bb.y1, plate_bb.x2, plate_bb.y2)

            matched_vehicle = None
            if require_vehicle and vehicles:
                for v in vehicles:
                    if plate_inside_vehicle(plate_bbox_tuple, v["bbox"]):
                        matched_vehicle = v
                        break
                if matched_vehicle is None:
                    continue

            ocr_conf_raw, ocr_conf_avg = [], 0.0
            if det.ocr and det.ocr.confidence:
                conf = det.ocr.confidence
                if isinstance(conf, list):
                    ocr_conf_raw = [round(c * 100, 1) for c in conf]
                    ocr_conf_avg = round(sum(conf) / len(conf) * 100, 1) if conf else 0.0
                else:
                    ocr_conf_raw = [round(float(conf) * 100, 1)]
                    ocr_conf_avg = round(float(conf) * 100, 1)

            det_conf = det.detection.confidence
            if isinstance(det_conf, list):
                det_conf = sum(det_conf) / len(det_conf) if det_conf else 0.0
            det_conf = round(float(det_conf) * 100, 1)

            detections.append({
                "plate": det.ocr.text if det.ocr else "???",
                "confidence": ocr_conf_avg,
                "char_confidences": ocr_conf_raw,
                "det_confidence": det_conf,
                "bbox": plate_bbox_tuple,
                "vehicle_class": matched_vehicle["class"] if matched_vehicle else "unknown",
                "vehicle_confidence": round(matched_vehicle["confidence"] * 100, 1) if matched_vehicle else 0.0,
            })

    return detections, vehicles


def draw_annotations(frame, detections, vehicles=None):
    annotated = frame.copy()
    if vehicles:
        for v in vehicles:
            vx1, vy1, vx2, vy2 = v["bbox"]
            cv2.rectangle(annotated, (vx1, vy1), (vx2, vy2), (255, 180, 0), 1)
            cv2.putText(annotated, f"{v['class']} {v['confidence']*100:.0f}%",
                        (vx1, vy1 - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 180, 0), 1)
    for det in detections:
        px1, py1, px2, py2 = det["bbox"]
        cv2.rectangle(annotated, (px1, py1), (px2, py2), (36, 255, 12), 2)
        label = f"{det['plate']} {det['confidence']:.0f}%"
        cv2.putText(annotated, label, (px1, py1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(annotated, label, (px1, py1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    return annotated


def save_capture(frame, detections, annotated):
    CAPTURES_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = CAPTURES_DIR / f"{timestamp}_raw.jpg"
    ann_path = CAPTURES_DIR / f"{timestamp}_annotated.jpg"
    cv2.imwrite(str(raw_path), frame)
    cv2.imwrite(str(ann_path), annotated)

    write_header = not LOG_FILE.exists()
    with open(LOG_FILE, "a") as f:
        if write_header:
            f.write("timestamp,plate,ocr_confidence_avg,char_confidences,"
                    "det_confidence,vehicle_class,vehicle_confidence,image\n")
        for det in detections:
            char_conf_str = "|".join(str(c) for c in det["char_confidences"])
            f.write(f"{timestamp},{det['plate']},{det['confidence']},"
                    f"{char_conf_str},{det['det_confidence']},"
                    f"{det['vehicle_class']},{det['vehicle_confidence']},"
                    f"{raw_path.name}\n")
    return raw_path, ann_path


def print_results(detections):
    if not detections:
        print("    No license plates detected (on vehicles).")
        return
    for i, det in enumerate(detections, 1):
        print(f"    Plate #{i}: {det['plate']}")
        print(f"      OCR conf (avg)  : {det['confidence']}%")
        print(f"      Per-char conf   : {det['char_confidences']}")
        print(f"      Det conf        : {det['det_confidence']}%")
        print(f"      Vehicle         : {det['vehicle_class']} ({det['vehicle_confidence']}%)")