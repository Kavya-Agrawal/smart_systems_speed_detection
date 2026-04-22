"""
vigil_server.py — VIGIL Central Server
========================================
Flask server that receives detection packets from rpi_detector.py and
maintains all databases, traffic stats, notifications, and parked timers.

Usage:
    pip install flask
    python vigil_server.py                     # runs on 0.0.0.0:5000
    python vigil_server.py --port 8000         # custom port
    python vigil_server.py --host 127.0.0.1    # localhost only

Database: SQLite (vigil.db), auto-created on first run.
Uploaded images stored in: ./server_images/
"""

import argparse
import json
import os
import random
import shutil
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify


# ── Tunable parameters ────────────────────────────────────────────────
CHAR_CONFIDENCE_THRESHOLD = 40.0   # percent; below this → wildcard
SPEED_LIMIT_KMPH = 35.0            # km/h; above this → violation
PARKED_TIMEOUT_SECONDS = 45       # .75 minutes

DB_PATH = "vigil.db"
IMAGE_DIR = Path("server_images")

# ── Area adjacency graph ──────────────────────────────────────────────
# Undirected: if A is adjacent to B, then B is adjacent to A.
# "OUT" represents outside the monitored campus network.
# OUT - A - B - C - OUT
AREA_ADJACENCY = {
    "A":   {"B", "OUT"},
    "B":   {"A", "C"},
    "C":   {"B", "OUT"},
    "OUT": {"A", "C"},
}


def areas_adjacent(a: str, b: str) -> bool:
    """Check if two areas are adjacent in the graph."""
    if a == b:
        return True
    return b in AREA_ADJACENCY.get(a, set())


# ── Database ──────────────────────────────────────────────────────────

