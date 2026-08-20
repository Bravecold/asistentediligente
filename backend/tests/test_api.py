import os
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["APP_ENV"] = "development"

from fastapi.testclient import TestClient
from app.main import Base, app, engine

Base.metadata.create_all(engine)
client = TestClient(app)


def test_health_and_catalog():
    with client:
        assert client.get("/health").status_code == 200
        assert len(client.get("/api/procedures").json()) >= 3


def test_health_request_requires_sensitive_consent():
    with client:
        payload = {"requester_name": "Ana Pérez", "beneficiary_name": "Luis Pérez", "procedure_id": "ops-cita-eps", "description": "Necesito orientación para agendar medicina general", "accept_privacy": True, "accept_sensitive_data": False}
        assert client.post("/api/requests", json=payload).status_code == 422
        payload["accept_sensitive_data"] = True
        response = client.post("/api/requests", json=payload)
        assert response.status_code == 201
        assert response.json()["status"] == "submitted"


def test_role_protects_queue():
    with client:
        assert client.get("/api/requests").status_code == 403
        assert client.get("/api/requests", headers={"X-Demo-Role": "manager"}).status_code == 200

