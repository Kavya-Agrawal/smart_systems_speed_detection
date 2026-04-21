# import random
# import string
# from datetime import datetime, timedelta
# import csv

# # -----------------------------
# # CONFIG
# # -----------------------------
# NUM_VEHICLES = 200
# NUM_ZONES = 8
# NUM_EVENTS = 2000

# # -----------------------------
# # HELPERS
# # -----------------------------
# def random_plate():
#     return f"AS{random.randint(1,99):02d}{''.join(random.choices(string.ascii_uppercase, k=2))}{random.randint(1000,9999)}"

# def random_phone():
#     return "9" + "".join(random.choices(string.digits, k=9))

# def random_email(name):
#     domains = ["gmail.com", "iitg.ac.in", "yahoo.com"]
#     return name.lower().replace(" ", "") + "@" + random.choice(domains)

# def random_name():
#     first = ["Aman", "Riya", "Kavya", "Rahul", "Sneha", "Arjun", "Neha"]
#     last = ["Sharma", "Das", "Verma", "Gupta", "Mehta"]
#     return random.choice(first) + " " + random.choice(last)

# def random_timestamp():
#     return datetime.now() - timedelta(minutes=random.randint(0, 10000))

# # -----------------------------
# # ZONES TABLE
# # -----------------------------
# zones = []
# zone_names = [
#     "Academic Complex", "Hostel Area", "Main Gate",
#     "Library Road", "Market Area", "Sports Complex",
#     "Faculty Housing", "Lake Side"
# ]

# for i in range(NUM_ZONES):
#     zones.append({
#         "zone_id": i,
#         "zone_name": zone_names[i],
#         "speed_limit": random.choice([20, 30, 40]),
#         "risk_score": round(random.uniform(0.1, 0.9), 2),
#         "num_accidents": random.randint(0, 15),
#         "vehicle_density": random.randint(50, 300)
#     })

# # -----------------------------
# # VEHICLES TABLE
# # -----------------------------
# vehicles = []

# for _ in range(NUM_VEHICLES):
#     name = random_name()
#     vehicles.append({
#         "plate": random_plate(),
#         "owner_name": name,
#         "phone": random_phone(),
#         "email": random_email(name),
#         "total_violations": 0,
#         "last_seen": "",
#         "currently_in_campus": random.choice([True, False]),
#         "max_speed": 0,
#         "min_speed": 999,
#         "avg_speed": 0
#     })

# # -----------------------------
# # EVENTS TABLE
# # -----------------------------
# events = []
# violations = []

# vehicle_speed_history = {v["plate"]: [] for v in vehicles}

# for i in range(NUM_EVENTS):
#     vehicle = random.choice(vehicles)
#     zone = random.choice(zones)

#     speed = random.randint(10, 80)
#     timestamp = random_timestamp()

#     is_violation = speed > zone["speed_limit"]

#     event = {
#         "event_id": i,
#         "plate": vehicle["plate"],
#         "zone_id": zone["zone_id"],
#         "speed": speed,
#         "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
#         "is_violation": is_violation,
#         "image_url": f"/images/{vehicle['plate']}_{i}.jpg"
#     }

#     events.append(event)

#     # Update stats
#     vehicle_speed_history[vehicle["plate"]].append(speed)
#     vehicle["last_seen"] = event["timestamp"]

#     # Violations
#     if is_violation:
#         vehicle["total_violations"] += 1
#         violations.append({
#             "violation_id": len(violations),
#             "event_id": i,
#             "plate": vehicle["plate"],
#             "fine": random.choice([100, 200, 500]),
#             "status": random.choice(["paid", "pending", "ignored"])
#         })

# # -----------------------------
# # UPDATE VEHICLE STATS
# # -----------------------------
# for v in vehicles:
#     speeds = vehicle_speed_history[v["plate"]]
#     if speeds:
#         v["max_speed"] = max(speeds)
#         v["min_speed"] = min(speeds)
#         v["avg_speed"] = round(sum(speeds) / len(speeds), 2)

# # -----------------------------
# # SAVE TO CSV
# # -----------------------------
# def save_csv(filename, data):
#     with open(filename, "w", newline="") as f:
#         writer = csv.DictWriter(f, fieldnames=data[0].keys())
#         writer.writeheader()
#         writer.writerows(data)

# save_csv("vehicles.csv", vehicles)
# save_csv("zones.csv", zones)
# save_csv("events.csv", events)
# save_csv("violations.csv", violations)

# print("✅ Dummy data generated successfully!")


import random
import string
from datetime import datetime, timedelta
import csv

# ---------------- CONFIG ----------------
NUM_VEHICLES = 120
NUM_EVENTS = 1500

