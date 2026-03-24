

from fastapi import FastAPI, Depends
from sqlalchemy import create_engine, Column, String, Integer, Float, Boolean, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base
import pandas as pd


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()   

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all (for now)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)






# =============================
# DB SETUP
# =============================
DATABASE_URL = "sqlite:///./veloguard.db"

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

# =============================
# MODELS (MATCH YOUR SCHEMA)
# =============================

class Vehicle(Base):
    __tablename__ = "vehicles"

    plate = Column(String, primary_key=True)
    owner = Column(String)
    phone = Column(String)
    email = Column(String)
    type = Column(String)

    total_violations = Column(Integer, default=0)
    last_seen = Column(String)
    currently_in_campus = Column(Boolean)

    max_speed = Column(Integer)
    min_speed = Column(Integer)
    avg_speed = Column(Float)


class Zone(Base):
    __tablename__ = "zones"

    zone_id = Column(Integer, primary_key=True)
    name = Column(String)
    speed_limit = Column(Integer)
    risk_level = Column(String)

    accident_count = Column(Integer, default=0)
    vehicle_density = Column(Integer, default=0)


class Event(Base):
    __tablename__ = "events"

    event_id = Column(Integer, primary_key=True)
    plate = Column(String, ForeignKey("vehicles.plate"))
    zone_id = Column(Integer, ForeignKey("zones.zone_id"))

    speed = Column(Integer)
    speed_limit = Column(Integer)

    event_time = Column(String)
    camera_id = Column(String)

    status = Column(String)


class Notification(Base):
    __tablename__ = "notifications"

    notif_id = Column(Integer, primary_key=True)

    plate = Column(String)
    owner = Column(String)
    phone = Column(String)

    type = Column(String)
    message = Column(String)

    delivery_status = Column(String)
    sent_time = Column(String)


# CREATE TABLES
Base.metadata.create_all(bind=engine)

# =============================
# FASTAPI APP
# =============================
# app = FastAPI()


# =============================
# DB DEPENDENCY
# =============================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================
# LOAD CSV DATA (IMPORTANT)
# =============================
@app.post("/load-data")
def load_data(db=Depends(get_db)):
    vehicles = pd.read_csv("vehicles.csv")
    zones = pd.read_csv("zones.csv")
    events = pd.read_csv("events.csv")
    notifications = pd.read_csv("notifications.csv")

    # ---- VEHICLES ----
    for _, row in vehicles.iterrows():
        db.merge(Vehicle(**row.to_dict()))

    # ---- ZONES (FIX MAPPING) ----
    for _, row in zones.iterrows():
        db.merge(Zone(
            zone_id=row["zone_id"],
            name=row["name"],
            speed_limit=row["limit"],          # FIXED
            risk_level=row["risk"],            # FIXED
            accident_count=row["accidents"],
            vehicle_density=row["vehicles"]
        ))

    # ---- EVENTS (FIX MAPPING) ----
    for _, row in events.iterrows():
        db.merge(Event(
            event_id=row["event_id"],
            plate=row["plate"],
            zone_id=row["zone_id"],
            speed=row["speed"],
            speed_limit=row["limit"],
            event_time=row["time"],
            camera_id=row["camera"],
            status=row["status"]
        ))

    # ---- NOTIFICATIONS (FIX MAPPING) ----
    for _, row in notifications.iterrows():
        db.merge(Notification(
            notif_id=row["notif_id"],
            plate=row["plate"],
            owner=row["owner"],
            phone=row["phone"],
            type=row["type"],
            message=row["message"],
            delivery_status=row["status"],     # FIXED
            sent_time=row["time"]
        ))

    db.commit()
    return {"message": "✅ Data loaded successfully"}


# =============================
# API ENDPOINTS
# =============================

@app.get("/")
def root():
    return {"message": "VeloGuard Backend Running 🚀"}


@app.get("/vehicles")
def get_vehicles(db=Depends(get_db)):
    return db.query(Vehicle).all()


@app.get("/zones")
def get_zones(db=Depends(get_db)):
    return db.query(Zone).all()


@app.get("/events")
def get_events(db=Depends(get_db)):
    return db.query(Event).order_by(Event.event_time.desc()).limit(100).all()


@app.get("/violations")
def get_violations(db=Depends(get_db)):
    return db.query(Event).filter(Event.status == "VIOLATION").all()


@app.get("/notifications")
def get_notifications(db=Depends(get_db)):
    return db.query(Notification).order_by(Notification.sent_time.desc()).limit(50).all()


# =============================
# BASIC ANALYTICS (VERY USEFUL)
# =============================

@app.get("/stats")
def get_stats(db=Depends(get_db)):
    total_vehicles = db.query(Vehicle).count()
    total_events = db.query(Event).count()
    total_violations = db.query(Event).filter(Event.status == "VIOLATION").count()

    return {
        "vehicles": total_vehicles,
        "events": total_events,
        "violations": total_violations
    }