def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS nameplates (
            nameplate       TEXT PRIMARY KEY,
            registered      INTEGER DEFAULT 0,
            parked          INTEGER DEFAULT 0,
            last_area       TEXT DEFAULT 'OUT',
            owner           TEXT DEFAULT '',
            owner_phone     TEXT DEFAULT '',
            violations      INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS notifications (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            nameplate       TEXT NOT NULL,
            area            TEXT NOT NULL,
            time            TEXT NOT NULL,
            speed           REAL NOT NULL,
            owner           TEXT DEFAULT '',
            owner_phone     TEXT DEFAULT '',
            image_path      TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS traffic_stats (
            area            TEXT PRIMARY KEY,
            active_vehicles INTEGER DEFAULT 0,
            avg_speed       REAL DEFAULT 0.0,
            speed_observations INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS traffic_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            area            TEXT NOT NULL,
            nameplate       TEXT NOT NULL,
            status          TEXT NOT NULL,
            time            TEXT NOT NULL
        );
    """)

    # Ensure all areas in adjacency graph have a traffic_stats row
    for area in AREA_ADJACENCY:
        if area != "OUT":
            conn.execute(
                "INSERT OR IGNORE INTO traffic_stats (area) VALUES (?)", (area,)
            )
    conn.commit()
    conn.close()
    print(f"[+] Database initialized: {DB_PATH}")


# ── Parked timers ─────────────────────────────────────────────────────
# Dict of nameplate -> threading.Timer
# When a vehicle is detected, its timer resets to PARKED_TIMEOUT_SECONDS.
# If the timer fires, the vehicle is marked as parked.

_parked_timers: dict[str, threading.Timer] = {}
_timer_lock = threading.Lock()


def _on_parked_timer(nameplate: str):
    """Called when a vehicle's parked timer expires."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT last_area FROM nameplates WHERE nameplate = ?", (nameplate,)
        ).fetchone()
        if row is None:
            return
        last_area = row["last_area"]

        # Mark as parked
        conn.execute(
            "UPDATE nameplates SET parked = 1 WHERE nameplate = ?", (nameplate,)
        )

        # Decrement active vehicles in last_area (if not OUT)
        if last_area != "OUT":
            conn.execute(
                "UPDATE traffic_stats SET active_vehicles = MAX(active_vehicles - 1, 0) "
                "WHERE area = ?", (last_area,)
            )

        # Traffic log entry
        conn.execute(
            "INSERT INTO traffic_log (area, nameplate, status, time) VALUES (?, ?, 'parked', ?)",
            (last_area, nameplate, now),
        )
        conn.commit()
        print(f"[T] Parked timer fired: {nameplate} in area {last_area}")
    finally:
        conn.close()

    with _timer_lock:
        _parked_timers.pop(nameplate, None)


def reset_parked_timer(nameplate: str):
    """Cancel existing timer and start a new one."""
    with _timer_lock:
        old = _parked_timers.pop(nameplate, None)
        if old is not None:
            old.cancel()

        t = threading.Timer(PARKED_TIMEOUT_SECONDS, _on_parked_timer, args=[nameplate])
        t.daemon = True
        t.start()
        _parked_timers[nameplate] = t


# ── Nameplate matching ────────────────────────────────────────────────

def match_nameplate(
    raw_plate: str,
    char_confidences: list[float],
    exit_area: str,
) -> str:
    """
    Fuzzy-match a detected nameplate against the database.

    1. Replace low-confidence characters with wildcard '_'
    2. Search database with SQL LIKE
    3. Filter by adjacency (candidate's last_area must be adjacent to exit_area)
    4. If multiple matches: pick one at random
    5. If no matches: return the original raw_plate (treated as new)
    """
    # Build wildcard pattern
    pattern_chars = list(raw_plate)
    for i, ch in enumerate(pattern_chars):
        if i < len(char_confidences) and char_confidences[i] < CHAR_CONFIDENCE_THRESHOLD:
            pattern_chars[i] = "_"
    pattern = "".join(pattern_chars)

    has_wildcards = "_" in pattern

    if not has_wildcards:
        # Exact match — no need for fuzzy search
        return raw_plate

    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT nameplate, last_area FROM nameplates WHERE nameplate LIKE ?",
            (pattern,),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return raw_plate

    # Filter by adjacency: candidate's last_area must be adjacent to exit_area
    candidates = []
    for row in rows:
        if areas_adjacent(row["last_area"], exit_area):
            candidates.append(row["nameplate"])

    if not candidates:
        return raw_plate

    return random.choice(candidates)


# ── Flask app ─────────────────────────────────────────────────────────

app = Flask(__name__)


@app.route("/api/detection", methods=["POST"])
def handle_detection():
    """
    Receive a detection packet from rpi_detector.py.

    Form fields:
        entry_area, exit_area, speed (float, km/h),
        nameplate (str), char_confidences (JSON list of floats)
    File:
        image (JPEG)
    """
    entry_area = request.form.get("entry_area", "")
    exit_area = request.form.get("exit_area", "")
    speed = float(request.form.get("speed", 0))
    raw_nameplate = request.form.get("nameplate", "")
    char_conf_json = request.form.get("char_confidences", "[]")
    char_confidences = json.loads(char_conf_json)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Save uploaded image
    image_path = ""
    if "image" in request.files:
        IMAGE_DIR.mkdir(exist_ok=True)
        img = request.files["image"]
        fname = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{raw_nameplate}.jpg"
        image_path = str(IMAGE_DIR / fname)
        img.save(image_path)

    print(f"\n{'='*55}")
    print(f"[>] Detection received at {now}")
    print(f"    Raw plate       : {raw_nameplate}")
    print(f"    Char confidences: {char_confidences}")
    print(f"    Speed           : {speed:.1f} km/h")
    print(f"    Entry area      : {entry_area}")
    print(f"    Exit area       : {exit_area}")

    # ── Step 1: Nameplate matching ──
    nameplate = match_nameplate(raw_nameplate, char_confidences, exit_area)
    is_new = False

    conn = get_db()
    try:
        existing = conn.execute(
            "SELECT * FROM nameplates WHERE nameplate = ?", (nameplate,)
        ).fetchone()

        if existing is None:
            # New nameplate — insert as unregistered
            is_new = True
            conn.execute(
                "INSERT INTO nameplates (nameplate, registered, parked, last_area) "
                "VALUES (?, 0, 0, ?)",
                (nameplate, entry_area),
            )
            print(f"    Matched plate   : {nameplate} (NEW — unregistered)")
        else:
            print(f"    Matched plate   : {nameplate} (existing)")

        # ── Step 2: Reset parked timer ──
        conn.execute(
            "UPDATE nameplates SET parked = 0 WHERE nameplate = ?", (nameplate,)
        )

        # ── Step 3: Update traffic stats ──

        # Exit area: -1 active vehicle (unless OUT)
        if exit_area != "OUT":
            conn.execute(
                "UPDATE traffic_stats SET active_vehicles = MAX(active_vehicles - 1, 0) "
                "WHERE area = ?", (exit_area,)
            )

        # Entry area: +1 active vehicle, update avg speed (unless OUT)
        if entry_area != "OUT":
            row = conn.execute(
                "SELECT avg_speed, speed_observations FROM traffic_stats WHERE area = ?",
                (entry_area,),
            ).fetchone()
            if row:
                old_avg = row["avg_speed"]
                n = row["speed_observations"]
                new_avg = (old_avg * n + speed) / (n + 1)
                conn.execute(
                    "UPDATE traffic_stats SET "
                    "active_vehicles = active_vehicles + 1, "
                    "avg_speed = ?, speed_observations = ? "
                    "WHERE area = ?",
                    (round(new_avg, 2), n + 1, entry_area),
                )
            else:
                # Area not in traffic_stats yet (shouldn't happen after init)
                conn.execute(
                    "INSERT INTO traffic_stats (area, active_vehicles, avg_speed, speed_observations) "
                    "VALUES (?, 1, ?, 1)",
                    (entry_area, speed),
                )

        # ── Step 4: Traffic log (always, even for OUT) ──
        conn.execute(
            "INSERT INTO traffic_log (area, nameplate, status, time) VALUES (?, ?, 'exit', ?)",
            (exit_area, nameplate, now),
        )
        conn.execute(
            "INSERT INTO traffic_log (area, nameplate, status, time) VALUES (?, ?, 'entry', ?)",
            (entry_area, nameplate, now),
        )

        # ── Step 5: Speed violation check ──
        is_violation = speed > SPEED_LIMIT_KMPH
        if is_violation:
            conn.execute(
                "UPDATE nameplates SET violations = violations + 1 WHERE nameplate = ?",
                (nameplate,),
            )

            # Fetch owner info for notification
            veh = conn.execute(
                "SELECT owner, owner_phone FROM nameplates WHERE nameplate = ?",
                (nameplate,),
            ).fetchone()

            conn.execute(
                "INSERT INTO notifications (nameplate, area, time, speed, owner, owner_phone, image_path) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (nameplate, entry_area, now, speed,
                 veh["owner"] if veh else "", veh["owner_phone"] if veh else "",
                 image_path),
            )
            print(f"    *** SPEED VIOLATION: {speed:.1f} km/h > {SPEED_LIMIT_KMPH} km/h ***")

        # ── Step 6: Update nameplate's last_area ──
        conn.execute(
            "UPDATE nameplates SET last_area = ? WHERE nameplate = ?",
            (entry_area, nameplate),
        )

        conn.commit()
    finally:
        conn.close()

    # ── Step 7: Reset parked timer ──
    reset_parked_timer(nameplate)

    result = {
        "status": "ok",
        "message": f"Processed plate {nameplate}",
        "matched_plate": nameplate,
        "is_new": is_new,
        "is_violation": is_violation if 'is_violation' in dir() else False,
        "speed": speed,
        "entry_area": entry_area,
        "exit_area": exit_area,
    }
    print(f"    Result          : {result['message']}")
    print(f"{'='*55}\n")
    return jsonify(result), 200


