"""
rpi_detector.py — VIGIL RPi Lane Detection Script
===================================================
Monitors lane pressure sensors (buttons for now) on GPIO pins.
When a vehicle crosses a lane:
  1. First sensor triggers → camera captures frame → ALPR runs
  2. Second sensor triggers → speed calculated from time differential
  3. Detection packet sent to vigil_server.py

Phone camera setup (IP Webcam over USB tethering):
  1. Install "IP Webcam" app on phone (Play Store, by Pavel Khlebovich)
  2. Open app → set resolution 1920x1080, focus mode "continuous video"
  3. Tap "Start server" at bottom
  4. Connect phone to RPi via USB cable
  5. On phone: Settings → Hotspot & Tethering → USB Tethering → ON
  6. On RPi: run `ip addr show usb0` — phone is typically at 192.168.42.129
  7. Test: open http://192.168.42.129:8080 in browser on RPi
  8. Set CAMERA_URL below to that address

Usage:
    python rpi_detector.py
"""

import json
import time
from datetime import datetime

import requests
import RPi.GPIO as GPIO

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
SERVER_URL = "http://localhost:5000"       # vigil_server.py address
CAMERA_URL = "http://192.168.42.129:8080" # IP Webcam base URL
SENSOR_DISTANCE = 2.0       # metres between first and second sensor in a lane
IDLE_TIMEOUT = 5.0           # max seconds to wait for second sensor after first
K = 3                        # consecutive HIGH reads to confirm a press
SAMPLE_DT = 0.05             # seconds between GPIO samples
WARMUP = 5                   # GPIO stabilization time in seconds
NO_VEHICLE_FILTER = False    # set True to skip vehicle bbox check


# ── Lane configuration ────────────────────────────────────────────────
# Each lane defines:
#   lane_id      — unique identifier
#   pin_first    — GPIO pin (BOARD) for the first (upstream) sensor
#   pin_second   — GPIO pin (BOARD) for the second (downstream) sensor
#   camera_url   — IP Webcam URL for the camera covering this lane
#   facing       — 0 = camera sees car's back plate, 1 = front plate
#   entry_area   — the area the car enters when crossing this lane
#   exit_area    — the area the car exits (leaves behind)
#                  use "OUT" for outside the monitored network

LANES = [
    {
        "lane_id": "L1",
        "pin_first": 11,
        "pin_second": 13,
        "camera_url": CAMERA_URL,
        "facing": 0,
        "entry_area": "A",
        "exit_area": "OUT",
    },
    # Add more lanes as needed:
    # {
    #     "lane_id": "L2",
    #     "pin_first": 15,
    #     "pin_second": 16,
    #     "camera_url": CAMERA_URL,
    #     "facing": 0,
    #     "entry_area": "B",
    #     "exit_area": "A",
    # },
]