# ---------------- HELPERS ----------------
def random_plate():
    states = ["AS", "ML", "WB", "DL", "KA"]
    return f"{random.choice(states)}{random.randint(1,99):02d}{''.join(random.choices(string.ascii_uppercase, k=2))}{random.randint(1000,9999)}"

def random_phone():
    return "+91" + "".join(random.choices(string.digits, k=10))

def random_name():
    first = ["Aman","Riya","Kavya","Rahul","Sneha","Arjun","Neha","Vikram","Pooja","Rajesh","Meena","Rohan","Ananya","Priya","Suresh"]
    last = ["Sharma","Das","Verma","Gupta","Mehta","Iyer","Nair","Bose","Joshi","Kumar"]
    return random.choice(first) + " " + random.choice(last)

def random_email(name):
    domains = ["gmail.com","iitg.ac.in"]
    return name.lower().replace(" ",".") + "@" + random.choice(domains)

def rand_time():
    return datetime.now() - timedelta(minutes=random.randint(0, 1440))

# ---------------- ZONES ----------------
zones = [
    {"zone_id":1,"name":"Main Gate","limit":20,"risk":"HIGH","accidents":34,"vehicles":120},
    {"zone_id":2,"name":"Academic Block A","limit":20,"risk":"MEDIUM","accidents":18,"vehicles":90},
    {"zone_id":3,"name":"Academic Block B","limit":20,"risk":"LOW","accidents":7,"vehicles":60},
    {"zone_id":4,"name":"Residential Zone","limit":15,"risk":"MEDIUM","accidents":22,"vehicles":80},
    {"zone_id":5,"name":"Sports Complex","limit":25,"risk":"LOW","accidents":5,"vehicles":40},
    {"zone_id":6,"name":"Hospital Road","limit":20,"risk":"HIGH","accidents":29,"vehicles":70},
    {"zone_id":7,"name":"Library Junction","limit":20,"risk":"MEDIUM","accidents":11,"vehicles":65},
    {"zone_id":8,"name":"GH-4 Gate","limit":20,"risk":"HIGH","accidents":41,"vehicles":100}
]

# ---------------- VEHICLES ----------------
vehicles = []
speed_map = {}

for _ in range(NUM_VEHICLES):
    name = random_name()
    plate = random_plate()
    vehicles.append({
        "plate": plate,
        "owner": name,
        "phone": random_phone(),
        "email": random_email(name),
        "type": random.choice(["Student","Faculty","Staff","Visitor","Vendor"]),
        "total_violations": 0,
        "last_seen": "",
        "currently_in_campus": random.choice([True, False]),
        "max_speed": 0,
        "min_speed": 999,
        "avg_speed": 0
    })
    speed_map[plate] = []

# ---------------- EVENTS ----------------
events = []
notifications = []

for i in range(NUM_EVENTS):
    v = random.choice(vehicles)
    z = random.choice(zones)

    speed = random.randint(10, 70)
    t = rand_time()

    violation = speed > z["limit"]

    event = {
        "event_id": i,
        "plate": v["plate"],
        "zone": z["name"],
        "zone_id": z["zone_id"],
        "speed": speed,
        "limit": z["limit"],
        "time": t.strftime("%Y-%m-%d %H:%M:%S"),
        "camera": f"CAM-{random.randint(1,12)}",
        "status": "VIOLATION" if violation else "NORMAL"
    }

    events.append(event)

    # update stats
    speed_map[v["plate"]].append(speed)
    v["last_seen"] = event["time"]

    if violation:
        v["total_violations"] += 1

        notifications.append({
            "notif_id": len(notifications),
            "plate": v["plate"],
            "owner": v["owner"],
            "phone": v["phone"],
            "type": random.choice(["SMS","EMAIL","SYSTEM"]),
            "message": f"{v['plate']} overspeeding ({speed} km/h) at {z['name']}",
            "status": random.choice(["Delivered","Failed"]),
            "time": event["time"]
        })

# ---------------- UPDATE VEHICLE STATS ----------------
for v in vehicles:
    speeds = speed_map[v["plate"]]
    if speeds:
        v["max_speed"] = max(speeds)
        v["min_speed"] = min(speeds)
        v["avg_speed"] = round(sum(speeds)/len(speeds),2)

# ---------------- SAVE ----------------
def save(name, data):
    with open(name,"w",newline="") as f:
        writer = csv.DictWriter(f, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)

save("vehicles.csv", vehicles)
save("zones.csv", zones)
save("events.csv", events)
save("notifications.csv", notifications)

print("✅ Clean dummy data ready for your dashboard")