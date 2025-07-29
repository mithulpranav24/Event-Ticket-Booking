from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class Event:
    id: str
    title: str
    date: datetime
    capacity: int
    duration_hours: float
    type: str = "basic"
    instructor: Optional[str] = None
    created_by: Optional[str] = None  # user_id of organizer

    def display_details(self) -> str:
        """Return a string representation of the event details."""
        return f"Event: {self.title}, Date: {self.date}, Capacity: {self.capacity}, Duration: {self.duration_hours} hours"

@dataclass
class Attendee:
    id: str
    name: str
    email: str

@dataclass
class User:
    id: str
    name: str
    email: str
    password: str
    role: str  # 'admin', 'organizer', or 'attendee'


