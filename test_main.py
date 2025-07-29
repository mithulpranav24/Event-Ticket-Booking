import pytest
from fastapi.testclient import TestClient
from main import app, db
from passlib.hash import bcrypt
from models import User
from datetime import datetime

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def organizer_user():
    user = User(
        id="user1",
        name="Test Organizer",
        email="organizer@example.com",
        password=bcrypt.hash("password123"),
        role="organizer"
    )
    db.add_user(user)
    return user

@pytest.fixture
def auth_headers(client, organizer_user):
    response = client.post("/login", json={"email": "organizer@example.com", "password": "password123"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}

def test_register_user(client):
    response = client.post("/register", json={
        "id": "user2",
        "name": "Test User",
        "email": "test@example.com",
        "password": "password123",
        "role": "attendee"
    })
    assert response.status_code == 201
    assert response.json()["message"] == "User registered"

def test_login_success(client, organizer_user):
    response = client.post("/login", json={"email": "organizer@example.com", "password": "password123"})
    assert response.status_code == 200
    assert "access_token" in response.json()
    assert "refresh_token" in response.json()

def test_create_event(auth_headers, client):
    response = client.post("/events", json={
        "id": "event1",
        "title": "Test Event",
        "date": "2025-05-01T10:00:00",
        "capacity": 50,
        "duration_hours": 2.0,
        "type": "basic",
        "instructor": "John Doe"
    }, headers=auth_headers)
    assert response.status_code == 201
    assert response.json()["message"] == "Event created"

def test_list_events(client):
    response = client.get("/events")
    assert response.status_code == 200
    assert response.json()["message"] == "Events retrieved"
    assert isinstance(response.json()["data"], list)

def test_register_attendee(client, auth_headers):
    # Create event first
    client.post("/events", json={
        "id": "event1",
        "title": "Test Event",
        "date": "2025-05-01T10:00:00",
        "capacity": 50,
        "duration_hours": 2.0,
        "type": "basic",
        "instructor": "John Doe"
    }, headers=auth_headers)
    response = client.post("/events/event1/register", json={
        "id": "attendee1",
        "name": "Test Attendee",
        "email": "attendee@example.com"
    })
    assert response.status_code == 200
    assert response.json()["message"].startswith("Test Attendee registered")

def test_invalid_capacity(auth_headers, client):
    response = client.post("/events", json={
        "id": "event2",
        "title": "Invalid Event",
        "date": "2025-05-02T10:00:00",
        "capacity": 0,
        "duration_hours": 1.0,
        "type": "basic"
    }, headers=auth_headers)
    assert response.status_code == 400
    assert response.json()["detail"] == "Capacity must be positive"