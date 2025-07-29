from datetime import datetime
from fastapi import HTTPException
from io import StringIO
import csv

def parse_date(date_str: str) -> datetime:
    """Parse a date string into a datetime object."""
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d %H:%M")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format")

def check_event_permission(event, current_user):
    """Check if the user has permission to modify an event."""
    if current_user["role"] == "admin":
        return
    if event.created_by != current_user["id"]:
        raise HTTPException(status_code=403, detail="Access denied: you are not the event organizer")

def generate_csv(attendees):
    """Generate a CSV string from a list of attendees."""
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["ID", "Name", "Email"])
    for a in attendees:
        writer.writerow([a["id"], a["name"], a["email"]])
    buffer.seek(0)
    return buffer