import sqlite3
from datetime import datetime

class Database:
    def __init__(self, db_name="events.db"):
        """
        Initialize SQLite database connection.
        Note: For production, consider using PostgreSQL for better scalability.
        """
        self.conn = sqlite3.connect(db_name, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        """Create database tables with appropriate indexes."""
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'organizer', 'attendee'))
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                date TEXT NOT NULL,
                capacity INTEGER NOT NULL,
                duration_hours REAL NOT NULL,
                type TEXT NOT NULL,
                instructor TEXT,
                created_by TEXT NOT NULL,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendees (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS event_attendees (
                event_id TEXT,
                attendee_id TEXT,
                FOREIGN KEY (event_id) REFERENCES events(id),
                FOREIGN KEY (attendee_id) REFERENCES attendees(id),
                PRIMARY KEY (event_id, attendee_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS schedule (
                event_id TEXT PRIMARY KEY,
                start_ts REAL NOT NULL,
                end_ts REAL NOT NULL,
                FOREIGN KEY (event_id) REFERENCES events(id)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_event_attendees_event_id ON event_attendees(event_id)')
        self.conn.commit()

    def add_event(self, event):
        """Add an event to the database."""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO events (id, title, date, capacity, duration_hours, type, instructor, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (event.id, event.title, event.date.isoformat(), event.capacity, event.duration_hours, event.type, event.instructor, event.created_by))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_event(self, event_id):
        """Retrieve an event by ID."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM events WHERE id = ?', (event_id,))
        row = cursor.fetchone()
        if row:
            return {
                "id": row[0], "title": row[1], "date": row[2], "capacity": row[3],
                "duration_hours": row[4], "type": row[5], "instructor": row[6], "created_by": row[7]
            }
        return None

    def list_events(self):
        """Retrieve all events."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM events')
        rows = cursor.fetchall()
        return [{
            "id": r[0], "title": r[1], "date": r[2], "capacity": r[3],
            "duration_hours": r[4], "type": r[5], "instructor": r[6], "created_by": r[7]
        } for r in rows]

    def add_attendee(self, attendee):
        """Add an attendee to the database."""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO attendees (id, name, email)
            VALUES (?, ?, ?)
        ''', (attendee.id, attendee.name, attendee.email))
        self.conn.commit()

    def register_attendee(self, event_id, attendee_id):
        """Register an attendee for an event."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM event_attendees WHERE event_id = ?', (event_id,))
        current_attendees = cursor.fetchone()[0]
        cursor.execute('SELECT capacity FROM events WHERE id = ?', (event_id,))
        capacity = cursor.fetchone()
        if capacity is None:
            return False
        capacity = capacity[0]
        if current_attendees >= capacity:
            return False
        cursor.execute('''
            INSERT OR IGNORE INTO event_attendees (event_id, attendee_id)
            VALUES (?, ?)
        ''', (event_id, attendee_id))
        self.conn.commit()
        return cursor.rowcount > 0

    def get_attendee_count(self, event_id):
        """Get the number of attendees for an event."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM event_attendees WHERE event_id = ?', (event_id,))
        result = cursor.fetchone()
        return result[0] if result else 0

    def delete_event(self, event_id):
        """Delete an event and its attendees."""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM event_attendees WHERE event_id = ?', (event_id,))
        cursor.execute('DELETE FROM schedule WHERE event_id = ?', (event_id,))
        cursor.execute('DELETE FROM events WHERE id = ?', (event_id,))
        self.conn.commit()
        return cursor.rowcount > 0

    def update_event(self, event_id, title=None, date=None, capacity=None, duration_hours=None, type=None, instructor=None):
        """Update an event's details."""
        cursor = self.conn.cursor()
        updates = {}
        if title: updates["title"] = title
        if date: updates["date"] = date
        if capacity: updates["capacity"] = capacity
        if duration_hours: updates["duration_hours"] = duration_hours
        if type: updates["type"] = type
        if instructor: updates["instructor"] = instructor
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
            values = list(updates.values()) + [event_id]
            cursor.execute(f'UPDATE events SET {set_clause} WHERE id = ?', values)
            self.conn.commit()
            return cursor.rowcount > 0
        return False

    def add_schedule(self, event_id, start_ts, end_ts):
        """Add an event to the schedule table."""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO schedule (event_id, start_ts, end_ts)
            VALUES (?, ?, ?)
        ''', (event_id, start_ts, end_ts))
        self.conn.commit()

    def remove_schedule(self, event_id):
        """Remove an event from the schedule table."""
        cursor = self.conn.cursor()
        cursor.execute('DELETE FROM schedule WHERE event_id = ?', (event_id,))
        self.conn.commit()

    def get_schedule(self):
        """Retrieve all scheduled events."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT event_id, start_ts, end_ts FROM schedule')
        return [(row[0], row[1], row[2]) for row in cursor.fetchall()]

    def add_user(self, user):
        """Add a user to the database."""
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO users (id, name, email, password, role)
            VALUES (?, ?, ?, ?, ?)
        ''', (user.id, user.name, user.email, user.password, user.role))
        self.conn.commit()

    def get_user_by_email(self, email):
        """Retrieve a user by email."""
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        row = cursor.fetchone()
        if row:
            return {"id": row[0], "name": row[1], "email": row[2], "password": row[3], "role": row[4]}
        return None

    def list_attendees_for_event(self, event_id):
        """Retrieve all attendees for an event."""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT a.id, a.name, a.email FROM attendees a
            JOIN event_attendees ea ON a.id = ea.attendee_id
            WHERE ea.event_id = ?
        ''', (event_id,))
        rows = cursor.fetchall()
        return [{"id": r[0], "name": r[1], "email": r[2]} for r in rows]

    def close(self):
        """Close the database connection."""
        self.conn.close()