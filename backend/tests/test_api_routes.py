import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_navigation_geocode_endpoint():
    response = client.get("/api/v1/navigation/geocode?q=Paris")
    assert response.status_code == 200
    data = response.json()
    assert "lat" in data
    assert "lon" in data

def test_analytics_dashboard_endpoint():
    response = client.get("/api/v1/analytics/dashboard?user_id=test")
    assert response.status_code == 200
    data = response.json()
    assert "travel_statistics" in data
    assert "recommendation_accuracy" in data

def test_diary_export_pdf_endpoint():
    response = client.get("/api/v1/diary/export-pdf/trip_99")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