# ── GPIO setup ────────────────────────────────────────────────────────
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)
for lane in LANES:
    GPIO.setup(lane["pin_first"], GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(lane["pin_second"], GPIO.IN, pull_up_down=GPIO.PUD_DOWN)


# ── Helpers ───────────────────────────────────────────────────────────


def confirmed_high(pin: int, k: int = K, dt: float = SAMPLE_DT) -> bool:
    """Require k consecutive HIGH reads to debounce."""
    streak = 0
    while streak < k:
        if GPIO.input(pin) == 1:
            streak += 1
        else:
            return False
        time.sleep(dt)
    return True


def wait_until_low(pin: int, dt: float = SAMPLE_DT):
    """Block until pin goes LOW (button released)."""
    while GPIO.input(pin) == 1:
        time.sleep(dt)


def capture_and_detect(alpr, vehicle_model, camera_url: str, require_vehicle: bool = True):
    """
    Trigger camera snapshot, run ALPR with vehicle filter.
    Returns (frame, detections, vehicles) or (None, [], []) on failure.
    """
    print("[*] Capturing snapshot...")
    frame = grab_snapshot(camera_url)
    if frame is None:
        print("[!] Failed to grab snapshot.")
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


def send_to_server(
    entry_area: str,
    exit_area: str,
    speed_kmph: float,
    nameplate: str,
    char_confidences: list[float],
    image_path: str,
):
    """POST detection data + image to vigil_server.py."""
    url = f"{SERVER_URL}/api/detection"
    data = {
        "entry_area": entry_area,
        "exit_area": exit_area,
        "speed": speed_kmph,
        "nameplate": nameplate,
        "char_confidences": json.dumps(char_confidences),
    }
    try:
        with open(image_path, "rb") as img_file:
            files = {"image": (str(image_path), img_file, "image/jpeg")}
            resp = requests.post(url, data=data, files=files, timeout=10)
        if resp.status_code == 200:
            result = resp.json()
            print(f"[+] Server response: {result.get('message', 'OK')}")
            return result
        else:
            print(f"[!] Server returned {resp.status_code}: {resp.text}")
    except requests.ConnectionError:
        print(f"[!] Could not connect to server at {SERVER_URL}")
    except Exception as e:
        print(f"[!] Error sending to server: {e}")
    return None


# ── Main loop ─────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("  VIGIL — RPi Lane Detector")
    print(f"  Server        : {SERVER_URL}")
    print(f"  Camera        : {CAMERA_URL}")
    print(f"  Vehicle filter: {'ON' if require_vehicle else 'OFF'}")
    print(f"  Lanes         : {[l['lane_id'] for l in LANES]}")
    print("=" * 60)

    alpr = init_alpr()
    vehicle_model = init_vehicle_detector() if not NO_VEHICLE_FILTER else None
    if vehicle_model is None and not NO_VEHICLE_FILTER:
        print("[!] Vehicle filter requested but detector unavailable. Running unfiltered.")
    require_vehicle = (vehicle_model is not None) and (not NO_VEHICLE_FILTER)

    print(f"\n[*] GPIO stabilizing for {WARMUP}s...")
    time.sleep(WARMUP)
    print("[+] System ready. PASSIVE: waiting for lane triggers.\n")

    try:
        while True:
            for lane in LANES:
                lid = lane["lane_id"]
                pin1 = lane["pin_first"]
                pin2 = lane["pin_second"]

                # ── Check for reverse traffic (second sensor fires first) ──
                if GPIO.input(pin2) == 1:
                    if confirmed_high(pin2):
                        print(f"[!] {lid}: Reverse traffic (sensor2 before sensor1). Discarding.")
                        wait_until_low(pin2)
                    continue

                # ── First sensor triggered ──
                if GPIO.input(pin1) != 1:
                    continue
                if not confirmed_high(pin1):
                    continue

                t1 = time.time()
                ts1 = datetime.fromtimestamp(t1).strftime("%H:%M:%S.%f")[:-3]
                print(f"\n[*] {lid}: Sensor1 confirmed at {ts1}")

                # ── Camera capture + ALPR ──
                frame, detections, vehicles = capture_and_detect(
                    alpr, vehicle_model, lane["camera_url"], require_vehicle,
                )

                if frame is None or not detections:
                    print(f"[!] {lid}: No valid plate detected. Discarding event.")
                    wait_until_low(pin1)
                    continue

                # Save annotated image
                annotated = draw_annotations(frame, detections, vehicles)
                raw_path, _ = save_capture(frame, detections, annotated)

                best = detections[0]  # take highest-confidence plate
                print(f"[*] {lid}: Plate = {best['plate']}, waiting for sensor2 (up to {IDLE_TIMEOUT}s)...")

                # ── Wait for second sensor ──
                sensor2_hit = False
                while time.time() - t1 <= IDLE_TIMEOUT:
                    if GPIO.input(pin2) == 1 and confirmed_high(pin2):
                        t2 = time.time()
                        dt = t2 - t1
                        speed_mps = SENSOR_DISTANCE / dt if dt > 0 else 0.0
                        speed_kmph = speed_mps * 3.6

                        ts2 = datetime.fromtimestamp(t2).strftime("%H:%M:%S.%f")[:-3]
                        print(f"[+] {lid}: VALID EVENT")
                        print(f"    Plate          : {best['plate']}")
                        print(f"    Sensor1        : {ts1}")
                        print(f"    Sensor2        : {ts2}")
                        print(f"    Δt             : {dt:.3f} s")
                        print(f"    Speed          : {speed_mps:.2f} m/s  ({speed_kmph:.1f} km/h)")
                        print(f"    Entry area     : {lane['entry_area']}")
                        print(f"    Exit area      : {lane['exit_area']}")

                        # ── Send to server ──
                        send_to_server(
                            entry_area=lane["entry_area"],
                            exit_area=lane["exit_area"],
                            speed_kmph=speed_kmph,
                            nameplate=best["plate"],
                            char_confidences=best["char_confidences"],
                            image_path=str(raw_path),
                        )

                        sensor2_hit = True
                        break

                    time.sleep(SAMPLE_DT)

                if not sensor2_hit:
                    print(f"[!] {lid}: Sensor2 timeout ({IDLE_TIMEOUT}s). Discarding event.")

                # Wait for both sensors to go LOW before resuming
                wait_until_low(pin1)
                wait_until_low(pin2)
                print()

            time.sleep(SAMPLE_DT)

    except KeyboardInterrupt:
        print("\n[*] Shutting down...")
    finally:
        GPIO.cleanup()
        print("[*] GPIO cleaned up. VIGIL RPi detector stopped.")


if __name__ == "__main__":
    main()