# ── Status / debug endpoints ─────────────────────────────────────────

@app.route("/api/stats", methods=["GET"])
def get_stats():
    """Return all traffic stats."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM traffic_stats").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/nameplates", methods=["GET"])
def get_nameplates():
    """Return all nameplates in the database."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM nameplates").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/notifications", methods=["GET"])
def get_notifications():
    """Return all speed violation notifications."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM notifications ORDER BY id DESC LIMIT 50"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/log", methods=["GET"])
def get_log():
    """Return recent traffic log entries."""
    limit = request.args.get("limit", 100, type=int)
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM traffic_log ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/timers", methods=["GET"])
def get_timers():
    """Return currently active parked timers (for debugging)."""
    with _timer_lock:
        active = list(_parked_timers.keys())
    return jsonify({"active_parked_timers": active, "timeout_seconds": PARKED_TIMEOUT_SECONDS})


@app.route("/", methods=["GET"])
def index():
    return (
        "<h2>VIGIL Server Running</h2>"
        "<p>Endpoints: "
        "<a href='/api/stats'>/api/stats</a> | "
        "<a href='/api/nameplates'>/api/nameplates</a> | "
        "<a href='/api/notifications'>/api/notifications</a> | "
        "<a href='/api/log'>/api/log</a> | "
        "<a href='/api/timers'>/api/timers</a>"
        "</p>"
    )


# ── Pre-populate some test data (optional) ────────────────────────────

def seed_test_data():
    """Insert some test registered vehicles. Call manually or on first run."""
    conn = get_db()
    test_vehicles = [
        ("AS01AB1234", 1, "A", "Test Owner 1", "9876543210"),
        ("AS09XY5678", 1, "B", "Test Owner 2", "9876543211"),
        ("NL07Z0042",  1, "C", "Test Owner 3", "9876543212"),
    ]
    for plate, reg, area, owner, phone in test_vehicles:
        conn.execute(
            "INSERT OR IGNORE INTO nameplates "
            "(nameplate, registered, parked, last_area, owner, owner_phone) "
            "VALUES (?, ?, 0, ?, ?, ?)",
            (plate, reg, area, owner, phone),
        )
    conn.commit()
    conn.close()
    print("[+] Test data seeded.")


# ── Entry point ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="VIGIL Central Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8000, help="Port")
    parser.add_argument("--seed", action="store_true", help="Seed test data on startup")
    args = parser.parse_args()

    init_db()
    if args.seed:
        seed_test_data()

    print(f"\n{'='*55}")
    print(f"  VIGIL Server")
    print(f"  Listening on  : {args.host}:{args.port}")
    print(f"  Database      : {DB_PATH}")
    print(f"  Speed limit   : {SPEED_LIMIT_KMPH} km/h")
    print(f"  Parked timeout: {PARKED_TIMEOUT_SECONDS}s")
    print(f"  Char conf threshold: {CHAR_CONFIDENCE_THRESHOLD}%")
    print(f"  Areas         : {list(AREA_ADJACENCY.keys())}")
    print(f"{'='*55}\n")

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()

