from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi import status
from passlib.hash import bcrypt
from pydantic import BaseModel
from typing import Optional, List, Literal
from models import Event, Attendee, User
from manager import EventManager, Scheduler
from database import Database
from auth import get_current_user, create_access_token, create_refresh_token, oauth2_scheme
from utils import parse_date, check_event_permission, generate_csv
import logging
from contextlib import asynccontextmanager
from jose import JWTError, jwt  # Added import for jwt and JWTError

from dotenv import load_dotenv
import os

load_dotenv()  # Load variables from .env file
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS"))

# Other authentication functions (e.g., create_access_token, get_current_user)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database
db = Database()

# FastAPI App
@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    logger.info("Closing database connection")
    db.close()

app = FastAPI(lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Init
scheduler = Scheduler(db)
manager = EventManager(db, scheduler)

# -------------------------------
# Schemas
# -------------------------------
class EventCreate(BaseModel):
    id: str
    title: str
    date: str
    capacity: int
    duration_hours: float = 1.0
    type: Literal["basic", "premium"] = "basic"
    instructor: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "id": "event1",
                "title": "Python Workshop",
                "date": "2025-05-01T10:00:00",
                "capacity": 50,
                "duration_hours": 2.0,
                "type": "basic",
                "instructor": "John Doe"
            }
        }

class EventUpdate(BaseModel):
    title: Optional[str] = None
    date: Optional[str] = None
    capacity: Optional[int] = None
    duration_hours: Optional[float] = None
    type: Optional[Literal["basic", "premium"]] = None
    instructor: Optional[str] = None

class AttendeeCreate(BaseModel):
    id: str
    name: str
    email: str

class UserRegister(BaseModel):
    id: str
    name: str
    email: str
    password: str
    role: Literal["admin", "organizer", "attendee"]

