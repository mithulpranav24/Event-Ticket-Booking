import heapq
from datetime import datetime, timedelta
from models import Event
from database import Database
from intervaltree import IntervalTree
from utils import parse_date

class EventManager:
    def __init__(self, db: Database, scheduler):
        """Initialize EventManager with database and scheduler."""
        self.db = db
        self.scheduler = scheduler

    def add_event(self, event: Event) -> bool:
        """Add a new event to the database."""
        return self.db.add_event(event)

    def get_event(self, event_id: str) -> Event | None:
        """Retrieve an event by ID."""
        event_data = self.db.get_event(event_id)
        if event_data:
            date = parse_date(event_data["date"])
            return Event(
                id=event_data["id"],
                title=event_data["title"],
                date=date,
                capacity=event_data["capacity"],
                duration_hours=event_data["duration_hours"],
                type=event_data["type"],
                instructor=event_data["instructor"],
                created_by=event_data["created_by"]
            )
        return None

    def list_events(self) -> list[Event]:
        """Retrieve all events."""
        db_events = self.db.list_events()
        events = []
        for e in db_events:
            date = parse_date(e["date"])
            evt = Event(
                id=e["id"],
                title=e["title"],
                date=date,
                capacity=e["capacity"],
                duration_hours=e["duration_hours"],
                type=e["type"],
                instructor=e["instructor"],
                created_by=e["created_by"]
            )
            events.append(evt)
        return events

    def delete_event(self, event_id: str) -> bool:
        """Delete an event."""
        event = self.get_event(event_id)
        if event and self.db.delete_event(event_id):
            self.scheduler.remove_event(event_id)
            return True
        return False

    def update_event(self, event_id: str, title=None, date=None, capacity=None, duration_hours=None, type=None, instructor=None) -> bool:
        """Update an event and reschedule if date or duration changes."""
        event = self.get_event(event_id)
        if not event:
            return False
        parsed_date = parse_date(date) if date else None
        if self.db.update_event(event_id, title, parsed_date.isoformat() if parsed_date else None, capacity, duration_hours, type, instructor):
            if date or duration_hours:  # Reschedule if date or duration changed
                self.scheduler.remove_event(event_id)
                updated_event = self.get_event(event_id)
                self.scheduler.schedule_event(updated_event)
            return True
        return False

class Scheduler:
    def __init__(self, db: Database):
        """Initialize Scheduler with database and load existing schedule."""
        self.db = db
        self.event_queue = []
        self.intervals = IntervalTree()
        self.load_schedule()

    def load_schedule(self):
        """Load scheduled events from the database."""
        for event_id, start_ts, end_ts in self.db.get_schedule():
            self.intervals[start_ts:end_ts] = event_id
            heapq.heappush(self.event_queue, (datetime.fromtimestamp(start_ts), event_id))
        heapq.heapify(self.event_queue)

    def schedule_event(self, event: Event):
        """Schedule an event and check for conflicts."""
        start = event.date
        end = start + timedelta(hours=event.duration_hours)
        start_ts = start.timestamp()
        end_ts = end.timestamp()
        
        if self.intervals.overlaps(start_ts, end_ts):
            overlapping = self.intervals[start_ts:end_ts]
            conflicting_id = next(iter(overlapping)).data
            conflicting_event = self.db.get_event(conflicting_id)
            raise ValueError(f"Conflict with event {conflicting_event['title']} at {conflicting_event['date']}")
        
        self.intervals[start_ts:end_ts] = event.id
        heapq.heappush(self.event_queue, (event.date, event.id))
        self.db.add_schedule(event.id, start_ts, end_ts)

    def remove_event(self, event_id: str):
        """Remove an event from the schedule."""
        to_remove = [iv for iv in self.intervals if iv.data == event_id]
        for iv in to_remove:
            self.intervals.remove(iv)
        self.event_queue = [(t, eid) for t, eid in self.event_queue if eid != event_id]
        heapq.heapify(self.event_queue)
        self.db.remove_schedule(event_id)

    def get_next_event(self) -> tuple[datetime, str] | None:
        """Retrieve the next scheduled event."""
        while self.event_queue and self.event_queue[0][0] < datetime.now():
            heapq.heappop(self.event_queue)  # Remove past events
        return self.event_queue[0] if self.event_queue else None