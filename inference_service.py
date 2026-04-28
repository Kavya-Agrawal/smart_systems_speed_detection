"""
inference_service.py — VIGIL Inference Relay
=============================================
Flask service that sits between rpi_detector.py and vigil_server.py.

Receives trigger from RPi (speed + lane info + camera URL):
  1. Captures image from phone camera (IP Webcam)
  2. Runs vehicle detection + ALPR
  3. Checks for false positives (no vehicle / no plate)
  4. If valid, forwards detection data + image to vigil_server.py

Runs on a machine with enough compute for ML (laptop, desktop, etc).

Usage:
    python inference_service.py
    python inference_service.py --port 5001 --server http://localhost:5000
    python inference_service.py --no-vehicle-filter

Endpoints:
    POST /api/trigger   — receives trigger from RPi
    GET  /              — health check
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
import cv2

from flask import Flask, request, jsonify
import requests as http_requests

from cap_inf import (
    init_alpr,
    init_vehicle_detector,
    grab_snapshot,
    run_alpr_on_frame,
    draw_annotations,
    save_capture,
    print_results,
)


# ── Tunable parameters ────────────────────────────────────────────────
VIGIL_SERVER_URL = "http://localhost:5000"   # vigil_server.py address
NO_VEHICLE_FILTER = False

CAPTURES_DIR = Path("inference_captures")


# ── Globals (initialized in main) ────────────────────────────────────
alpr = None
vehicle_model = None
require_vehicle = True

app = Flask(__name__)


# ── Core inference logic ──────────────────────────────────────────────

def capture_and_infer(camera_url: str) -> tuple:
    """
    Capture image from phone camera, run ALPR with vehicle filtering.
    Returns (frame, detections, vehicles) or (None, [], []).
    """
    print("[*] Capturing snapshot from camera...")
    frame = grab_snapshot(camera_url)
    if frame is None:
        print("[!] Failed to grab snapshot from camera.")
        return None, [], []

    print(f"[*] Frame size: {frame.shape[1]}x{frame.shape[0]}")
    print("[*] Running vehicle detection + ALPR...")
    t0 = time.perf_counter()
    detections, vehicles = run_alpr_on_frame(
        alpr, vehicle_model, frame, require_vehicle=require_vehicle,
    )
    elapsed = (time.perf_counter() - t0) * 1000
    print(f"[+] Inference done in {elapsed:.0f} ms")
    print_results(detections)

    return frame, detections, vehicles


def forward_to_server(
    entry_area: str,
    exit_area: str,
    speed_kmph: float,
    nameplate: str,
    char_confidences: list[float],
    image_path: str,
    server_url: str,
) -> dict | None:
    """Forward the complete detection to vigil_server.py."""
    url = f"{server_url}/api/detection"
    data = {
        "entry_area": entry_area,
        "exit_area": exit_area,
        "speed": speed_kmph,
        "nameplate": nameplate,
        "char_confidences": json.dumps(char_confidences),
    }
    try:
        with open(image_path, "rb") as img_file:
            files = {"image": (os.path.basename(image_path), img_file, "image/jpeg")}
            resp = http_requests.post(url, data=data, files=files, timeout=10)
        if resp.status_code == 200:
            result = resp.json()
            print(f"[+] VIGIL server: {result.get('message', 'OK')}")
            return result
        else:
            print(f"[!] VIGIL server returned {resp.status_code}: {resp.text}")
    except http_requests.ConnectionError:
        print(f"[!] Could not connect to VIGIL server at {server_url}")
    except Exception as e:
        print(f"[!] Error forwarding to server: {e}")
    return None


# ── Flask endpoint ────────────────────────────────────────────────────

@app.route("/api/trigger", methods=["POST"])
def handle_trigger():
    """
    Receive a trigger from rpi_detector.py.

    JSON body:
        lane_id, camera_url, entry_area, exit_area, speed (float), facing (int)
    """
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    lane_id = data.get("lane_id", "?")
    camera_url = data.get("camera_url", "")
    entry_area = data.get("entry_area", "")
    exit_area = data.get("exit_area", "")
    speed = float(data.get("speed", 0))
    facing = int(data.get("facing", 0))

    now = datetime.now().strftime("%H:%M:%S")
    print(f"\n{'='*55}")
    print(f"[>] Trigger from RPi at {now}")
    print(f"    Lane       : {lane_id}")
    print(f"    Camera     : {camera_url}")
    print(f"    Speed      : {speed:.1f} km/h")
    print(f"    Entry area : {entry_area}")
    print(f"    Exit area  : {exit_area}")
    print(f"    Facing     : {'front' if facing == 1 else 'back'}")

    # ── Step 1: Capture + ALPR ──
    frame, detections, vehicles = capture_and_infer(camera_url)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    cv2.imwrite(str(CAPTURES_DIR / f"{timestamp}_RAW.jpg"), frame)

    if frame is None:
        msg = f"{lane_id}: Camera capture failed"
        print(f"[!] {msg}")
        print(f"{'='*55}\n")
        return jsonify({"status": "error", "message": msg}), 200

    if not detections:
        msg = f"{lane_id}: No valid plate detected (false positive or no vehicle)"
        print(f"[!] {msg}")
        print(f"{'='*55}\n")
        return jsonify({"status": "skipped", "message": msg}), 200

    # ── Step 2: Save capture locally ──
    best = detections[0]
    annotated = draw_annotations(frame, detections, vehicles)

    CAPTURES_DIR.mkdir(exist_ok=True)
    raw_path = CAPTURES_DIR / f"{timestamp}_{best['plate']}_raw.jpg"
    ann_path = CAPTURES_DIR / f"{timestamp}_{best['plate']}_annotated.jpg"

    
    cv2.imwrite(str(raw_path), frame)
    cv2.imwrite(str(ann_path), annotated)
    print(f"    Saved: {raw_path}")

    # ── Step 3: Forward to VIGIL server ──
    print(f"[*] Forwarding to VIGIL server: {best['plate']} @ {speed:.1f} km/h")
    result = forward_to_server(
        entry_area=entry_area,
        exit_area=exit_area,
        speed_kmph=speed,
        nameplate=best["plate"],
        char_confidences=best["char_confidences"],
        image_path=str(raw_path),
        server_url=app.config["VIGIL_SERVER_URL"],
    )

    msg = f"{lane_id}: Processed {best['plate']}"
    print(f"[+] {msg}")
    print(f"{'='*55}\n")

    return jsonify({
        "status": "ok",
        "message": msg,
        "plate": best["plate"],
        "confidence": best["confidence"],
        "speed": speed,
        "server_result": result,
    }), 200


@app.route("/", methods=["GET"])
def index():
    return (
        "<h2>VIGIL Inference Service Running</h2>"
        f"<p>Vehicle filter: {'ON' if require_vehicle else 'OFF'}</p>"
        f"<p>Forwarding to: {app.config['VIGIL_SERVER_URL']}</p>"
    )


# ── Entry point ───────────────────────────────────────────────────────

def main():
    global alpr, vehicle_model, require_vehicle

    parser = argparse.ArgumentParser(description="VIGIL Inference Service")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=5001, help="Port (default 5001)")
    parser.add_argument("--server", default=VIGIL_SERVER_URL,
                        help="VIGIL server URL (default http://localhost:5000)")
    parser.add_argument("--no-vehicle-filter", action="store_true",
                        help="Disable vehicle bbox filtering")
    args = parser.parse_args()

    app.config["VIGIL_SERVER_URL"] = args.server
    no_filter = args.no_vehicle_filter or NO_VEHICLE_FILTER

    print("=" * 55)
    print("  VIGIL — Inference Service")
    print(f"  Listening on : {args.host}:{args.port}")
    print(f"  VIGIL server : {args.server}")
    print(f"  Vehicle filter: {'OFF' if no_filter else 'ON'}")
    print("=" * 55)

    # Load models
    alpr = init_alpr()
    if not no_filter:
        vehicle_model = init_vehicle_detector()
    else:
        vehicle_model = None

    if vehicle_model is None and not no_filter:
        print("[!] Vehicle filter requested but unavailable. Running unfiltered.")
    require_vehicle = (vehicle_model is not None) and (not no_filter)

    print(f"\n[+] Inference service ready. Waiting for triggers.\n")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