class UserLogin(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str

# -------------------------------
# Auth Routes
# -------------------------------
@app.post("/register", response_model=dict, status_code=status.HTTP_201_CREATED, summary="Register a new user")
def register(user: UserRegister):
    """Register a new user with a specified role."""
    existing = db.get_user_by_email(user.email)
    if existing:
        raise HTTPException(status_code=400, detail="User already exists")
    hashed = bcrypt.hash(user.password)
    user_obj = User(user.id, user.name, user.email, hashed, user.role)
    db.add_user(user_obj)
    logger.info(f"User {user.email} registered with role {user.role}")
    return {"message": "User registered", "data": {"email": user.email}}

@app.post("/login", response_model=TokenResponse, summary="Login and receive access/refresh tokens")
def login(user: UserLogin):
    """Authenticate user and return access and refresh tokens."""
    db_user = db.get_user_by_email(user.email)
    if not db_user or not bcrypt.verify(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": user.email})
    refresh_token = create_refresh_token(data={"sub": user.email})
    logger.info(f"User {user.email} logged in")
    return {"access_token": access_token, "refresh_token": refresh_token}

@app.post("/refresh", response_model=dict, summary="Refresh access token")
@app.post("/refresh", response_model=dict, summary="Refresh access token")
def refresh(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Invalid refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        logger.info(f"Refreshing token: {token[:20]}...")
        logger.info(f"Using SECRET_KEY: {'set' if SECRET_KEY else 'unset'}, ALGORITHM: {ALGORITHM}")
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        logger.info(f"Token payload: {payload}")
        email: str = payload.get("sub")
        if email is None:
            logger.error("No 'sub' in token payload")
            raise credentials_exception
        access_token = create_access_token(data={"sub": email})
        logger.info(f"Token refreshed for {email}")
        return {"message": "Token refreshed", "data": {"access_token": access_token}}
    except JWTError as e:
        logger.error(f"JWTError: {str(e)}")
        raise credentials_exception
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Refresh failed: {str(e)}")

# -------------------------------
# Event Routes
# -------------------------------
@app.get("/", response_model=dict, summary="API root endpoint")
def root():
    """Welcome message for the Event Management API."""
    return {"message": "Welcome to Event Management API", "data": {}}

@app.post("/events", response_model=dict, status_code=status.HTTP_201_CREATED, summary="Create a new event")
def create_event(event: EventCreate, current_user=Depends(get_current_user)):
    """Create a new event (organizers only)."""
    if current_user["role"] != "organizer":
        raise HTTPException(status_code=403, detail="Only organizers can create events")
    if event.capacity <= 0:
        raise HTTPException(status_code=400, detail="Capacity must be positive")
    evt = Event(
        id=event.id,
        title=event.title,
        date=parse_date(event.date),
        capacity=event.capacity,
        duration_hours=event.duration_hours,
        type=event.type,
        instructor=event.instructor,
        created_by=current_user["id"]
    )
    if manager.add_event(evt):
        scheduler.schedule_event(evt)
        logger.info(f"Event {event.id} created by {current_user['id']}")
        return {"message": "Event created", "data": evt.display_details()}
    raise HTTPException(status_code=400, detail="Event ID already exists")

@app.get("/events", response_model=dict, summary="List all events")
def list_events():
    """Retrieve a list of all events."""
    events = manager.list_events()
    data = [{"id": e.id, "title": e.title, "date": str(e.date)} for e in events]
    return {"message": "Events retrieved", "data": data}

@app.put("/events/{event_id}", response_model=dict, summary="Update an event")
def update_event(event_id: str, event: EventUpdate, current_user=Depends(get_current_user)):
    """Update an existing event (organizers or admins only)."""
    evt = manager.get_event(event_id)
    if not evt:
        raise HTTPException(status_code=404, detail="Event not found")
    check_event_permission(evt, current_user)
    if event.capacity is not None and event.capacity <= 0:
        raise HTTPException(status_code=400, detail="Capacity must be positive")
    success = manager.update_event(
        event_id,
        title=event.title,
        date=event.date,
        capacity=event.capacity,
        duration_hours=event.duration_hours,
        type=event.type,
        instructor=event.instructor
    )
    if success:
        logger.info(f"Event {event_id} updated by {current_user['id']}")
        return {"message": f"Event {event_id} updated", "data": manager.get_event(event_id).display_details()}
    raise HTTPException(status_code=400, detail="Update failed: invalid data or event not found")

@app.delete("/events/{event_id}", response_model=dict, summary="Delete an event")
def delete_event(event_id: str, current_user=Depends(get_current_user)):
    """Delete an event (organizers or admins only)."""
    evt = manager.get_event(event_id)
    if not evt:
        raise HTTPException(status_code=404, detail="Event not found")
    check_event_permission(evt, current_user)
    if manager.delete_event(event_id):
        logger.info(f"Event {event_id} deleted by {current_user['id']}")
        return {"message": f"Event {event_id} deleted", "data": {}}
    raise HTTPException(status_code=400, detail="Delete failed: event not found")

@app.get("/scheduler/next", response_model=dict, summary="Get the next scheduled event")
def get_next_event():
    """Retrieve the next scheduled event."""
    next_event = scheduler.get_next_event()
    if next_event:
        date, event_id = next_event
        event = manager.get_event(event_id)
        return {"message": "Next event retrieved", "data": {"title": event.title, "date": str(date)}}
    return {"message": "No scheduled events", "data": {}}

# -------------------------------
# Attendee Routes
# -------------------------------
@app.post("/events/{event_id}/register", response_model=dict, summary="Register an attendee for an event")
def register_attendee(event_id: str, attendee: AttendeeCreate):
    """Register an attendee for an event."""
    event = manager.get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    att = Attendee(attendee.id, attendee.name, attendee.email)
    db.add_attendee(att)
    if db.register_attendee(event_id, att.id):
        logger.info(f"Attendee {att.id} registered for event {event_id}")
        return {"message": f"{att.name} registered for {event.title}", "data": {"attendee_id": att.id}}
    raise HTTPException(status_code=400, detail="Registration failed: event is full")

@app.get("/events/{event_id}/attendees/export", response_model=None, summary="Export attendees as CSV")
def export_attendees(event_id: str, current_user=Depends(get_current_user)):
    """Export the list of attendees for an event as a CSV file (organizers or admins only)."""
    event = manager.get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    check_event_permission(event, current_user)
    attendees = db.list_attendees_for_event(event_id)
    csv_data = generate_csv(attendees)
    logger.info(f"Attendees exported for event {event_id} by {current_user['id']}")
    return StreamingResponse(csv_data, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=attendees.csv"})